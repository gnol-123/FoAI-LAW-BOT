import os
import uuid
from functools import wraps

from dotenv import load_dotenv
from firebase_admin import auth
from flask import Flask, g, jsonify, request
from flask_cors import CORS

from agent import chain as agent
from db import chat_sessions, messages, users
from db import documents as documents_db
from db.firebase_init import init_app

load_dotenv()
init_app()

app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# Startup: sync unprocessed PDFs from Firebase Storage → Pinecone + Whoosh
# ---------------------------------------------------------------------------

def _rag_ready() -> bool:
    key = os.environ.get("PINECONE_API_KEY", "")
    return bool(key) and key != "your-pinecone-api-key-here"


def sync_from_storage() -> None:
    """Download any unprocessed PDFs from Firebase Storage and index them."""
    if not os.environ.get("FIREBASE_STORAGE_BUCKET"):
        print("[sync] FIREBASE_STORAGE_BUCKET not set — skipping")
        return
    if not _rag_ready():
        print("[sync] PINECONE_API_KEY not set or is placeholder — skipping")
        return

    try:
        from firebase_admin import storage as fb_storage
        from rag.ingest import ingest_pdf

        bucket = fb_storage.bucket()

        # Scan all prefixes where the scraper may have uploaded PDFs
        prefixes = ["uploads/", "legislation/"]
        blobs = []
        for prefix in prefixes:
            blobs.extend(bucket.list_blobs(prefix=prefix))

        pdf_blobs = [b for b in blobs if b.name.lower().endswith(".pdf")]
        print(f"[sync] found {len(pdf_blobs)} PDF(s) in Storage across prefixes: {prefixes}")

        if not pdf_blobs:
            print("[sync] nothing to index")
            return

        existing = {d["storagePath"]: d for d in documents_db.list_documents()}

        for blob in pdf_blobs:
            doc_meta = existing.get(blob.name)
            if doc_meta and doc_meta.get("status") == "ready":
                print(f"[sync] already indexed — skipping: {blob.name}")
                continue

            filename = blob.name.rsplit("/", 1)[-1]
            doc_id   = (doc_meta or {}).get("documentId") or str(uuid.uuid4())
            print(f"[sync] indexing {filename} ({blob.name}) …")

            if not doc_meta:
                documents_db.create_document(doc_id, filename, "sync", blob.name)

            try:
                chunk_count = ingest_pdf(blob.download_as_bytes(), doc_id, filename)
                documents_db.update_document(doc_id, {"status": "ready", "chunkCount": chunk_count})
                print(f"[sync] ✓ {filename} — {chunk_count} chunks embedded")
            except Exception as exc:
                documents_db.update_document(doc_id, {"status": "error", "error": str(exc)})
                print(f"[sync] ✗ {filename} failed: {exc}")

    except Exception as exc:
        import traceback
        print(f"[sync] ERROR: {exc}")
        traceback.print_exc()


sync_from_storage()


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header.removeprefix("Bearer ").strip()
        if not token:
            return jsonify({"error": "Missing Authorization header"}), 401
        try:
            g.user = auth.verify_id_token(token)
        except auth.InvalidIdTokenError:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# User routes
# ---------------------------------------------------------------------------

@app.post("/users")
@require_auth
def create_user():
    uid = g.user["uid"]
    body = request.get_json(force=True)
    try:
        user = users.create_user(
            user_id=uid,
            username=body["username"],
            email=body["email"],
            plan=body.get("plan", "free"),
        )
        return jsonify(user), 201
    except ValueError:
        return jsonify({"error": "already_exists"}), 409


@app.get("/users/me")
@require_auth
def get_me():
    user = users.get_user(g.user["uid"])
    if user is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)


# ---------------------------------------------------------------------------
# Chat session routes
# ---------------------------------------------------------------------------

@app.get("/sessions")
@require_auth
def list_sessions():
    return jsonify(chat_sessions.list_sessions(g.user["uid"]))


@app.post("/sessions")
@require_auth
def create_session():
    body = request.get_json(force=True)
    session = chat_sessions.create_session(
        user_id=g.user["uid"],
        title=body.get("title", "New conversation"),
        jurisdiction=body.get("jurisdiction", ""),
        practice_area=body.get("practiceArea", ""),
    )
    return jsonify(session), 201


@app.get("/sessions/<session_id>")
@require_auth
def get_session(session_id):
    session = chat_sessions.get_session(g.user["uid"], session_id)
    if session is None:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


@app.delete("/sessions/<session_id>")
@require_auth
def delete_session(session_id):
    chat_sessions.delete_session(g.user["uid"], session_id)
    return "", 204


@app.patch("/sessions/<session_id>")
@require_auth
def rename_session(session_id):
    body = request.get_json(force=True)
    title = body.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    chat_sessions.update_session(g.user["uid"], session_id, {"title": title})
    return jsonify({"title": title})


# ---------------------------------------------------------------------------
# Message routes
# ---------------------------------------------------------------------------

@app.get("/sessions/<session_id>/messages")
@require_auth
def get_messages(session_id):
    return jsonify(messages.get_messages(g.user["uid"], session_id))


@app.post("/sessions/<session_id>/messages")
@require_auth
def add_message(session_id):
    body = request.get_json(force=True)
    message = messages.add_message(
        user_id=g.user["uid"],
        session_id=session_id,
        role=body["role"],
        content=body["content"],
        sources=body.get("sources"),
    )
    return jsonify(message), 201


