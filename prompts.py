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

Scoring anchors (examples for calibration, integer levels 0–5):
- Completeness (0–5)
  • 0: Mentions almost none of the required points.
  • 1: Mentions a few isolated points; most key elements are missing.
  • 2: Covers some points but misses many essential elements.
  • 3: Covers about half of the key points; notable gaps remain.
  • 4: Covers most key points with minor omissions.
  • 5: Covers essentially all key points with no substantive omissions.
- Conciseness (0–5)
  • 0: Highly verbose or rambling; many irrelevant details.
  • 1: Very wordy; several tangents; hard to follow.
  • 2: Some unnecessary verbosity; could be much tighter.
  • 3: Slightly verbose or repetitive but generally to the point.
  • 4: Clear and mostly compact with minimal extra wording.
  • 5: Very clear and compact; no fluff or redundancy.
- Correctness (0–5)
  • 0: Major factual errors or contradictions with the expected answer.
  • 1: Mostly incorrect; only a few minor facts align.
  • 2: Several inaccuracies; partial alignment with the expected answer.
  • 3: Mostly correct with one or two minor inaccuracies.
  • 4: Correct with only negligible inaccuracies or omissions.
  • 5: Factually accurate and fully aligned with the expected answer.

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


def build_prompt_variant(idx: int, question: str, expected: str, participant: str) -> str:
    """Return a slightly varied prompt to promote self-consistency.

    Variations permute field order and lightly rephrase instructions. All variants
    strictly require numeric 0–5 scores and a flat JSON schema with the exact keys
    completeness, conciseness, correctness, and comment.
    """
    variant = idx % 4
    if variant == 0:
        return (
            build_prompt(question, expected, participant)
        )
    if variant == 1:
        return (
            "Evaluate the answer strictly per the rubric below and return only JSON.\n\n"
            + f"Participant answer: {participant}\n"
            + f"Expected answer: {expected}\n"
            + f"Question: {question}\n\n"
            + "Keys: completeness, conciseness, correctness, comment. Scores must be numeric 0-5."
            + "\nReturn exactly this JSON shape (no extra keys):"
            + "\n{\"completeness\": <number 0-5>, \"conciseness\": <number 0-5>, \"correctness\": <number 0-5>, \"comment\": \"<brief justification>\"}"
            + "\nNo nested objects, no arrays, no code fences, no prose outside the JSON."
        )
    if variant == 2:
        return (
            "You are a careful grader. Score on a 0-5 numeric scale for each criterion and justify briefly.\n\n"
            + f"Question: {question}\n"
            + f"Participant answer: {participant}\n"
            + f"Expected answer: {expected}\n\n"
            + "Return JSON with completeness, conciseness, correctness, comment. Scores must be numbers in [0,5]."
            + "\nFormat (exact keys, no extras):"
            + "\n{\"completeness\": <number 0-5>, \"conciseness\": <number 0-5>, \"correctness\": <number 0-5>, \"comment\": \"<brief justification>\"}"
            + "\nDo not return nested objects like {\"score\":..., \"justification\":...}."
            + "\nDo not include code fences or any text outside the JSON."
        )
    # variant 3
    return (
        "Return JSON only. Consider correctness most important, then completeness, then conciseness.\n\n"
        + f"Expected answer: {expected}\n"
        + f"Question: {question}\n"
        + f"Participant answer: {participant}\n\n"
        + "Fields: completeness, conciseness, correctness, comment. Each score must be numeric 0-5."
        + "\nExact output JSON (no extra keys, no nesting):"
        + "\n{\"completeness\": <number 0-5>, \"conciseness\": <number 0-5>, \"correctness\": <number 0-5>, \"comment\": \"<brief justification>\"}"
        + "\nNo code fences, no prose before/after."
    )