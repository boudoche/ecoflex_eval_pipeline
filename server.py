import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, Header
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
# Fixed OpenAI model
DEFAULT_MODEL = "gpt-4o-mini"
# Fixed number of parallel workers for grading
FIXED_WORKERS = int(os.getenv("FIXED_WORKERS", "6"))
# Token sources
TOKENS_PATH = os.getenv("TOKENS_PATH", os.path.join(os.path.dirname(__file__), "tokens.json"))
TEAM_TOKENS = os.getenv("TEAM_TOKENS", "")  # format: token1:TeamA,token2:TeamB

app = FastAPI(title="Ecoflex Auto Grader", version="1.2.0")

# Allow CORS for simple integration/testing; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
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
    "token_to_team": {},
}


def _ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _load_tokens() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    env_value = os.getenv("TEAM_TOKENS", TEAM_TOKENS)
    if env_value:
        parts = [p.strip() for p in env_value.split(",") if p.strip()]
        for part in parts:
            if ":" in part:
                token, team = part.split(":", 1)
                token = token.strip()
                team = team.strip()
                if token:
                    mapping[token] = team
    path_value = os.getenv("TOKENS_PATH", TOKENS_PATH)
    if os.path.isfile(path_value):
        try:
            import json
            with open(path_value, "r", encoding="utf-8") as f:
                data = json.load(f)
            for token, team in data.items():
                if isinstance(token, str) and isinstance(team, str):
                    mapping[token] = team
        except Exception:
            pass
    return mapping


def _require_token_and_team(x_submission_token: Optional[str]) -> Tuple[str, str]:
    if not x_submission_token:
        raise HTTPException(status_code=401, detail="Missing submission token")
    team = _state["token_to_team"].get(x_submission_token)
    if not team:
        raise HTTPException(status_code=401, detail="Invalid submission token")
    return x_submission_token, team


@app.on_event("startup")
async def startup_event() -> None:
    _ensure_results_dir()
    try:
        _state["questions"] = load_questions(QUESTIONS_PATH)
    except Exception as exc:
        raise RuntimeError(f"Failed to load questions from {QUESTIONS_PATH}: {exc}")
    _state["token_to_team"] = _load_tokens()


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


@app.post("/reload-tokens")
async def reload_tokens() -> Dict[str, int]:
    mapping = _load_tokens()
    _state["token_to_team"] = mapping
    return {"loaded": len(mapping)}


@app.post("/grade")
async def grade_submission(
    submission: Dict[str, Any],
    use_llm: bool = Query(True, description="Use OpenAI LLM instead of heuristics"),
    write_files: bool = Query(True, description="Write JSON and update summary.csv on disk"),
    x_submission_token: Optional[str] = Header(None, alias="X-Submission-Token"),
) -> Dict[str, Any]:
    _, team = _require_token_and_team(x_submission_token)

    questions = _state.get("questions") or {}
    if not questions:
        raise HTTPException(status_code=500, detail="Questions not loaded")

    submission = dict(submission)
    submission["participant_id"] = team

    try:
        result = evaluate_submission(
            questions,
            submission,
            use_llm=use_llm,
            model=DEFAULT_MODEL,
            workers=FIXED_WORKERS,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if write_files:
        try:
            write_results(result, RESULTS_DIR)
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
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to write results: {exc}")

    return result


@app.post("/grade-batch")
async def grade_batch(
    submissions: List[Dict[str, Any]],
    use_llm: bool = Query(True),
    write_files: bool = Query(True),
    x_submission_token: Optional[str] = Header(None, alias="X-Submission-Token"),
) -> Dict[str, Any]:
    _, team = _require_token_and_team(x_submission_token)

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
        all_rows: List[Dict[str, Any]] = []

    for submission in submissions:
        sub = dict(submission)
        sub["participant_id"] = team
        try:
            result = evaluate_submission(
                questions,
                sub,
                use_llm=use_llm,
                model=DEFAULT_MODEL,
                workers=FIXED_WORKERS,
            )
            results.append(result)
        except Exception as exc:
            results.append({"participant_id": sub.get("participant_id", "unknown"), "error": str(exc)})
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
