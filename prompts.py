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
Evaluate each response according to three independent criteria, scored on a 
scale from 0 to 5, where 0 is worst and 5 is best:

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
"""

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

    All variants include the full rubric with scoring anchors, treat criteria neutrally,
    use a consistent field order (Question → Expected → Participant), and enforce strict
    flat JSON output. Only the intro phrasing is lightly varied to reduce prompt overfitting.
    """
    # Shared JSON output instruction (adds format enforcement to the rubric)
    json_format = (
        "\nFormat: Return ONLY a flat JSON object with exactly these keys:\n"
        '{"completeness": <number 0-5>, "conciseness": <number 0-5>, "correctness": <number 0-5>, "comment": "<brief text>"}\n'
        "Do NOT include code fences, nested objects, extra keys, or any text outside the JSON."
    )

    # Consistent field order for all variants
    fields_block = (
        f"\nQuestion: {question}\n"
        f"Expected answer: {expected}\n"
        f"Participant answer: {participant}"
    )

    variant = idx % 4
    if variant == 0:
        # Baseline: full rubric, neutral tone
        return (
            "You are an impartial evaluator grading hackathon answers.\n"
            + f"{RUBRIC}{fields_block}{json_format}"
        )
    
    if variant == 1:
        # Slightly rephrased intro, same rubric
        return (
            "You are an impartial evaluator. Apply the rubric below strictly.\n"
            + f"{RUBRIC}{fields_block}{json_format}"
        )
    
    if variant == 2:
        # Emphasize calibration anchors, same rubric
        return (
            "You are a careful grader. Use the scoring anchors in the rubric to assign precise scores.\n"
            + f"{RUBRIC}{fields_block}{json_format}"
        )
    
    # variant 3: neutral phrasing, same rubric
    return (
        "You are evaluating a hackathon answer. Follow the rubric to score each criterion independently.\n"
        + f"{RUBRIC}{fields_block}{json_format}"
    )