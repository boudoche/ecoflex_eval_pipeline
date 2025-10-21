import os
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import FastAPI, HTTPException, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from evaluate import (
    load_questions,
    evaluate_submission,
    write_results,
)
from reporting import write_summary_csv

import asyncio
from concurrent.futures import ThreadPoolExecutor

QUESTIONS_PATH = os.getenv("QUESTIONS_PATH", os.path.join(os.path.dirname(__file__), "questions.json"))
RESULTS_DIR = os.getenv("RESULTS_DIR", os.path.join(os.path.dirname(__file__), "results"))
# Fixed OpenAI model
DEFAULT_MODEL = "gpt-4o-mini"
# Fixed number of parallel workers for grading
FIXED_WORKERS = int(os.getenv("FIXED_WORKERS", "6"))
# Token sources
TOKENS_PATH = os.getenv("TOKENS_PATH", os.path.join(os.path.dirname(__file__), "tokens.json"))
TEAM_TOKENS = os.getenv("TEAM_TOKENS", "")  # format: token:Team[:email],token:Team[:email]
# Max submission size (in bytes, default 5MB)
MAX_SUBMISSION_SIZE = int(os.getenv("MAX_SUBMISSION_SIZE", str(5 * 1024 * 1024)))

# Logging configuration (includes filename and line number)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s [%(process)d] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S.%f%z",
)
logger = logging.getLogger("ecoflex")

app = FastAPI(title="Ecoflex Auto Grader", version="1.3.3")

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
    "token_to_info": {},  # token -> {team:str, email:str, used:bool}
    "executor": None,
}


