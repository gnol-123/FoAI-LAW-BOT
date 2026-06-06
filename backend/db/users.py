from datetime import datetime, timezone, timedelta

from firebase_admin import firestore as fs
from .firebase_init import get_db

TOKEN_LIMIT  = 100_000
WINDOW_HOURS = 10


# ── Token tracking helpers ─────────────────────────────────────────────────────

def _compute_status(window: dict) -> dict:
    start_iso = window.get("start")
    used      = window.get("used", 0)

    if start_iso:
        start_dt = datetime.fromisoformat(start_iso)
        if datetime.now(timezone.utc) >= start_dt + timedelta(hours=WINDOW_HOURS):
            used, start_iso = 0, None   # window expired

    resets_at = None
    if start_iso:
        start_dt  = datetime.fromisoformat(start_iso)
        resets_at = (start_dt + timedelta(hours=WINDOW_HOURS)).isoformat()

    return {
        "used":        used,
        "remaining":   max(0, TOKEN_LIMIT - used),
        "limit":       TOKEN_LIMIT,
        "windowHours": WINDOW_HOURS,
        "resetsAt":    resets_at,
    }


def get_token_status(user_id: str) -> dict:
    doc  = get_db().collection("users").document(user_id).get()
    data = doc.to_dict() if doc.exists else {}
    return _compute_status(data.get("tokenWindow", {}))


def record_token_usage(user_id: str, tokens: int) -> dict:
    """Add *tokens* to the user's current window and return updated status."""
    ref  = get_db().collection("users").document(user_id)
    doc  = ref.get()
    data = doc.to_dict() if doc.exists else {}
    win  = data.get("tokenWindow", {})

    now_iso  = datetime.now(timezone.utc).isoformat()
    start    = win.get("start")
    used     = win.get("used", 0)

    if start:
        start_dt = datetime.fromisoformat(start)
        if datetime.now(timezone.utc) >= start_dt + timedelta(hours=WINDOW_HOURS):
            start, used = now_iso, 0    # new window
    else:
        start = now_iso

    new_used = used + tokens
    ref.update({"tokenWindow": {"start": start, "used": new_used}})
    return _compute_status({"start": start, "used": new_used})


def create_user(user_id: str, username: str, email: str, plan: str = "free") -> dict:
    ref = get_db().collection("users").document(user_id)
    if ref.get().exists:
        raise ValueError("already_exists")
    data = {
        "username": username,
        "email": email,
        "plan": plan,
        "createdAt": fs.SERVER_TIMESTAMP,
    }
    ref.set(data)
    return {"userId": user_id, "username": username, "email": email, "plan": plan}


def get_user(user_id: str) -> dict | None:
    doc = get_db().collection("users").document(user_id).get()
    return doc.to_dict() if doc.exists else None


def update_user(user_id: str, fields: dict) -> None:
    get_db().collection("users").document(user_id).update(fields)
