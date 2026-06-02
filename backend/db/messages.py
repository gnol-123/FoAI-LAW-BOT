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
    attachment_text: str = "",
    attachment_name: str = "",
) -> dict:
    ref = _messages_ref(user_id, session_id).document()
    data = {
        "role": role,          # "user" | "assistant"
        "content": content,
        "timestamp": fs.SERVER_TIMESTAMP,
        "sources": sources or [],
    }
    # Store attachment on the message so the LLM can reference it in future turns.
    # attachmentText is kept server-side only; the API strips it before returning
    # to the frontend (50k chars is too large to send back on every history load).
    if attachment_text:
        data["attachmentText"] = attachment_text
        data["attachmentName"] = attachment_name
    ref.set(data)
    return {
        "messageId":    ref.id,
        "role":         role,
        "content":      content,
        "sources":      sources or [],
        **({"attachmentName": attachment_name} if attachment_name else {}),
    }


def _serialize(data: dict) -> dict:
    return {
        k: v.isoformat() if hasattr(v, "isoformat") else v
        for k, v in data.items()
    }


def get_messages(
    user_id: str,
    session_id: str,
    include_attachments: bool = True,
) -> list[dict]:
    """
    Return a session's messages ordered by time.

    include_attachments=False projects out the heavy `attachmentText` field
    (up to 50k chars per message) at the Firestore level so it is never read
    or transferred. The chat endpoint needs the text to rebuild LLM context,
    but the frontend message-list endpoint does not — there it's pure waste.
    """
    query = _messages_ref(user_id, session_id).order_by("timestamp")
    if not include_attachments:
        query = query.select(["role", "content", "timestamp", "sources", "attachmentName"])
    docs = query.stream()
    return [{"messageId": d.id, **_serialize(d.to_dict())} for d in docs]
