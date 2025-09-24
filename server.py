import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from evaluate import (
    load_questions,
    evaluate_submission,
    write_results,
)


QUESTIONS_PATH = os.getenv("QUESTIONS_PATH", os.path.join(os.path.dirname(__file__), "questions.json"))
RESULTS_DIR = os.getenv("RESULTS_DIR", os.path.join(os.path.dirname(__file__), "results"))
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
# Fixed number of parallel workers for grading
FIXED_WORKERS = int(os.getenv("FIXED_WORKERS", "6"))

app = FastAPI(title="Ecoflex Auto Grader", version="1.0.0")

# Allow CORS for simple integration/testing; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static UI
ui_dir = os.path.join(os.path.dirname(__file__), "ui")
if os.path.isdir(ui_dir):
    app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")

@app.get("/")
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui/")

# In-memory state
_state: Dict[str, Any] = {
    "questions": {},
}


def _ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


@app.on_event("startup")
async def startup_event() -> None:
    _ensure_results_dir()
    try:
        _state["questions"] = load_questions(QUESTIONS_PATH)
    except Exception as exc:
        # Fail fast if questions are unavailable
        raise RuntimeError(f"Failed to load questions from {QUESTIONS_PATH}: {exc}")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/reload-questions")
async def reload_questions() -> Dict[str, str]:
    try:
        _state["questions"] = load_questions(QUESTIONS_PATH)
        return {"status": "reloaded"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to reload questions: {exc}")


@app.post("/grade")
async def grade_submission(
    submission: Dict[str, Any],
    use_llm: bool = Query(True, description="Use OpenAI LLM instead of heuristics"),
    model: str = Query(DEFAULT_MODEL, description="OpenAI model name when use_llm=true"),
    write_files: bool = Query(True, description="Write JSON and update summary.csv on disk"),
) -> Dict[str, Any]:
    """
    Accept a single submission JSON and return graded results.

    Expected payload format:
    {
      "participant_id": "TeamName",
      "answers": [ {"question_id": "Q1", "answer": "..."}, ... ]
    }
    """
    questions = _state.get("questions") or {}
    if not questions:
        raise HTTPException(status_code=500, detail="Questions not loaded")

    try:
        result = evaluate_submission(
            questions,
            submission,
            use_llm=use_llm,
            model=model,
            workers=FIXED_WORKERS,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if write_files:
        try:
            write_results(result, RESULTS_DIR)
            # Also append/update summary.csv: re-generate for this single result
            from csv import DictWriter
            csv_path = os.path.join(RESULTS_DIR, "summary.csv")
            fieldnames = [
                "participant_id",
                "question_id",
                "completeness",
                "conciseness",
                "correctness",
                "score",
            ]
            rows: List[Dict[str, Any]] = []
            pid = result.get("participant_id") or "unknown"
            for q in result.get("questions", []):
                eval_data = q["evaluation"]
                rows.append(
                    {
                        "participant_id": pid,
                        "question_id": q["question_id"],
                        "completeness": eval_data["completeness"],
                        "conciseness": eval_data["conciseness"],
                        "correctness": eval_data["correctness"],
                        "score": eval_data["score"],
                    }
                )
            # Overwrite per-request, simple behavior; for multi-tenant use, consider append with dedup
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)
        except Exception as exc:
            # Do not fail the API if disk write fails
            raise HTTPException(status_code=500, detail=f"Failed to write results: {exc}")

    return result


# Optional: batch grading endpoint
@app.post("/grade-batch")
async def grade_batch(
    submissions: List[Dict[str, Any]],
    use_llm: bool = Query(True),
    model: str = Query(DEFAULT_MODEL),
    write_files: bool = Query(True),
) -> Dict[str, Any]:
    questions = _state.get("questions") or {}
    if not questions:
        raise HTTPException(status_code=500, detail="Questions not loaded")

    results: List[Dict[str, Any]] = []
    from csv import DictWriter

    if write_files:
        _ensure_results_dir()
        csv_path = os.path.join(RESULTS_DIR, "summary.csv")
        fieldnames = [
            "participant_id",
            "question_id",
            "completeness",
            "conciseness",
            "correctness",
            "score",
        ]
        # Rebuild summary from this batch only
        all_rows: List[Dict[str, Any]] = []

    for submission in submissions:
        try:
            result = evaluate_submission(
                questions,
                submission,
                use_llm=use_llm,
                model=model,
                workers=FIXED_WORKERS,
            )
            results.append(result)
        except Exception as exc:
            # Include error per submission
            results.append({"participant_id": submission.get("participant_id", "unknown"), "error": str(exc)})
            continue

        if write_files:
            try:
                write_results(result, RESULTS_DIR)
                pid = result.get("participant_id") or "unknown"
                for q in result.get("questions", []):
                    eval_data = q["evaluation"]
                    all_rows.append(
                        {
                            "participant_id": pid,
                            "question_id": q["question_id"],
                            "completeness": eval_data["completeness"],
                            "conciseness": eval_data["conciseness"],
                            "correctness": eval_data["correctness"],
                            "score": eval_data["score"],
                        }
                    )
            except Exception as exc:
                results.append({"participant_id": pid, "error": f"Failed to write results: {exc}"})

    if write_files:
        try:
            with open(os.path.join(RESULTS_DIR, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
                writer = DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                for r in all_rows:
                    writer.writerow(r)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to write summary: {exc}")

    return {"results": results}
