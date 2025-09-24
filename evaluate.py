"""Command-line tool for evaluating hackathon answers.

This script reads a set of questions with expected answers and a directory
containing participant submissions.  For each answer, it either calls a
language model (via OpenAI's API) to obtain a structured evaluation or
computes a simple heuristic score.  Results are written to per-participant
JSON files and a consolidated CSV summary.

Usage example:

    python3 evaluate.py --questions questions.json \
        --submissions_dir submissions \
        --out_dir results

Set the --use-llm flag to call the OpenAI API.  You must have the
environment variable OPENAI_API_KEY defined for LLM evaluation.  If this
flag is omitted, the script uses a simple heuristic scoring function.

"""

import argparse
import csv
import json
import os
import sys
import time
import random
import threading
from statistics import median
from typing import Dict, Any, List, Tuple, Optional

from prompts import build_prompt, parse_response

# Only import openai if needed; otherwise it's optional for heuristic mode.
try:
    import openai  # type: ignore
except ImportError:
    openai = None  # type: ignore


DEFAULT_WEIGHTS: Tuple[float, float, float] = (0.3, 0.2, 0.5)
MODEL_NAME = "gpt-4o-mini"

# Global OpenAI concurrency limiter (per-process)
_OPENAI_CONCURRENCY = max(1, int(os.getenv("OPENAI_CONCURRENCY", "6")))
_OPENAI_SEMAPHORE = threading.Semaphore(_OPENAI_CONCURRENCY)

# Default self-consistency runs (can be overridden by env and CLI)
DEFAULT_SC_RUNS = int(os.getenv("SELF_CONSISTENCY_RUNS", "3"))


def load_weights_from_env() -> Tuple[float, float, float]:
    """Load scoring weights from environment variables if set, else defaults.

    Env vars: WEIGHT_COMPLETENESS, WEIGHT_CONCISENESS, WEIGHT_CORRECTNESS.
    If provided and the sum is > 0, weights are normalized to sum to 1.0.
    """
    wc = os.getenv("WEIGHT_COMPLETENESS")
    wz = os.getenv("WEIGHT_CONCISENESS")
    wr = os.getenv("WEIGHT_CORRECTNESS")
    if wc is None and wz is None and wr is None:
        return DEFAULT_WEIGHTS
    try:
        c = float(wc) if wc is not None else DEFAULT_WEIGHTS[0]
        z = float(wz) if wz is not None else DEFAULT_WEIGHTS[1]
        r = float(wr) if wr is not None else DEFAULT_WEIGHTS[2]
    except Exception:
        return DEFAULT_WEIGHTS
    s = c + z + r
    if s <= 0:
        return DEFAULT_WEIGHTS
    return (c / s, z / s, r / s)


