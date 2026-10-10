from uuid import uuid4
from ..models.case import utc_now


def notify(db, user_id, message, case_id=None, kind="UPDATE"):
    if user_id:
        db.create("notifications", {"id": uuid4().hex, "user_id": user_id, "case_id": case_id, "kind": kind, "message": message, "created_at": utc_now(), "read_at": None})
