from firebase_admin import firestore as fs
from .firebase_init import get_db


def _sessions_ref(user_id: str):
    return get_db().collection("users").document(user_id).collection("chatSessions")


def create_session(
    user_id: str,
    title: str,
    jurisdiction: str = "",
    practice_area: str = "",
) -> dict:
    ref = _sessions_ref(user_id).document()
    data = {
        "title": title,
        "createdAt": fs.SERVER_TIMESTAMP,
        "updatedAt": fs.SERVER_TIMESTAMP,
        "metadata": {
            "documentIds": [],
            "jurisdiction": jurisdiction,
            "practiceArea": practice_area,
        },
    }
    ref.set(data)
    return {"sessionId": ref.id, **data}


def get_session(user_id: str, session_id: str) -> dict | None:
    doc = _sessions_ref(user_id).document(session_id).get()
    return doc.to_dict() if doc.exists else None


def list_sessions(user_id: str) -> list[dict]:
    docs = (
        _sessions_ref(user_id)
        .order_by("updatedAt", direction=fs.Query.DESCENDING)
        .stream()
    )
    return [{"sessionId": d.id, **d.to_dict()} for d in docs]


def update_session(user_id: str, session_id: str, fields: dict) -> None:
    fields["updatedAt"] = fs.SERVER_TIMESTAMP
    _sessions_ref(user_id).document(session_id).update(fields)


def delete_session(user_id: str, session_id: str) -> None:
    _sessions_ref(user_id).document(session_id).delete()
