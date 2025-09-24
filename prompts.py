"""Utilities for building prompts and parsing responses for the Ecoflex evaluation pipeline.

This module defines a rubric and helper functions used to construct prompts
for large language models (LLMs) when scoring hackathon responses. It also
includes a simple parser for extracting JSON objects from LLM outputs.
"""

import json
from typing import Any, Dict

# The rubric used to instruct the LLM on how to score answers.  Feel free to
# modify or extend this string to refine the evaluation criteria.  The LLM
# should output a JSON object with the keys "completeness", "conciseness",
# "correctness", and "comment".
RUBRIC = """
You are an impartial evaluator grading hackathon answers.  Each response is
evaluated according to three independent criteria, scored on a scale from 0
to 5, where 0 is worst and 5 is best:

• Completeness: Does the participant's answer include all important points
  present in the expected answer?  Penalise missing information.

• Conciseness: Is the participant's answer clear and succinct?  Penalise
  unnecessary verbosity and tangents.  Answers shorter than or equal in
  length to the expected answer should generally receive higher scores.

• Correctness: Are the facts in the participant's answer correct relative to
  the expected answer?  Penalise incorrect statements and hallucinations.

Scoring anchors (examples for calibration):
- Completeness (0 / 3 / 5)
  • 0: Mentions almost none of the required points.
  • 3: Covers about half of the key points; notable gaps remain.
  • 5: Covers essentially all key points with no substantive omissions.
- Conciseness (0 / 3 / 5)
  • 0: Highly verbose or rambling; includes lots of irrelevant details.
  • 3: Some extra wording, minor repetition, but generally to the point.
  • 5: Clear, compact phrasing without fluff or redundancy.
- Correctness (0 / 3 / 5)
  • 0: Contains major factual errors or contradicts the expected answer.
  • 3: Mostly correct with one or two minor inaccuracies.
  • 5: Factually accurate and aligned with the expected answer.

You MUST return your evaluation as a JSON object with exactly the keys
"completeness", "conciseness", "correctness", and "comment".  The values of
"completeness", "conciseness", and "correctness" must be numbers between 0
and 5 (inclusive).  The "comment" field should contain a brief one- or two-
sentence justification for the scores.
"""

def build_prompt(question: str, expected_answer: str, participant_answer: str) -> str:
    """Construct a prompt to send to an LLM for evaluating a single answer.

    Parameters
    ----------
    question : str
        The question being asked.
    expected_answer : str
        The canonical or reference answer that contains all required
        information.
    participant_answer : str
        The answer provided by the participant.

    Returns
    -------
    str
        A formatted prompt combining the rubric and the specific question
        context.  The prompt instructs the LLM to provide a JSON-formatted
        evaluation.
    """
    return (
        f"{RUBRIC}\n\n"
        f"Question: {question}\n"
        f"Expected answer: {expected_answer}\n"
        f"Participant answer: {participant_answer}\n\n"
        "Return your evaluation strictly as a JSON object with keys "
        "\"completeness\", \"conciseness\", \"correctness\", and \"comment\"."
    )


def parse_response(response: str) -> Dict[str, Any]:
    """Parse a JSON object from an LLM's raw text response.

    LLMs sometimes return additional text before or after the JSON payload,
    or wrap the JSON in code fences.  This helper attempts to extract the
    JSON substring and parse it into a Python dictionary.

    Parameters
    ----------
    response : str
        The raw text returned by the LLM.

    Returns
    -------
    dict
        The parsed JSON object.

    Raises
    ------
    ValueError
        If no valid JSON object can be found in the response.
    """
    response = response.strip()
    # Try to parse the entire response first
    try:
        return json.loads(response)
    except Exception:
        pass

    # Remove code fences if present (e.g. ```json ... ```)
    if response.startswith("```"):
        # Find the first opening brace after the code fence
        idx = response.find("{", response.find("```"))
    else:
        idx = response.find("{")
    if idx != -1:
        end_idx = response.rfind("}")
        if end_idx != -1 and end_idx > idx:
            json_str = response[idx : end_idx + 1]
            try:
                return json.loads(json_str)
            except Exception:
                pass
    # As a last resort, scan for first and last braces and attempt to parse
    braces = [i for i, ch in enumerate(response) if ch in "{}"]
    if braces:
        start = braces[0]
        end = braces[-1]
        try:
            return json.loads(response[start : end + 1])
        except Exception:
            pass
    raise ValueError("No valid JSON object found in response")