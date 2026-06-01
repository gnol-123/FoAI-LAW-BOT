"""
Quick manual test — run with: python test_auth.py
Requires the Flask server to be running: flask --app app run
"""
import requests

# ── config ────────────────────────────────────────────────────────────────────
FIREBASE_WEB_API_KEY = "YOUR_WEB_API_KEY"   # Firebase Console → Project Settings → General
TEST_EMAIL    = "test@example.com"           # user you created in Firebase Console → Auth
TEST_PASSWORD = "testpassword"
BASE_URL      = "http://127.0.0.1:5000"
# ──────────────────────────────────────────────────────────────────────────────


def get_id_token(email: str, password: str) -> str:
    """Sign in via Firebase Auth REST API and return an ID token."""
    resp = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={FIREBASE_WEB_API_KEY}",
        json={"email": email, "password": password, "returnSecureToken": True},
    )
    resp.raise_for_status()
    token = resp.json()["idToken"]
    print(f"[OK] signed in as {email}")
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_health():
    r = requests.get(f"{BASE_URL}/health")
    print(f"[health] {r.status_code} {r.json()}")


def test_create_user(token: str):
    r = requests.post(
        f"{BASE_URL}/users",
        headers=auth_headers(token),
        json={"username": "testuser", "email": TEST_EMAIL},
    )
    print(f"[POST /users] {r.status_code} {r.json()}")


def test_create_session(token: str) -> str:
    r = requests.post(
        f"{BASE_URL}/sessions",
        headers=auth_headers(token),
        json={"title": "Test session", "jurisdiction": "Australia", "practiceArea": "Employment"},
    )
    print(f"[POST /sessions] {r.status_code} {r.json()}")
    return r.json().get("sessionId", "")


def test_chat(token: str, session_id: str):
    r = requests.post(
        f"{BASE_URL}/sessions/{session_id}/chat",
        headers=auth_headers(token),
        json={"message": "What is unfair dismissal under Australian law?"},
    )
    print(f"[POST /chat] {r.status_code}")
    data = r.json()
    print(f"  content: {data.get('content', '')[:300]}")


if __name__ == "__main__":
    test_health()
    token = get_id_token(TEST_EMAIL, TEST_PASSWORD)
    test_create_user(token)
    session_id = test_create_session(token)
    if session_id:
        test_chat(token, session_id)
