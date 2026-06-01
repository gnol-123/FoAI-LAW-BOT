"""
Uploads a downloaded PDF to Firebase Cloud Storage under the legislation/ prefix.
"""

import logging
import os
import re
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, storage

log = logging.getLogger(__name__)

_initialized = False


def _init() -> None:
    global _initialized
    if _initialized or firebase_admin._apps:
        _initialized = True
        return
    key_path = os.environ["FIREBASE_SERVICE_ACCOUNT_KEY"]
    bucket_name = os.environ["FIREBASE_STORAGE_BUCKET"]
    firebase_admin.initialize_app(
        credentials.Certificate(key_path),
        {"storageBucket": bucket_name},
    )
    _initialized = True
    log.info("Firebase app initialised")


def _slugify(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


def upload_pdf(local_path: Path, act_name: str) -> str:
    """
    Upload a PDF to Firebase Storage at legislation/{slug}/{filename}.
    Returns the blob path (e.g. "legislation/fair_work_act_2009/FairWork.pdf").
    Skips the upload if the blob already exists and has the same size.
    """
    _init()
    bucket = storage.bucket()
    slug = _slugify(act_name)
    blob_name = f"uploads/legislation/{slug}/{local_path.name}"
    blob = bucket.blob(blob_name)

    # Skip if already uploaded with the same size (idempotent re-runs)
    blob.reload() if blob.exists() else None
    if blob.exists() and blob.size == local_path.stat().st_size:
        log.info(f"Already up-to-date in Storage — skipping: {blob_name}")
        return blob_name

    log.info(f"Uploading {local_path.name} → gs://{bucket.name}/{blob_name}")
    blob.upload_from_filename(str(local_path), content_type="application/pdf")
    log.info(f"Upload complete ({local_path.stat().st_size / 1024:.0f} KB): {blob_name}")
    return blob_name
