"""
routers/records.py — All student-record-related endpoints.

Adapted from the Guesthouse `routers/bookings.py`:
  Booking            → StudentRecord
  Guest Name         → student_name
  Check-in Date      → test_date
  Room Price         → marks_obtained
  Room assignment    → Grade (auto-computed, not manually set)

Public (no auth):
  POST   /api/records              — add a new student record
  GET    /api/records/analytics    — class-level summary stats

Admin (JWT required):
  GET    /api/records              — list all records (with optional filter)
  GET    /api/records/{doc_id}     — single record detail
  PATCH  /api/records/{doc_id}/status  — mark Reviewed / Archived
  DELETE /api/records/{doc_id}     — hard delete
  POST   /api/records/cleanup      — remove old archived records
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import require_admin
from config import get_settings
from database import (
    create_record, delete_record, get_all_records,
    get_record_by_doc_id, update_record_status,
)
from models import (
    ClassAnalytics, Grade, MessageResponse, RecordStatus,
    StatusUpdate, StudentRecordCreate, StudentRecordResponse,
)
from services.date_utils import now_ist
from services.grade_service import compute_grade, grade_distribution

logger   = logging.getLogger(__name__)
settings = get_settings()
router   = APIRouter(tags=["records"])


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _to_response(r: dict) -> StudentRecordResponse:
    """Convert a raw Firestore dict to a validated StudentRecordResponse."""
    marks     = r.get("marks_obtained", 0.0)
    max_marks = r.get("max_marks", 100.0)
    return StudentRecordResponse(
        fbDocId        = r.get("fbDocId", ""),
        id             = r.get("id", 0),
        student_name   = r.get("student_name", ""),
        test_date      = r.get("test_date", ""),
        marks_obtained = marks,
        subject        = r.get("subject", ""),
        class_name     = r.get("class_name", ""),
        roll_number    = r.get("roll_number", ""),
        max_marks      = max_marks,
        remarks        = r.get("remarks", ""),
        timestamp      = r.get("timestamp", ""),
        status         = r.get("status", RecordStatus.Pending),
        grade          = compute_grade(marks, max_marks),
        notes          = r.get("notes"),
    )


# ══════════════════════════════════════════════════════════════════
#  PUBLIC — ADD A NEW STUDENT RECORD
# ══════════════════════════════════════════════════════════════════

@router.post("/api/records", response_model=StudentRecordResponse, status_code=201)
async def add_record(body: StudentRecordCreate):
    """
    Accept a new student test record from the form.
    Validates, saves to Firestore as Pending, returns the saved document.
    (Analogous to submit_booking in the Guesthouse app.)
    """
    # Validate test date is not more than 1 year in the future
    test_dt = datetime.strptime(body.test_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    max_future = datetime.now(timezone.utc) + timedelta(days=365)
    if test_dt > max_future:
        raise HTTPException(
            status_code=400,
            detail="Test date cannot be more than 1 year in the future"
        )

    numeric_id = body.id or int(datetime.now(timezone.utc).timestamp() * 1000)

    record_data = {
        "id":             numeric_id,
        "student_name":   body.student_name,
        "test_date":      body.test_date,
        "marks_obtained": body.marks_obtained,
        "subject":        body.subject,
        "class_name":     body.class_name,
        "roll_number":    body.roll_number,
        "max_marks":      body.max_marks,
        "remarks":        body.remarks,
        "timestamp":      now_ist(),
        "status":         RecordStatus.Pending,
        "notes":          None,
    }

    doc_id = await create_record(record_data)
    record_data["fbDocId"] = doc_id

    logger.info(
        "New record added: %s — %s on %s (%.1f / %.1f)",
        doc_id, body.student_name, body.test_date,
        body.marks_obtained, body.max_marks
    )
    return _to_response(record_data)


# ══════════════════════════════════════════════════════════════════
#  PUBLIC — CLASS ANALYTICS SUMMARY
# ══════════════════════════════════════════════════════════════════

@router.get("/api/records/analytics", response_model=list[ClassAnalytics])
async def get_analytics(
    class_name: Optional[str] = Query(None),
    subject:    Optional[str] = Query(None),
):
    """
    Return summary analytics grouped by class + subject.
    Optional query params to filter to a specific class / subject.
    (No auth required — teacher-facing dashboard summary.)
    """
    all_records = await get_all_records()

    # Filter by class/subject if provided
    if class_name:
        all_records = [r for r in all_records if r.get("class_name") == class_name]
    if subject:
        all_records = [r for r in all_records if r.get("subject") == subject]

    # Group records by (class_name, subject)
    groups: dict[tuple, list] = {}
    for r in all_records:
        key = (r.get("class_name", ""), r.get("subject", ""))
        groups.setdefault(key, []).append(r)

    results = []
    for (cls, sub), recs in groups.items():
        marks_list = [r.get("marks_obtained", 0.0) for r in recs]
        results.append(ClassAnalytics(
            class_name          = cls,
            subject             = sub,
            total_students      = len(recs),
            average_marks       = round(sum(marks_list) / len(marks_list), 2),
            highest_marks       = max(marks_list),
            lowest_marks        = min(marks_list),
            grade_distribution  = grade_distribution(recs),
        ))

    return results


# ══════════════════════════════════════════════════════════════════
#  ADMIN — LIST ALL RECORDS
# ══════════════════════════════════════════════════════════════════

@router.get("/api/records", response_model=list[StudentRecordResponse])
async def list_records(
    status_filter: Optional[str] = Query(None, alias="status"),
    class_filter:  Optional[str] = Query(None, alias="class"),
    subject_filter: Optional[str] = Query(None, alias="subject"),
    admin: str = Depends(require_admin),
):
    """
    Return all student records, optionally filtered.
    Requires JWT. (Analogous to list_bookings in the Guesthouse app.)
    """
    all_records = await get_all_records()
    if status_filter and status_filter != "all":
        all_records = [r for r in all_records if r.get("status") == status_filter]
    if class_filter:
        all_records = [r for r in all_records if r.get("class_name") == class_filter]
    if subject_filter:
        all_records = [r for r in all_records if r.get("subject") == subject_filter]
    return [_to_response(r) for r in all_records]


# ══════════════════════════════════════════════════════════════════
#  ADMIN — GET SINGLE RECORD
# ══════════════════════════════════════════════════════════════════

@router.get("/api/records/{doc_id}", response_model=StudentRecordResponse)
async def get_record(doc_id: str, admin: str = Depends(require_admin)):
    r = await get_record_by_doc_id(doc_id)
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return _to_response(r)


# ══════════════════════════════════════════════════════════════════
#  ADMIN — UPDATE STATUS (Reviewed / Archived)
# ══════════════════════════════════════════════════════════════════

@router.patch("/api/records/{doc_id}/status", response_model=StudentRecordResponse)
async def update_status(
    doc_id: str,
    body: StatusUpdate,
    admin: str = Depends(require_admin),
):
    """
    Core status-change endpoint.
      Pending  → Reviewed | Archived
      Reviewed → Archived
    (Analogous to update_status in the Guesthouse app.)
    """
    r = await get_record_by_doc_id(doc_id)
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")

    new_status = body.status.value
    await update_record_status(doc_id, new_status, notes=body.notes)

    updated = {**r, "status": new_status}
    if body.notes is not None:
        updated["notes"] = body.notes

    logger.info(
        "Record %s status → %s by admin '%s'",
        doc_id, new_status, admin
    )
    return _to_response({**updated, "fbDocId": doc_id})


# ══════════════════════════════════════════════════════════════════
#  ADMIN — DELETE RECORD
# ══════════════════════════════════════════════════════════════════

@router.delete("/api/records/{doc_id}", response_model=MessageResponse)
async def remove_record(doc_id: str, admin: str = Depends(require_admin)):
    r = await get_record_by_doc_id(doc_id)
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    await delete_record(doc_id)
    logger.info("Record %s deleted by admin '%s'", doc_id, admin)
    return MessageResponse(message="Record deleted", detail=doc_id)


# ══════════════════════════════════════════════════════════════════
#  ADMIN — AUTO-CLEANUP (old archived records)
# ══════════════════════════════════════════════════════════════════

@router.post("/api/records/cleanup", response_model=MessageResponse)
async def cleanup_old_records(admin: str = Depends(require_admin)):
    """
    Delete Archived records whose test_date is more than CLEANUP_DAYS ago.
    (Analogous to cleanup_old_bookings in the Guesthouse app.)
    """
    all_records = await get_all_records()
    cutoff      = datetime.now(timezone.utc) - timedelta(days=settings.CLEANUP_DAYS)
    cutoff_str  = cutoff.strftime("%Y-%m-%d")

    removed = 0
    for r in all_records:
        if r.get("status") == "Pending":
            continue   # never auto-remove Pending records
        if r.get("test_date", "9999-99-99") < cutoff_str:
            await delete_record(r["fbDocId"])
            removed += 1

    logger.info("Cleanup: removed %d stale record(s)", removed)
    return MessageResponse(
        message=f"Cleanup complete — {removed} record(s) removed",
        detail=f"Cutoff: {cutoff_str}",
    )
