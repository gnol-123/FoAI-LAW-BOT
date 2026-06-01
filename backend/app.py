import os
from functools import wraps

from dotenv import load_dotenv
from firebase_admin import auth
from flask import Flask, g, jsonify, request

from db import chat_sessions, messages, users

load_dotenv()

app = Flask(__name__)


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
    user = users.create_user(
        user_id=uid,
        username=body["username"],
        email=body["email"],
        plan=body.get("plan", "free"),
    )
    return jsonify(user), 201


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

if __name__ == "__main__":
    app.run(debug=True)
