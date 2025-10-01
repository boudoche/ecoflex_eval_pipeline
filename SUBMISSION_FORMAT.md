## Submission JSON format

Your file must be a JSON object with two keys:

- `participant_id`: your team name
- `answers`: an array of objects `{ "question_id": string, "answer": string }`

Example:

```json
{
  "participant_id": "DemoTeam",
  "answers": [
    { "question_id": "Q1", "answer": "..." },
    { "question_id": "Q2", "answer": "..." }
  ]
}
```

Valid `question_id` values are defined in `questions.json` (e.g., `Q1`, `Q2`, ...).

## How to submit via the web UI

1. Open the submission page hosted on the server:
   - `https://<your-domain-or-sslip-io>/ui/`
2. Enter your team token in the token field (required):
   - Header sent is `X-Submission-Token: <your_token>`
3. Drag and drop your JSON file into the drop area, or click to browse.
4. Click Submit. You will see a minimal success message if accepted.
5. The server will grade your submission and send an email confirmation.


## Sample file

See `sssample_submission.json` for a ready-to-use example.

