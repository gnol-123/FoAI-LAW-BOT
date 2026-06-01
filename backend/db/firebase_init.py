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
        bucket = os.environ.get("FIREBASE_STORAGE_BUCKET")
        if bucket:
            options["storageBucket"] = bucket
        firebase_admin.initialize_app(cred, options)


def get_db():
    global _db
    if _db is None:
        init_app()
        _db = firestore.client()
    return _db
