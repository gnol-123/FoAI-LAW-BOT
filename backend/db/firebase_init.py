import os
import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def get_db():
    global _db
    if _db is None:
        if not firebase_admin._apps:
            key_path = os.environ["FIREBASE_SERVICE_ACCOUNT_KEY"]
            firebase_admin.initialize_app(credentials.Certificate(key_path))
        _db = firestore.client()
    return _db
