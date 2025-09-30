import os
from typing import List, Dict


def write_summary_csv(csv_path: str, rows: List[Dict[str, object]]) -> None:
    """Write summary CSV with a canonical field order.

    Fields: participant_id, question_id, completeness, conciseness, correctness, score
    """
    from csv import DictWriter

    fieldnames = [
        "participant_id",
        "question_id",
        "completeness",
        "conciseness",
        "correctness",
        "score",
    ]

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fieldnames})