# ---------------------------------------------------------------------------
# Chat (agent + RAG)
# ---------------------------------------------------------------------------

@app.post("/sessions/<session_id>/chat")
@require_auth
def chat(session_id):
    body = request.get_json(force=True)
    question = body.get("message", "").strip()
    if not question:
        return jsonify({"error": "message is required"}), 400

    uid = g.user["uid"]

    # ── Token limit pre-check ──────────────────────────────────────────────
    token_status = users.get_token_status(uid)
    if token_status["remaining"] <= 0:
        return jsonify({
            "error": "token_limit_reached",
            "message": "You have used your 10,000-token allowance for this 10-hour window.",
            "resetsAt": token_status["resetsAt"],
        }), 429

    prior = messages.get_messages(uid, session_id)
    history = [{"role": m["role"], "content": m["content"]} for m in prior]

    messages.add_message(uid, session_id, role="user", content=question)

    # Query expansion + hybrid RRF retrieval
    context_chunks = []
    if _rag_ready():
        try:
            from rag.query_expansion import expand
            from rag.hybrid_retriever import retrieve
            queries = expand(question)
            app.logger.info(f"[rag] queries: {queries}")
            context_chunks = retrieve(queries)
        except Exception as exc:
            app.logger.warning(f"[rag] skipped: {exc}")

    thinking, answer, sources, tokens_used = agent.run(
        question=question,
        history=history,
        context_chunks=context_chunks,
    )

    # ── Record actual token usage ──────────────────────────────────────────
    token_status = users.record_token_usage(uid, tokens_used)
    app.logger.info(f"[tokens] {uid}: +{tokens_used} → {token_status['used']}/{token_status['limit']}")

    formatted_sources = [
        {
            "documentId":     c["documentId"],
            "excerpt":        c["text"][:200],
            "relevanceScore": c["score"],
            "citation":       f"{c['filename']}, p.{c['pageNumber']}",
        }
        for c in sources
    ]

    saved = messages.add_message(
        uid, session_id,
        role="assistant",
        content=answer,
        sources=formatted_sources,
    )

    new_title = None
    if not prior:
        try:
            new_title = agent.generate_title(question)
        except Exception:
            pass

    chat_sessions.update_session(uid, session_id, {"title": new_title} if new_title else {})

    return jsonify({
        "messageId":   saved["messageId"],
        "content":     answer,
        "thinking":    thinking,
        "sources":     formatted_sources,
        "tokenStatus": token_status,
        **({"title": new_title} if new_title else {}),
    })


# ---------------------------------------------------------------------------
# Token status
# ---------------------------------------------------------------------------

@app.get("/users/me/tokens")
@require_auth
def token_status_route():
    return jsonify(users.get_token_status(g.user["uid"]))


# ---------------------------------------------------------------------------
# Document library (RAG source documents)
# ---------------------------------------------------------------------------

@app.post("/documents/sync")
@require_auth
def trigger_sync():
    """Manually trigger a storage sync (e.g. right after a direct upload)."""
    sync_from_storage()
    return jsonify({"status": "ok"})


@app.get("/documents")
@require_auth
def list_docs():
    return jsonify(documents_db.list_documents())


@app.post("/documents/upload")
@require_auth
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    uid      = g.user["uid"]
    doc_id   = str(uuid.uuid4())
    filename = file.filename
    storage_path = f"documents/{doc_id}/{filename}"
    file_bytes   = file.read()

    doc = documents_db.create_document(
        doc_id=doc_id,
        filename=filename,
        uploaded_by=uid,
        storage_path=storage_path,
    )

    # Upload raw PDF to Firebase Storage (non-fatal if it fails)
    try:
        from firebase_admin import storage as fb_storage
        blob = fb_storage.bucket().blob(storage_path)
        blob.upload_from_string(file_bytes, content_type="application/pdf")
    except Exception as e:
        app.logger.warning(f"Firebase Storage upload failed: {e}")

    # Parse → chunk → embed → index in Pinecone
    try:
        from rag.ingest import ingest_pdf
        chunk_count = ingest_pdf(
            file_bytes=file_bytes,
            doc_id=doc_id,
            filename=filename,
        )
        documents_db.update_document(doc_id, {"status": "ready", "chunkCount": chunk_count})
        doc.update({"status": "ready", "chunkCount": chunk_count})
    except Exception as e:
        documents_db.update_document(doc_id, {"status": "error", "error": str(e)})
        return jsonify({"error": str(e)}), 500

    return jsonify(doc), 201


@app.delete("/documents/<doc_id>")
@require_auth
def delete_doc(doc_id):
    doc = documents_db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    if doc.get("chunkCount", 0) > 0:
        try:
            from rag.ingest import delete_document_vectors
            delete_document_vectors(doc_id, doc["chunkCount"])
        except Exception as e:
            app.logger.warning(f"Pinecone deletion failed: {e}")

    try:
        from firebase_admin import storage as fb_storage
        fb_storage.bucket().blob(doc["storagePath"]).delete()
    except Exception as e:
        app.logger.warning(f"Storage deletion failed: {e}")

    documents_db.delete_document(doc_id)
    return "", 204


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
