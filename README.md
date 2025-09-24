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
- `server.py` — FastAPI service to accept submissions over HTTP and grade them.
- `ui/index.html` — Minimal drag‑and‑drop web UI that posts submissions to the API.

## Running the Evaluator (CLI)

First, ensure you have Python 3.8 or newer installed.  To evaluate
submissions using the heuristic scorer, run:

```bash
python3 evaluate.py \
    --questions questions.json \
    --submissions_dir submissions \
    --out_dir results
```

To use a large language model for evaluation, set your OpenAI API key in
the environment and pass `--use-llm`:

```bash
export OPENAI_API_KEY=sk-...yourkey...
python3 evaluate.py \
    --questions questions.json \
    --submissions_dir submissions \
    --out_dir results \
    --use-llm \
    --model gpt-3.5-turbo
```

### Parallelization (CLI)

You can process answers concurrently per submission with `--workers N` (default 1):

```bash
python3 evaluate.py ... --workers 6
```

The implementation uses a thread pool and caps concurrency internally to a safe upper bound.

### Weights and Scoring (CLI)

Scores combine three criteria using weights that default to 30% / 20% / 50%:

- **Completeness** (0.3)
- **Conciseness** (0.2)
- **Correctness** (0.5)

You can override weights via CLI (values are normalized to sum to 1):

```bash
python3 evaluate.py ... \
  --weight-completeness 0.3 \
  --weight-conciseness 0.2 \
  --weight-correctness 0.5
```

Alternatively, use environment variables (also normalized):

```bash
export WEIGHT_COMPLETENESS=0.3
export WEIGHT_CONCISENESS=0.2
export WEIGHT_CORRECTNESS=0.5
```

### Self‑Consistency (CLI)

To reduce variance from a single LLM call, you can enable self‑consistency:

- The evaluator runs multiple LLM calls with small prompt variants
- It aggregates the median for each score (completeness/conciseness/correctness)

Enable with:

```bash
python3 evaluate.py ... --use-llm --sc-runs 3
```

You can also set `SELF_CONSISTENCY_RUNS` in the environment.

## API Server (Auto‑Grading)

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
- Results are written to `results/` and `results/summary.csv` by default. Configure with env vars:
  - `QUESTIONS_PATH` (default: `questions.json`)
  - `RESULTS_DIR` (default: `./results`)
  - `OPENAI_MODEL` (default: `gpt-3.5-turbo`)

Server behavior:
- Uses LLM by default (`use_llm=true`); set `OPENAI_API_KEY` on the server.
- Uses a fixed concurrency for grading (default 6 workers). Set `FIXED_WORKERS` env to adjust server‑side.
- Supports self‑consistency via env: `SELF_CONSISTENCY_RUNS` (e.g., 3).
- Supports scoring weights via env: `WEIGHT_COMPLETENESS`, `WEIGHT_CONCISENESS`, `WEIGHT_CORRECTNESS`.

### Deploy on AWS EC2 (quick start)

1. Launch an Ubuntu 22.04/24.04 EC2 instance. Open security group ports 22 (SSH) and 80/443 (HTTP/HTTPS).
2. SSH in and install system deps:
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip nginx
   ```
3. Clone/upload this repo, then inside the project dir:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   export QUESTIONS_PATH=$(pwd)/questions.json
   export RESULTS_DIR=$(pwd)/results
   mkdir -p "$RESULTS_DIR"
   # Required for LLM mode
   export OPENAI_API_KEY=sk-...yourkey...
   ```
4. Run the server via systemd (auto‑restart on boot/crash). Example unit file (`/etc/systemd/system/ecoflex.service`):
   ```ini
   [Unit]
   Description=Ecoflex Grader API
   After=network.target
   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/ecoflex_eval_pipeline
   EnvironmentFile=/etc/ecoflex.env
   ExecStart=/home/ubuntu/ecoflex_eval_pipeline/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
   Restart=always
   RestartSec=3
   [Install]
   WantedBy=multi-user.target
   ```
   Example env file (`/etc/ecoflex.env`):
   ```bash
   QUESTIONS_PATH=/home/ubuntu/ecoflex_eval_pipeline/questions.json
   RESULTS_DIR=/home/ubuntu/ecoflex_eval_pipeline/results
   OPENAI_MODEL=gpt-3.5-turbo
   # Required for LLM
   OPENAI_API_KEY=sk-...yourkey...
   # Scoring weights (normalized)
   WEIGHT_COMPLETENESS=0.3
   WEIGHT_CONCISENESS=0.2
   WEIGHT_CORRECTNESS=0.5
   # Self‑consistency runs
   SELF_CONSISTENCY_RUNS=3
   # Fixed parallel workers
   FIXED_WORKERS=6
   ```
   Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ecoflex
   ```
5. (Optional) Reverse proxy with Nginx on port 80/443 and enable TLS via Certbot. For a temporary DNS, you can use `sslip.io` (e.g., `54-xx-xx-xx-xx.sslip.io`).

## Evaluation & Grading Details

The evaluator produces, for each answer, three criterion scores and an aggregated score:

- **Completeness (0–5)**: coverage of key points from the expected answer.
- **Conciseness (0–5)**: clarity and lack of unnecessary verbosity.
- **Correctness (0–5)**: factual alignment with the expected answer.

The final score is a weighted sum:

- Defaults: completeness 0.3, conciseness 0.2, correctness 0.5 (30% / 20% / 50%).
- Configurable via CLI or environment (normalized automatically).

### Heuristic mode

A lightweight token‑based heuristic computes all three scores without calling the LLM. Useful for testing or when no API key is available.

### LLM mode

- The prompt includes a clear rubric and now also 0/3/5 **calibration anchors** to stabilize the scale.
- Optional **self‑consistency**: the evaluator can call the LLM multiple times with small prompt variations and aggregate the median per criterion to reduce variance from single‑shot runs.
- Temperature is set to 0.0 to minimize randomness.

### Parallelization

- Within a single submission, answers are graded concurrently (thread pool).
- In the API server, a fixed number of workers is used by default (configurable via `FIXED_WORKERS`).
- Be mindful of API provider rate limits when increasing concurrency/self‑consistency runs.

### Outputs

- Per‑participant JSON is saved in `results/{participant_id}.json`.
- `results/summary.csv` aggregates the per‑question scores and final score.

## Submission Format

Participants should submit a JSON file with the following structure:

```json
{
  "participant_id": "TeamName",
  "answers": [
    { "question_id": "Q34", "answer": "..." },
    { "question_id": "Q35", "answer": "..." }
  ]
}
```

Each `question_id` must correspond to an entry in `questions.json`.

## License

This project is provided as is, without warranty of any kind.  Feel
free to modify and reuse it for your hackathon or educational project.