def load_questions(path: str) -> Dict[str, Dict[str, str]]:
    """Load the questions file and index by question ID.

    The questions file should be a JSON object with a top-level key
    "questions" containing a list of objects with keys "id", "question",
    and "expected_answer".

    Parameters
    ----------
    path : str
        Path to the questions JSON file.

    Returns
    -------
    dict
        A mapping from question ID to a dict with keys "question" and
        "expected_answer".
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = {}
    for item in data.get("questions", []):
        qid = item["id"]
        questions[qid] = {
            "question": item["question"],
            "expected_answer": item["expected_answer"],
        }
    return questions


def load_submission(path: str) -> Dict[str, Any]:
    """Load a single participant submission from a JSON file.

    Each submission file must contain a "participant_id" and an
    "answers" list.  Each element in the list should be a dict with
    "question_id" and "answer" keys.

    Parameters
    ----------
    path : str
        The path to the submission JSON file.

    Returns
    -------
    dict
        The parsed submission.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def heuristic_evaluate(expected: str, answer: str) -> Dict[str, Any]:
    """Compute heuristic scores for an answer without using an LLM.

    The heuristics are simple and intended as placeholders for testing.

    - Completeness is the fraction of unique expected tokens present in the
      participant answer, scaled to 0–5.
    - Conciseness is based on the ratio of expected length to answer length,
      with shorter answers scoring higher.
    - Correctness is the Jaccard similarity between expected and answer tokens,
      scaled to 0–5.

    Parameters
    ----------
    expected : str
        The reference answer.
    answer : str
        The participant's answer.

    Returns
    -------
    dict
        A dict with keys "completeness", "conciseness", "correctness", and
        "comment".
    """
    import string

    def tokenize(text: str) -> List[str]:
        # Lowercase, split on whitespace, strip punctuation and filter empty
        tokens = [t.strip(string.punctuation).lower() for t in text.split()]
        return [t for t in tokens if t]

    exp_tokens = set(tokenize(expected))
    ans_tokens = set(tokenize(answer))

    # Completeness: fraction of expected tokens present
    if not exp_tokens:
        completeness = 5.0
    else:
        completeness = (len(exp_tokens & ans_tokens) / len(exp_tokens)) * 5.0

    # Conciseness: shorter answers relative to expected get higher scores
    exp_len = len(tokenize(expected))
    ans_len = len(tokenize(answer))
    if ans_len == 0:
        conciseness = 0.0
    else:
        ratio = exp_len / ans_len
        conciseness = 5.0 if ratio >= 1.0 else max(0.0, ratio * 5.0)

    # Correctness: Jaccard similarity scaled to 0–5
    union = exp_tokens | ans_tokens
    if not union:
        correctness = 5.0
    else:
        correctness = (len(exp_tokens & ans_tokens) / len(union)) * 5.0

    # Simple comment explaining missing and extra tokens
    missing = exp_tokens - ans_tokens
    extra = ans_tokens - exp_tokens
    comment_parts: List[str] = []
    if missing:
        comment_parts.append("Missing: " + ", ".join(sorted(missing)))
    if extra:
        comment_parts.append("Extra: " + ", ".join(sorted(extra)))
    comment = "; ".join(comment_parts) if comment_parts else "Good answer"

    return {
        "completeness": round(min(max(completeness, 0.0), 5.0), 2),
        "conciseness": round(min(max(conciseness, 0.0), 5.0), 2),
        "correctness": round(min(max(correctness, 0.0), 5.0), 2),
        "comment": comment,
    }


def _build_prompt_variant(idx: int, question: str, expected: str, participant: str) -> str:
    """Return a slightly varied prompt to promote self-consistency.

    Variations permute field order and lightly rephrase instructions.
    """
    variant = idx % 4
    if variant == 0:
        return build_prompt(question, expected, participant)
    if variant == 1:
        return (
            "Evaluate the answer strictly per the rubric below and return only JSON.\n\n"
            + f"Participant answer: {participant}\n"
            + f"Expected answer: {expected}\n"
            + f"Question: {question}\n\n"
            + "Keys: completeness, conciseness, correctness, comment."
        )
    if variant == 2:
        return (
            "You are a careful grader. Score on a 0-5 scale for each criterion and justify briefly.\n\n"
            + f"Question: {question}\n"
            + f"Participant answer: {participant}\n"
            + f"Expected answer: {expected}\n\n"
            + "Return JSON with completeness, conciseness, correctness, comment."
        )
    # variant 3
    return (
        "Return JSON only. Consider correctness most important, then completeness, then conciseness.\n\n"
        + f"Expected answer: {expected}\n"
        + f"Question: {question}\n"
        + f"Participant answer: {participant}\n\n"
        + "Fields: completeness, conciseness, correctness, comment."
    )


