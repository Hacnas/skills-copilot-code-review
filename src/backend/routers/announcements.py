"""
Announcements endpoints for Mergington High School API

Provides public listing of active announcements and authenticated CRUD for teachers.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"],
)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        # Accept ISO strings; also accept 'YYYY-MM-DDTHH:MM' from datetime-local inputs
        # If string lacks seconds/zone, fromisoformat will still parse
        return datetime.fromisoformat(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}")


@router.get("/active", response_model=List[Dict[str, Any]])
@router.get("/active/", response_model=List[Dict[str, Any]])
def get_active_announcements(now: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Return announcements that are currently active based on start/end dates.

    - now: optional ISO datetime to evaluate against (defaults to current UTC time).
    """
    reference = datetime.fromisoformat(now) if now else datetime.utcnow()

    query = {
        "$and": [
            {"end_date": {"$gte": reference}},
            {"$or": [
                {"start_date": {"$lte": reference}},
                {"start_date": {"$exists": False}},
                {"start_date": None},
            ]},
        ]
    }

    results: List[Dict[str, Any]] = []
    for ann in announcements_collection.find(query).sort("end_date", 1):
        doc = {**ann}
        doc["id"] = str(doc.pop("_id"))
        results.append(_serialize_dates(doc))
    return results


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def list_announcements() -> List[Dict[str, Any]]:
    """List all announcements (admin view)."""
    results: List[Dict[str, Any]] = []
    for ann in announcements_collection.find().sort("end_date", -1):
        doc = {**ann}
        doc["id"] = str(doc.pop("_id"))
        results.append(_serialize_dates(doc))
    return results


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    end_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Create a new announcement (requires teacher authentication)."""
    _require_teacher(teacher_username)

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    end_dt = _parse_datetime(end_date)
    if end_dt is None:
        raise HTTPException(status_code=400, detail="end_date is required")

    start_dt = _parse_datetime(start_date)

    now = datetime.utcnow()
    doc = {
        "message": message.strip(),
        "start_date": start_dt,
        "end_date": end_dt,
        "created_at": now,
        "updated_at": now,
    }

    result = announcements_collection.insert_one(doc)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    out = {**created}
    out["id"] = str(out.pop("_id"))
    return _serialize_dates(out)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: Optional[str] = None,
    end_date: Optional[str] = None,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Update an announcement (requires teacher authentication)."""
    _require_teacher(teacher_username)

    update: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    if message is not None:
        if not message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        update["message"] = message.strip()
    if start_date is not None:
        update["start_date"] = _parse_datetime(start_date)
    if end_date is not None:
        end_dt = _parse_datetime(end_date)
        if end_dt is None:
            raise HTTPException(status_code=400, detail="end_date cannot be null")
        update["end_date"] = end_dt

    res = announcements_collection.update_one({"_id": _to_object_id(announcement_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    doc = announcements_collection.find_one({"_id": _to_object_id(announcement_id)})
    out = {**doc}
    out["id"] = str(out.pop("_id"))
    return _serialize_dates(out)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Delete an announcement (requires teacher authentication)."""
    _require_teacher(teacher_username)

    res = announcements_collection.delete_one({"_id": _to_object_id(announcement_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted"}


# Helpers
from bson import ObjectId  # type: ignore

def _to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")


def _require_teacher(username: Optional[str]) -> None:
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")


def _serialize_dates(doc: Dict[str, Any]) -> Dict[str, Any]:
    # Convert datetime fields to ISO strings for JSON
    for key in ["start_date", "end_date", "created_at", "updated_at"]:
        if key in doc and isinstance(doc[key], datetime):
            doc[key] = doc[key].isoformat()
    return doc
