import json
import os

import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def init_app():
    if not firebase_admin._apps:
        key_val = os.environ["FIREBASE_SERVICE_ACCOUNT_KEY"]
        # Cloud platforms pass the JSON content as a string; locally it's a file path
        try:
            cred = credentials.Certificate(json.loads(key_val))
        except (json.JSONDecodeError, ValueError):
            cred = credentials.Certificate(key_val)

        options = {}
        # Strip whitespace and gs:// prefix — common copy-paste artifacts
        bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "").strip().removeprefix("gs://")
        if bucket:
            options["storageBucket"] = bucket
            print(f"[firebase] storageBucket: {bucket}")
        else:
            print("[firebase] WARNING: FIREBASE_STORAGE_BUCKET not set")
        firebase_admin.initialize_app(cred, options)


def get_db():
    global _db
    if _db is None:
        init_app()
        _db = firestore.client()
    return _db