def _call_openai_chat(prompt: str, model: str) -> str:
    """Call OpenAI ChatCompletion with global concurrency limit and retry/backoff.

    Returns the assistant content string.
    """
    if openai is None:
        raise RuntimeError("openai module is not installed; install openai or use heuristic mode")

    max_retries = 4
    base_delay = 0.5

    for attempt in range(max_retries + 1):
        with _OPENAI_SEMAPHORE:
            try:
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )
                return response["choices"][0]["message"]["content"]
            except Exception as e:
                # Backoff on transient errors (rate limit, 5xx, network)
                if attempt >= max_retries:
                    raise RuntimeError(f"OpenAI API request failed after retries: {e}")
        # jittered exponential backoff outside the semaphore to free a slot
        sleep_seconds = base_delay * (2 ** attempt) * (1.0 + random.random() * 0.25)
        time.sleep(sleep_seconds)

    raise RuntimeError("Unreachable: exhausted retries without raising")


def llm_evaluate(question: str, expected: str, answer: str, model: str = MODEL_NAME) -> Dict[str, Any]:
    """Call an OpenAI LLM to score a single answer."""
    prompt = build_prompt(question, expected, answer)
    content = _call_openai_chat(prompt, model)
    return parse_response(content)


def llm_evaluate_self_consistent(
    question: str,
    expected: str,
    answer: str,
    model: str,
    runs: int,
) -> Dict[str, Any]:
    """Run multiple LLM evaluations with prompt variants and aggregate by median."""
    runs = max(1, min(runs, 9))
    results: List[Dict[str, Any]] = []
    for i in range(runs):
        prompt = _build_prompt_variant(i, question, expected, answer)
        try:
            content = _call_openai_chat(prompt, model)
            parsed = parse_response(content)
            results.append(parsed)
        except Exception:
            continue
    if not results:
        raise RuntimeError("All self-consistency runs failed")
    comp = [float(r.get("completeness", 0)) for r in results]
    conc = [float(r.get("conciseness", 0)) for r in results]
    corr = [float(r.get("correctness", 0)) for r in results]
    m_comp = float(median(comp))
    m_conc = float(median(conc))
    m_corr = float(median(corr))
    # Choose the comment from the run whose scores are closest to the medians
    def dist(i: int) -> float:
        ri = results[i]
        return abs(float(ri.get("completeness", 0)) - m_comp) \
             + abs(float(ri.get("conciseness", 0)) - m_conc) \
             + abs(float(ri.get("correctness", 0)) - m_corr)
    best_idx = min(range(len(results)), key=dist)
    chosen_comment = results[best_idx].get("comment", "")
    agg = {
        "completeness": m_comp,
        "conciseness": m_conc,
        "correctness": m_corr,
        "comment": chosen_comment,
    }
    return agg


def weighted_score(evaluation: Dict[str, float], weights: Tuple[float, float, float]) -> float:
    """Compute a weighted score from the individual criteria.

    Weights order: (completeness, conciseness, correctness). Result in [0, 5].
    """
    cpl = evaluation["completeness"]
    ccs = evaluation["conciseness"]
    crt = evaluation["correctness"]
    c_w, z_w, r_w = weights
    score = c_w * cpl + z_w * ccs + r_w * crt
    return round(score, 2)


def evaluate_submission(
    questions: Dict[str, Dict[str, str]],
    submission: Dict[str, Any],
    use_llm: bool = False,
    model: str = MODEL_NAME,
    workers: int = 1,
    weights: Optional[Tuple[float, float, float]] = None,
    sc_runs: int = 1,
) -> Dict[str, Any]:
    """Evaluate all answers from a single participant submission."""
    participant_id = submission.get("participant_id") or "unknown"
    answers_list = list(submission.get("answers", []))
    effective_weights = weights if weights is not None else load_weights_from_env()

    def process_one(item: Dict[str, Any]) -> Dict[str, Any]:
        qid = item.get("question_id")
        ans_text = item.get("answer", "")
        if qid not in questions:
            raise KeyError(f"Question ID '{qid}' not found in questions file")
        q_info = questions[qid]
        q_text = q_info["question"]
        expected = q_info["expected_answer"]
        if use_llm:
            if sc_runs and sc_runs > 1:
                evaluation = llm_evaluate_self_consistent(q_text, expected, ans_text, model=model, runs=sc_runs)
            else:
                evaluation = llm_evaluate(q_text, expected, ans_text, model=model)
        else:
            evaluation = heuristic_evaluate(expected, ans_text)
        evaluation["score"] = weighted_score(evaluation, effective_weights)
        return {"question_id": qid, "evaluation": evaluation}

    results_questions: List[Dict[str, Any]] = []

    if workers and workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        max_workers = max(1, min(workers, 10))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(process_one, item) for item in answers_list]
            results_questions = [f.result() for f in futures]
    else:
        for item in answers_list:
            results_questions.append(process_one(item))

    results = {
        "participant_id": participant_id,
        "questions": results_questions,
    }
    return results


