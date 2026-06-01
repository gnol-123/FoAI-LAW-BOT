from firebase_admin import firestore as fs
from .firebase_init import get_db


def _messages_ref(user_id: str, session_id: str):
    return (
        get_db()
        .collection("users").document(user_id)
        .collection("chatSessions").document(session_id)
        .collection("messages")
    )


def add_message(
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    sources: list | None = None,
) -> dict:
    ref = _messages_ref(user_id, session_id).document()
    data = {
        "role": role,          # "user" | "assistant"
        "content": content,
        "timestamp": fs.SERVER_TIMESTAMP,
        "sources": sources or [],
    }
    ref.set(data)
    return {"messageId": ref.id, "role": role, "content": content, "sources": sources or []}


def _serialize(data: dict) -> dict:
    return {
        k: v.isoformat() if hasattr(v, "isoformat") else v
        for k, v in data.items()
    }


def get_messages(user_id: str, session_id: str) -> list[dict]:
    docs = _messages_ref(user_id, session_id).order_by("timestamp").stream()
    return [{"messageId": d.id, **_serialize(d.to_dict())} for d in docs]
