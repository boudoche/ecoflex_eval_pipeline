# Ecoflex Hackathon Evaluation Pipeline

This repository contains a simple evaluation pipeline for scoring hackathon
responses using either a large language model (LLM) or a heuristic fallback.
The code was designed for the GreenHorizon Ecoflex hackathon but can be
adapted to other scenarios with minimal changes.

## Contents

- `prompts.py` — Defines the rubric and helper functions for building
  prompts and parsing LLM responses.
- `evaluate.py` — Command‐line script to evaluate participant submissions
  against a set of questions.  Supports LLM and heuristic modes.
- `questions.json` — A sample dataset with 40 questions and expected
  answers.
- `submissions/` — Example submission files.  The `team42.json` file
  demonstrates the expected submission format.
- `results/` — When you run the evaluator, results and a summary CSV
  will be saved here (you must create this directory or specify
  another path).

## Running the Evaluator

First, ensure you have Python 3.8 or newer installed.  To evaluate
submissions using the heuristic scorer, run:

```bash
python3 evaluate.py \
    --questions questions.json \
    --submissions_dir submissions \
    --out_dir results
```

The script will produce a `results` directory containing one JSON file per
participant and a `summary.csv` summarising the scores for each question.

### Using the OpenAI API

To use a large language model for evaluation, set your OpenAI API key in
the environment:

```bash
export OPENAI_API_KEY=sk-...yourkey...
```

Then add the `--use-llm` flag when running the script:

```bash
python3 evaluate.py \
    --questions questions.json \
    --submissions_dir submissions \
    --out_dir results \
    --use-llm \
    --model gpt-3.5-turbo
```

LLM responses are parsed according to the rubric defined in
`prompts.py`.  To reduce variability, the evaluator uses temperature 0
by default.

## Submission Format

Participants should submit a JSON file with the following structure:

```json
{
  "participant_id": "TeamName",
  "answers": [
    { "question_id": "Q34", "answer": "..." },
    { "question_id": "Q35", "answer": "..." },
    ...
  ]
}
```

Each `question_id` must correspond to an entry in `questions.json`.

## Scoring

By default, scores are computed as a weighted average of the three
criteria returned by the evaluator:

- **Completeness** (30%)
- **Conciseness** (20%)
- **Correctness** (50%)

If you wish to adjust these weights, edit the `weighted_score` function
in `evaluate.py`.

## API Server (Auto-Grading)

A lightweight FastAPI server is provided in `server.py` to accept HTTP submissions and grade them automatically.

### Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run locally

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

- Health check: `GET /health`
- Grade one submission: `POST /grade` with JSON body `{ "participant_id": "Team42", "answers": [ {"question_id": "Q1", "answer": "..."} ] }`
- Optional query params: `use_llm` (bool), `model` (str), `write_files` (bool)
- Results are written to `results/` and `results/summary.csv` by default. Configure with env vars:
  - `QUESTIONS_PATH` (default: `questions.json`)
  - `RESULTS_DIR` (default: `./results`)
  - `OPENAI_MODEL` (default: `gpt-3.5-turbo`)

### Deploy on AWS EC2 (quick start)

1. Launch an Ubuntu 22.04 EC2 instance. Open security group ports 22 and 80 (and 443 if using TLS).
2. SSH in and install system deps:
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip nginx
   ```
3. Clone or upload this repo to the instance, then inside the project dir:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   export QUESTIONS_PATH=$(pwd)/questions.json
   export RESULTS_DIR=$(pwd)/results
   mkdir -p "$RESULTS_DIR"
   # Optional for LLM mode
   # export OPENAI_API_KEY=sk-...yourkey...
   ```
4. Run the server with a production ASGI server via systemd + Uvicorn workers:
   ```bash
   pip install uvicorn[standard]
   nohup uvicorn server:app --host 0.0.0.0 --port 8000 &
   ```
5. (Optional) Reverse proxy with Nginx:
   - Create `/etc/nginx/sites-available/ecoflex` with a server block proxying to `127.0.0.1:8000`, enable it, then `sudo nginx -t && sudo systemctl reload nginx`.

For durable process management, replace `nohup` with a `systemd` service or `pm2`/`supervisord`.

## License

This project is provided as is, without warranty of any kind.  Feel
free to modify and reuse it for your hackathon or educational project.