from firebase_admin import firestore as fs
from .firebase_init import get_db


def create_user(user_id: str, username: str, email: str, plan: str = "free") -> dict:
    data = {
        "username": username,
        "email": email,
        "plan": plan,
        "createdAt": fs.SERVER_TIMESTAMP,
    }
    get_db().collection("users").document(user_id).set(data)
    return {"userId": user_id, **data}


def get_user(user_id: str) -> dict | None:
    doc = get_db().collection("users").document(user_id).get()
    return doc.to_dict() if doc.exists else None


def update_user(user_id: str, fields: dict) -> None:
    get_db().collection("users").document(user_id).update(fields)