def _ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _load_tokens() -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    # From env: token:Team[:email]
    env_value = os.getenv("TEAM_TOKENS", TEAM_TOKENS)
    if env_value:
        parts = [p.strip() for p in env_value.split(",") if p.strip()]
        for part in parts:
            fields = part.split(":")
            if len(fields) >= 2:
                token = fields[0].strip()
                team = fields[1].strip()
                email = fields[2].strip() if len(fields) >= 3 else ""
                if token:
                    result[token] = {"team": team, "email": email, "used": False}
    # From file: either {token: team} or {token: {team, email, used}}
    path_value = os.getenv("TOKENS_PATH", TOKENS_PATH)
    if os.path.isfile(path_value):
        try:
            with open(path_value, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for token, val in data.items():
                    if not isinstance(token, str):
                        continue
                    if isinstance(val, str):
                        result[token] = {"team": val, "email": result.get(token, {}).get("email", ""), "used": False}
                    elif isinstance(val, dict):
                        team = str(val.get("team", result.get(token, {}).get("team", "")))
                        email = str(val.get("email", result.get(token, {}).get("email", "")))
                        used = bool(val.get("used", False))
                        if team:
                            result[token] = {"team": team, "email": email, "used": used}
        except Exception:
            pass
    return result


def _persist_tokens(mapping: Dict[str, Dict[str, Any]]) -> None:
    path_value = os.getenv("TOKENS_PATH", TOKENS_PATH)
    if not path_value:
        return
    # Only persist if a path is provided; write full mapping
    try:
        os.makedirs(os.path.dirname(path_value) or ".", exist_ok=True)
        with open(path_value, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception:
        logger.exception("Failed to persist tokens file at %s", path_value)


def _require_token_and_team(x_submission_token: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    if not x_submission_token:
        raise HTTPException(status_code=401, detail="Missing submission token")
    info = _state["token_to_info"].get(x_submission_token)
    if not info or not info.get("team"):
        raise HTTPException(status_code=401, detail="Invalid submission token")
    # Enforce one submission per token
    if bool(info.get("used", False)):
        raise HTTPException(status_code=409, detail="Submission already received for this token")
    return x_submission_token, info


def _send_confirmation_email(to_addr: str, participant_id: str, submission_json: Dict[str, Any]) -> None:
    if not to_addr:
        return
    if os.getenv("EMAIL_ENABLED", "").lower() not in ("1", "true", "yes", "on"):
        return
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", user)
    from_name = os.getenv("SMTP_FROM_NAME", "Argusa Data Challenge")
    reply_to = os.getenv("SMTP_REPLY_TO", from_addr)
    use_ssl = os.getenv("SMTP_USE_SSL", "").lower() in ("1", "true", "yes", "on")
    if not host or not from_addr:
        logger.warning("Email disabled: SMTP_HOST/SMTP_FROM not configured")
        return
    
    # Build email with proper headers to avoid spam
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_addr
    msg["Reply-To"] = reply_to
    msg["Subject"] = f"✓ Submission Received - {participant_id}"
    
    # Add additional headers to improve deliverability
    msg["X-Mailer"] = "Ecoflex Auto Grader"
    msg["X-Priority"] = "3"  # Normal priority
    msg["Importance"] = "Normal"
    
    # Create a more professional email body (plain text + HTML)
    text_body = f"""Hello {participant_id},

Your submission has been received successfully!

Submission Details:
- Team/Participant: {participant_id}
- Number of answers: {len(submission_json.get('answers', []))}
- Status: Received

Your submission file is attached to this email for your records.

We will notify you once the evaluation is complete.

Best regards,
The Argusa Data Challenge Team

---
This is an automated message. Please do not reply to this email.
"""
    
    # Get logo URL from environment (optional)
    logo_url = os.getenv("EMAIL_LOGO_URL", "")
    
    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff; }}
        .header {{ 
            background: linear-gradient(135deg, #004B87 0%, #004B87 25%, #FDB913 25%, #FDB913 50%, #000000 50%, #000000 75%, #E94E1B 75%, #E94E1B 100%);
            color: white; 
            padding: 30px 20px; 
            text-align: center; 
            border-radius: 5px 5px 0 0;
        }}
        .logo {{ max-width: 200px; height: auto; margin-bottom: 15px; }}
        .header h1 {{ margin: 0; font-size: 24px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }}
        .content {{ background-color: #f9f9f9; padding: 30px 20px; border: 1px solid #ddd; }}
        .details {{ 
            background-color: white; 
            padding: 20px; 
            margin: 20px 0; 
            border-left: 5px solid #004B87;
            border-radius: 3px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .details h3 {{ color: #004B87; margin-top: 0; }}
        .details ul {{ list-style: none; padding: 0; }}
        .details li {{ padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
        .details li:last-child {{ border-bottom: none; }}
        .footer {{ 
            text-align: center; 
            margin-top: 20px; 
            padding: 20px;
            font-size: 12px; 
            color: #666;
            background-color: #f5f5f5;
            border-radius: 0 0 5px 5px;
        }}
        .success {{ color: #004B87; font-weight: bold; font-size: 18px; }}
        .brand-bar {{
            height: 8px;
            background: linear-gradient(90deg, #004B87 0%, #004B87 25%, #FDB913 25%, #FDB913 50%, #000000 50%, #000000 75%, #E94E1B 75%, #E94E1B 100%);
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            {"<img src='" + logo_url + "' alt='Argusa Logo' class='logo' />" if logo_url else ""}
            <h1>✓ Submission Received</h1>
        </div>
        <div class="brand-bar"></div>
        <div class="content">
            <p>Hello <strong>{participant_id}</strong>,</p>
            
            <p class="success">Your submission has been received successfully!</p>
            
            <div class="details">
                <h3>Submission Details</h3>
                <ul>
                    <li><strong>Team/Participant:</strong> {participant_id}</li>
                    <li><strong>Number of answers:</strong> {len(submission_json.get('answers', []))}</li>
                    <li><strong>Status:</strong> Received</li>
                </ul>
            </div>
            
            <p>Your submission file is attached to this email for your records.</p>
            
            <p>We will notify you once the evaluation is complete.</p>
            
            <p>Best regards,<br>
            <strong>The Argusa Data Challenge Team</strong></p>
        </div>
        <div class="footer">
            <div class="brand-bar" style="margin-bottom: 10px;"></div>
            <p>This is an automated message. Please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""
    
    # Set both plain text and HTML versions
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    
    # Attach submission JSON
    payload = json.dumps(submission_json, indent=2, ensure_ascii=False).encode("utf-8")
    msg.add_attachment(payload, maintype="application", subtype="json", filename=f"{participant_id}_submission.json")
    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as s:
                if user and password:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                try:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                except Exception:
                    pass
                if user and password:
                    s.login(user, password)
                s.send_message(msg)
        logger.info("Sent confirmation email to %s", to_addr)
    except Exception as exc:
        logger.exception("Failed to send confirmation email to %s: %s", to_addr, exc)


@app.on_event("startup")
async def startup_event() -> None:
    _ensure_results_dir()
    try:
        _state["questions"] = load_questions(QUESTIONS_PATH)
    except Exception as exc:
        logger.exception("Failed to load questions from %s", QUESTIONS_PATH)
        raise RuntimeError(f"Failed to load questions from {QUESTIONS_PATH}: {exc}")
    _state["token_to_info"] = _load_tokens()
    # ThreadPool for running CPU/IO bound grading off the event loop
    max_threads = max(4, FIXED_WORKERS)
    _state["executor"] = ThreadPoolExecutor(max_workers=max_threads)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    executor = _state.get("executor")
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/reload-questions")
async def reload_questions() -> Dict[str, str]:
    try:
        _state["questions"] = load_questions(QUESTIONS_PATH)
        return {"status": "reloaded"}
    except Exception as exc:
        logger.exception("Failed to reload questions")
        raise HTTPException(status_code=400, detail=f"Failed to reload questions: {exc}")


@app.post("/reload-tokens")
async def reload_tokens() -> Dict[str, int]:
    mapping = _load_tokens()
    _state["token_to_info"] = mapping
    return {"loaded": len(mapping)}


async def _run_in_executor(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    executor = _state.get("executor")
    return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))


def _coerce_submission_shape(obj: Any) -> Dict[str, Any]:
    # If the payload is a bare list, assume it's the answers array
    if isinstance(obj, list):
        return {"answers": obj}
    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail="Invalid submission payload; expected JSON object or array")
    # Accept common alternative keys
    if "answers" not in obj:
        if "items" in obj and isinstance(obj["items"], list):
            obj = {**obj, "answers": obj["items"]}
        elif "data" in obj and isinstance(obj["data"], list):
            obj = {**obj, "answers": obj["data"]}
    answers = obj.get("answers")
    if not isinstance(answers, list) or len(answers) == 0:
        raise HTTPException(status_code=400, detail="No answers provided; expected non-empty 'answers' array")
    return obj


def _write_team_xlsx(results_dir: str, participant_id: str, questions: List[Dict[str, Any]]) -> None:
    logger.debug("Preparing XLSX for participant=%s in dir=%s", participant_id, results_dir)
    try:
        from openpyxl import Workbook
    except Exception as exc:
        logger.warning("openpyxl not available, skipping XLSX for %s: %s", participant_id, exc)
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    # Layout: for each question, reserve 8 rows (4 variants per model × 2 models)
    # First columns per question on the first row: Qid, submitted answer, correct answers, final score, inconsistent
    # Next 8 rows (one per variant): correctness, conciseness, completeness, score, comment
    from openpyxl.styles import PatternFill
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

    # Write a header block legend at the top
    ws.append(["Qid", "submitted answer", "correct answers", "final score", "inconsistent", "suspicious",
               "variant model", "variant correctness", "variant conciseness", "variant completeness", "variant score", "variant comment"]) 
    for col in range(1, 13):
        try:
            ws.column_dimensions[chr(64 + col)].width = 24 if col in (2,3,12) else 18
        except Exception:
            pass

    # Collect all final scores for summary calculation
    all_final_scores = []

    for q in questions:
        qid = q.get("question_id")
        submitted = q.get("submitted_answer", "")
        eval_data = q.get("evaluation", {})
        final_score = eval_data.get("score")
        inconsistent = bool(eval_data.get("inconsistent", False))
        # Build main prompt info: include the question text and expected answer
        expected_text = ""
        try:
            qinfo = _state.get("questions", {}).get(qid, {})
            qtext = qinfo.get("question", "")
            exp = qinfo.get("expected_answer", "")
            if qtext or exp:
                expected_text = f"Question: {qtext}\nExpected: {exp}"
        except Exception:
            expected_text = ""
        # Write the question summary row
        suspicious = bool(eval_data.get("needs_manual_review", False))
        ws.append([qid, submitted, expected_text, final_score, inconsistent, suspicious, None, None, None, None, None, None])
        if inconsistent:
            ws.cell(row=ws.max_row, column=1).fill = red_fill
        if suspicious:
            ws.cell(row=ws.max_row, column=1).fill = yellow_fill
        
        # Collect final score for summary
        if final_score is not None:
            all_final_scores.append(float(final_score))

        # Variants
        v_scores = eval_data.get("variant_scores", []) or []
        v_comments = eval_data.get("variant_comments", []) or []
        v_weighted = eval_data.get("variant_weighted", []) or []
        # Ensure 8 rows (4 variants per model × 2 models)
        max_rows = 8
        for i in range(max_rows):
            if i < len(v_scores):
                v = v_scores[i]
                comment = v_comments[i] if i < len(v_comments) else ""
                w = v_weighted[i] if i < len(v_weighted) else None
                model_name = v.get("model", "unknown")
                ws.append([None, None, None, None, None, None, model_name, v.get("correctness"), v.get("conciseness"), v.get("completeness"), w, comment])
            else:
                ws.append([None]*12)
    
    # Add summary section at the end
    if all_final_scores:
        # Add empty row for separation
        ws.append([None]*12)
        
        # Calculate statistics
        total_score = sum(all_final_scores)
        average_score = total_score / len(all_final_scores)
        
        # Add summary rows with bold styling
        from openpyxl.styles import Font
        bold_font = Font(bold=True, size=12)
        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        
        # Total sum row
        ws.append(["TOTAL SCORE", None, None, round(total_score, 2), None, None, None, None, None, None, None, None])
        ws.cell(row=ws.max_row, column=1).font = bold_font
        ws.cell(row=ws.max_row, column=1).fill = green_fill
        ws.cell(row=ws.max_row, column=4).font = bold_font
        ws.cell(row=ws.max_row, column=4).fill = green_fill
        
        # Average score row
        ws.append(["AVERAGE SCORE", None, None, round(average_score, 2), None, None, None, None, None, None, None, None])
        ws.cell(row=ws.max_row, column=1).font = bold_font
        ws.cell(row=ws.max_row, column=1).fill = green_fill
        ws.cell(row=ws.max_row, column=4).font = bold_font
        ws.cell(row=ws.max_row, column=4).fill = green_fill
        
        # Number of questions
        ws.append(["NUMBER OF QUESTIONS", None, None, len(all_final_scores), None, None, None, None, None, None, None, None])
        ws.cell(row=ws.max_row, column=1).font = bold_font
        ws.cell(row=ws.max_row, column=4).font = bold_font
    
    # Column widths already set in header block above; no further header-based sizing here
    os.makedirs(results_dir, exist_ok=True)
    xlsx_path = os.path.abspath(os.path.join(results_dir, f"{participant_id}.xlsx"))
    try:
        wb.save(xlsx_path)
        logger.info("Wrote XLSX: %s", xlsx_path)
    except Exception as exc:
        logger.exception("Failed to write XLSX %s: %s", xlsx_path, exc)


@app.post("/grade")
async def grade_submission(
    request: Request,
    use_llm: bool = Query(True, description="Use OpenAI LLM instead of heuristics"),
    write_files: bool = Query(True, description="Write JSON and update summary.csv on disk"),
    x_submission_token: Optional[str] = Header(None, alias="X-Submission-Token"),
) -> Dict[str, Any]:
    # Check content length FIRST before any other processing
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_SUBMISSION_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Submission too large. Maximum size: {MAX_SUBMISSION_SIZE / (1024*1024):.1f}MB"
        )

    token, info = _require_token_and_team(x_submission_token)
    team = info.get("team", "unknown")

    questions = _state.get("questions") or {}
    if not questions:
        raise HTTPException(status_code=500, detail="Questions not loaded")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    sub = _coerce_submission_shape(body)
    sub = dict(sub)
    sub["participant_id"] = team

    if use_llm and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=400, detail="Missing OPENAI_API_KEY on server. Set it or call with use_llm=false.")

    try:
        result = await _run_in_executor(
            evaluate_submission,
            questions,
            sub,
            use_llm,
            DEFAULT_MODEL,
            FIXED_WORKERS,
            None,
            int(os.getenv("SELF_CONSISTENCY_RUNS", "3")),
            True,  # dual_model=True
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Grading failed for team %s (single)", team)
        raise HTTPException(status_code=400, detail=str(exc))

    if write_files:
        try:
            await _run_in_executor(write_results, result, RESULTS_DIR)
            csv_path = os.path.join(RESULTS_DIR, "summary.csv")
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
            # Write CSV using shared helper on executor
            await _run_in_executor(write_summary_csv, csv_path, rows)
            # Also write XLSX per participant
            await _run_in_executor(_write_team_xlsx, RESULTS_DIR, pid, result.get("questions", []))
            # Mark token as used and persist
            info["used"] = True
            _state["token_to_info"][token] = info
            _persist_tokens(_state["token_to_info"])
            # Send confirmation email AFTER all processing is complete (best-effort)
            try:
                _send_confirmation_email(info.get("email", ""), team, sub)
            except Exception:
                logger.exception("Email confirmation failed for team %s", team)
        except Exception as exc:
            logger.exception("Failed to write results for participant %s", pid)
            raise HTTPException(status_code=500, detail=f"Failed to write results: {exc}")

    return result


@app.post("/grade-batch")
async def grade_batch(
    request: Request,
    use_llm: bool = Query(True),
    write_files: bool = Query(True),
    x_submission_token: Optional[str] = Header(None, alias="X-Submission-Token"),
) -> Dict[str, Any]:
    # Check content length FIRST before any other processing
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_SUBMISSION_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Submission too large. Maximum size: {MAX_SUBMISSION_SIZE / (1024*1024):.1f}MB"
        )

    token, info = _require_token_and_team(x_submission_token)
    team = info.get("team", "unknown")

    questions = _state.get("questions") or {}
    if not questions:
        raise HTTPException(status_code=500, detail="Questions not loaded")

    try:
        items = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Batch body must be a JSON array of submissions")

    results: List[Dict[str, Any]] = []

    if write_files:
        _ensure_results_dir()
        csv_path = os.path.join(RESULTS_DIR, "summary.csv")
        all_rows: List[Dict[str, Any]] = []

    for item in items:
        try:
            sub = _coerce_submission_shape(item)
        except HTTPException as he:
            logger.error("Invalid submission shape: %s", he.detail)
            results.append({"error": he.detail})
            continue
        sub = dict(sub)
        sub["participant_id"] = team
        if use_llm and not os.getenv("OPENAI_API_KEY"):
            results.append({"participant_id": sub.get("participant_id", "unknown"), "error": "Missing OPENAI_API_KEY on server. Set it or call with use_llm=false."})
            continue
        try:
            result = await _run_in_executor(
                evaluate_submission,
                questions,
                sub,
                use_llm,
                DEFAULT_MODEL,
                FIXED_WORKERS,
                None,
                int(os.getenv("SELF_CONSISTENCY_RUNS", "3")),
                True,  # dual_model=True
            )
            results.append(result)
        except Exception as exc:
            logger.exception("Grading failed for team %s (batch)", team)
            results.append({"participant_id": sub.get("participant_id", "unknown"), "error": str(exc)})
            continue

        if write_files:
            try:
                await _run_in_executor(write_results, result, RESULTS_DIR)
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
                # Also write XLSX per participant
                await _run_in_executor(_write_team_xlsx, RESULTS_DIR, pid, result.get("questions", []))
            except Exception as exc:
                logger.exception("Failed to write results for participant %s (batch)", pid)
                results.append({"participant_id": pid, "error": f"Failed to write results: {exc}"})

    if write_files:
        try:
            await _run_in_executor(write_summary_csv, csv_path, all_rows)
            # After batch, mark token used and persist
            info["used"] = True
            _state["token_to_info"][token] = info
            _persist_tokens(_state["token_to_info"])
            # Send confirmation email AFTER all processing is complete (best-effort)
            try:
                _send_confirmation_email(info.get("email", ""), team, {"submissions": items})
            except Exception:
                logger.exception("Email confirmation failed for team %s (batch)", team)
        except Exception as exc:
            logger.exception("Failed to write summary CSV")
            raise HTTPException(status_code=500, detail=f"Failed to write summary: {exc}")

    return {"results": results}