def write_results(results: Dict[str, Any], out_dir: str) -> None:
    """Write a participant's evaluation results to a JSON file.

    The filename is based on the participant_id.
    """
    pid = results.get("participant_id") or "unknown"
    out_path = os.path.join(out_dir, f"{pid}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def append_summary(summary_rows: List[Dict[str, Any]], out_dir: str) -> None:
    """Write the summary CSV file for all participants."""
    csv_path = os.path.join(out_dir, "summary.csv")
    fieldnames = ["participant_id", "question_id", "completeness", "conciseness", "correctness", "score"]
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Ecoflex hackathon answers")
    parser.add_argument("--questions", required=True, help="Path to questions JSON file")
    parser.add_argument("--submissions_dir", required=True, help="Directory containing participant submissions")
    parser.add_argument("--out_dir", required=True, help="Directory to write the results")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI LLM for evaluation instead of heuristics")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel workers for grading")
    parser.add_argument("--weight-completeness", type=float, default=None, help="Weight for completeness")
    parser.add_argument("--weight-conciseness", type=float, default=None, help="Weight for conciseness")
    parser.add_argument("--weight-correctness", type=float, default=None, help="Weight for correctness")
    parser.add_argument("--sc-runs", type=int, default=DEFAULT_SC_RUNS, help="Self-consistency runs (repeat LLM and aggregate)")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    try:
        questions = load_questions(args.questions)
    except Exception as exc:
        print(f"Error loading questions: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.weight_completeness is not None or args.weight_conciseness is not None or args.weight_correctness is not None:
        c = args.weight_completeness if args.weight_completeness is not None else DEFAULT_WEIGHTS[0]
        z = args.weight_conciseness if args.weight_conciseness is not None else DEFAULT_WEIGHTS[1]
        r = args.weight_correctness if args.weight_correctness is not None else DEFAULT_WEIGHTS[2]
        s = c + z + r
        if s <= 0:
            weights = DEFAULT_WEIGHTS
        else:
            weights = (c / s, z / s, r / s)
    else:
        weights = load_weights_from_env()

    summary_rows: List[Dict[str, Any]] = []

    for filename in sorted(os.listdir(args.submissions_dir)):
        if not filename.lower().endswith(".json"):
            continue
        sub_path = os.path.join(args.submissions_dir, filename)
        try:
            submission = load_submission(sub_path)
        except Exception as exc:
            print(f"Skipping {filename}: failed to load JSON ({exc})", file=sys.stderr)
            continue
        try:
            result = evaluate_submission(
                questions,
                submission,
                use_llm=args.use_llm,
                model=MODEL_NAME,
                workers=args.workers,
                weights=weights,
                sc_runs=args.sc_runs,
            )
        except Exception as exc:
            print(f"Error evaluating {filename}: {exc}", file=sys.stderr)
            continue
        write_results(result, args.out_dir)
        pid = result.get("participant_id") or "unknown"
        for q in result["questions"]:
            eval_data = q["evaluation"]
            summary_rows.append({
                "participant_id": pid,
                "question_id": q["question_id"],
                "completeness": eval_data["completeness"],
                "conciseness": eval_data["conciseness"],
                "correctness": eval_data["correctness"],
                "score": eval_data["score"],
            })
    append_summary(summary_rows, args.out_dir)

    print(f"Evaluation complete. Results written to {args.out_dir}")


if __name__ == "__main__":
    main()