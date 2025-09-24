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
from typing import Dict, Any, List

from prompts import build_prompt, parse_response

# Only import openai if needed; otherwise it's optional for heuristic mode.
try:
    import openai  # type: ignore
except ImportError:
    openai = None  # type: ignore


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


def llm_evaluate(question: str, expected: str, answer: str, model: str = "gpt-3.5-turbo") -> Dict[str, Any]:
    """Call an OpenAI LLM to score a single answer.

    This function builds a prompt using the rubric and sends it to the
    specified model.  It then parses the JSON result.  You must set
    OPENAI_API_KEY in the environment for openai to work.

    Parameters
    ----------
    question : str
        The question text.
    expected : str
        The expected answer text.
    answer : str
        The participant's answer text.
    model : str, optional
        The OpenAI model name.  Defaults to "gpt-3.5-turbo".

    Returns
    -------
    dict
        The parsed evaluation with keys "completeness", "conciseness",
        "correctness", and "comment".

    Raises
    ------
    RuntimeError
        If the OpenAI module is not installed or the API key is missing.
    """
    if openai is None:
        raise RuntimeError("openai module is not installed; install openai or use heuristic mode")
    # Build prompt
    prompt = build_prompt(question, expected, answer)
    # Call the API
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
    except Exception as e:
        raise RuntimeError(f"OpenAI API request failed: {e}")
    # Extract the assistant's message
    content = response["choices"][0]["message"]["content"]
    return parse_response(content)


def weighted_score(evaluation: Dict[str, float]) -> float:
    """Compute a weighted score from the individual criteria.

    The default weights are: completeness 30%, conciseness 20%, correctness
    50%.  The result is rounded to two decimal places.

    Parameters
    ----------
    evaluation : dict
        A dict with keys "completeness", "conciseness", "correctness".

    Returns
    -------
    float
        The weighted score between 0 and 5.
    """
    cpl = evaluation["completeness"]
    ccs = evaluation["conciseness"]
    crt = evaluation["correctness"]
    score = (1/3) * cpl + (1/3) * ccs + (1/3) * crt
    return round(score, 2)


def evaluate_submission(
    questions: Dict[str, Dict[str, str]],
    submission: Dict[str, Any],
    use_llm: bool = False,
    model: str = "gpt-4o-mini"
) -> Dict[str, Any]:
    """Evaluate all answers from a single participant submission.

    Parameters
    ----------
    questions : dict
        Mapping from question IDs to question text and expected answer.
    submission : dict
        Participant submission loaded from JSON.
    use_llm : bool, optional
        Whether to use an LLM instead of heuristic scoring.  Defaults to False.
    model : str, optional
        The OpenAI model to use when calling the LLM.  Defaults to "gpt-3.5-turbo".

    Returns
    -------
    dict
        A results dictionary including the participant_id and a list of
        evaluations per question.
    """
    participant_id = submission.get("participant_id") or "unknown"
    results = {
        "participant_id": participant_id,
        "questions": [],
    }
    for answer in submission.get("answers", []):
        qid = answer.get("question_id")
        ans_text = answer.get("answer", "")
        if qid not in questions:
            raise KeyError(f"Question ID '{qid}' not found in questions file")
        q_info = questions[qid]
        q_text = q_info["question"]
        expected = q_info["expected_answer"]
        if use_llm:
            evaluation = llm_evaluate(q_text, expected, ans_text, model=model)
        else:
            evaluation = heuristic_evaluate(expected, ans_text)
        evaluation["score"] = weighted_score(evaluation)
        results["questions"].append({
            "question_id": qid,
            "evaluation": evaluation,
        })
    return results


def write_results(results: Dict[str, Any], out_dir: str) -> None:
    """Write a participant's evaluation results to a JSON file.

    The filename is based on the participant_id.

    Parameters
    ----------
    results : dict
        The evaluation results for a single participant.
    out_dir : str
        Directory in which to write the JSON file.
    """
    pid = results.get("participant_id") or "unknown"
    out_path = os.path.join(out_dir, f"{pid}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def append_summary(summary_rows: List[Dict[str, Any]], out_dir: str) -> None:
    """Write the summary CSV file for all participants.

    Parameters
    ----------
    summary_rows : list of dict
        Each dict contains participant_id, question_id, and scores.
    out_dir : str
        Directory in which to write the summary CSV.
    """
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
    parser.add_argument("--model", default="gpt-3.5-turbo", help="Model name to use when calling the LLM")
    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs(args.out_dir, exist_ok=True)

    # Load questions
    try:
        questions = load_questions(args.questions)
    except Exception as exc:
        print(f"Error loading questions: {exc}", file=sys.stderr)
        sys.exit(1)

    summary_rows: List[Dict[str, Any]] = []

    # Iterate over submissions
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
            result = evaluate_submission(questions, submission, use_llm=args.use_llm, model=args.model)
        except Exception as exc:
            print(f"Error evaluating {filename}: {exc}", file=sys.stderr)
            continue
        write_results(result, args.out_dir)
        # Build summary rows
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
    # Write summary CSV
    append_summary(summary_rows, args.out_dir)

    print(f"Evaluation complete. Results written to {args.out_dir}")


if __name__ == "__main__":
    main()