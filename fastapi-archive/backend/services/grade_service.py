"""
services/grade_service.py — Grade band calculation for TutorTrack AI.

Replaces the Guesthouse room_service.py — instead of checking room
availability, this service computes grade bands from marks_obtained.

Grade scale (out of max_marks):
  90–100 %  → Outstanding
  75–89  %  → Excellent
  60–74  %  → Good
  40–59  %  → Average
   0–39  %  → Needs Work
"""
from models import Grade


def compute_grade(marks_obtained: float, max_marks: float = 100.0) -> Grade:
    """
    Return the Grade enum value for the given marks.

    Args:
        marks_obtained: raw marks (e.g. 78.5)
        max_marks:      maximum possible marks (default 100)
    """
    if max_marks <= 0:
        return Grade.NeedsWork
    pct = (marks_obtained / max_marks) * 100
    if pct >= 90:
        return Grade.Outstanding
    if pct >= 75:
        return Grade.Excellent
    if pct >= 60:
        return Grade.Good
    if pct >= 40:
        return Grade.Average
    return Grade.NeedsWork


def grade_distribution(records: list[dict]) -> dict:
    """
    Given a list of student record dicts, return a count of each grade.
    Each dict must have 'marks_obtained' and 'max_marks' keys.
    """
    dist: dict[str, int] = {g.value: 0 for g in Grade}
    for r in records:
        g = compute_grade(r.get("marks_obtained", 0), r.get("max_marks", 100))
        dist[g.value] += 1
    return dist
