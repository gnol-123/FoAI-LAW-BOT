from firebase_admin import firestore as fs
from .firebase_init import get_db


def _serialize(data: dict) -> dict:
    return {
        k: v.isoformat() if hasattr(v, "isoformat") else v
        for k, v in data.items()
    }


def create_document(doc_id: str, filename: str, uploaded_by: str, storage_path: str) -> dict:
    data = {
        "filename": filename,
        "uploadedBy": uploaded_by,
        "uploadedAt": fs.SERVER_TIMESTAMP,
        "storagePath": storage_path,
        "status": "processing",
        "chunkCount": 0,
    }
    get_db().collection("documents").document(doc_id).set(data)
    return {"documentId": doc_id, "filename": filename, "status": "processing", "chunkCount": 0}


def update_document(doc_id: str, fields: dict) -> None:
    get_db().collection("documents").document(doc_id).update(fields)


def get_document(doc_id: str) -> dict | None:
    doc = get_db().collection("documents").document(doc_id).get()
    return {"documentId": doc.id, **_serialize(doc.to_dict())} if doc.exists else None


def list_documents() -> list[dict]:
    docs = (
        get_db().collection("documents")
        .order_by("uploadedAt", direction=fs.Query.DESCENDING)
        .stream()
    )
    return [{"documentId": d.id, **_serialize(d.to_dict())} for d in docs]


def delete_document(doc_id: str) -> None:
    get_db().collection("documents").document(doc_id).delete()
