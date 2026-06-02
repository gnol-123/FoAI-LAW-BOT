import { initializeApp }
  from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import {
  getAuth, signInWithEmailAndPassword, createUserWithEmailAndPassword,
  GoogleAuthProvider, signInWithPopup, sendEmailVerification,
  signOut, onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import { firebaseConfig } from "./firebase-config.js";

const auth = getAuth(initializeApp(firebaseConfig));

// ── DOM refs ───────────────────────────────────────────────────────────────────
const loginView       = document.getElementById("login-view");
const verifyView      = document.getElementById("verify-view");
const tabSignin       = document.getElementById("tab-signin");
const tabRegister     = document.getElementById("tab-register");
const authForm        = document.getElementById("auth-form");
const authEmailEl     = document.getElementById("auth-email");
const authPasswordEl  = document.getElementById("auth-password");
const authConfirmEl   = document.getElementById("auth-confirm");
const authSubmit      = document.getElementById("auth-submit");
const authError       = document.getElementById("auth-error");
const googleBtn       = document.getElementById("google-btn");
const verifyEmailEl   = document.getElementById("verify-email");
const verifyCheckBtn  = document.getElementById("verify-check-btn");
const verifyResendBtn = document.getElementById("verify-resend-btn");
const verifyLogoutBtn = document.getElementById("verify-logout-btn");
const verifyMsg       = document.getElementById("verify-msg");

// ── Auth state routing ─────────────────────────────────────────────────────────
// Verified users are sent to chat.html immediately; this page is login-only.
onAuthStateChanged(auth, (user) => {
  if (user && user.emailVerified) {
    window.location.replace("chat.html");
    return;
  }
  if (user && !user.emailVerified) {
    showVerifyView(user);
    return;
  }
  showLoginView();
});

// ── Views ─────────────────────────────────────────────────────────────────────
function showLoginView() {
  verifyView.style.display = "none";
  loginView.style.display  = "";
}

function showVerifyView(user) {
  loginView.style.display   = "none";
  verifyView.style.display  = "";
  verifyEmailEl.textContent = user.email;
  verifyMsg.textContent     = "";
}

// ── Error mapping ──────────────────────────────────────────────────────────────
function mapAuthError(code) {
  return ({
    "auth/email-already-in-use":   "An account with this email already exists.",
    "auth/invalid-email":          "Invalid email address.",
    "auth/weak-password":          "Password must be at least 6 characters.",
    "auth/user-not-found":         "No account found with this email.",
    "auth/wrong-password":         "Incorrect password.",
    "auth/invalid-credential":     "Invalid email or password.",
    "auth/too-many-requests":      "Too many attempts. Please try again later.",
    "auth/popup-closed-by-user":   "Sign-in cancelled.",
    "auth/network-request-failed": "Network error. Check your connection.",
  })[code] || "Something went wrong. Please try again.";
}

// ── Verification email settings ────────────────────────────────────────────────
// After clicking the link, Firebase redirects here; onAuthStateChanged then
// detects the verified user and sends them to chat.html automatically.
const VERIFY_ACTION_SETTINGS = {
  url: `${location.origin}/`,
  handleCodeInApp: false,
};

// ── Auth mode toggle (Sign in / Create account) ────────────────────────────────
let authMode = "signin";

function setAuthMode(mode) {
  authMode = mode;
  const reg = mode === "register";
  authConfirmEl.style.display = reg ? "" : "none";
  authConfirmEl.required      = reg;
  authSubmit.textContent      = reg ? "Create account" : "Sign in";
  authPasswordEl.autocomplete = reg ? "new-password" : "current-password";
  authError.textContent       = "";

  const active   = "bg-white dark:bg-slate-600 text-slate-900 dark:text-white shadow-sm";
  const inactive = "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200";
  tabSignin.className   = `flex-1 py-1.5 text-sm font-medium rounded-lg transition ${reg  ? inactive : active}`;
  tabRegister.className = `flex-1 py-1.5 text-sm font-medium rounded-lg transition ${reg  ? active   : inactive}`;
}

tabSignin.addEventListener("click",   () => setAuthMode("signin"));
tabRegister.addEventListener("click", () => setAuthMode("register"));

// ── Auth form submit ───────────────────────────────────────────────────────────
authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authError.textContent = "";
  const email    = authEmailEl.value.trim();
  const password = authPasswordEl.value;

  if (authMode === "register") {
    if (password !== authConfirmEl.value) {
      authError.textContent = "Passwords do not match.";
      return;
    }
    try {
      const cred = await createUserWithEmailAndPassword(auth, email, password);
      try {
        await sendEmailVerification(cred.user, VERIFY_ACTION_SETTINGS);
      } catch (emailErr) {
        console.warn("[auth] sendEmailVerification failed:", emailErr.message);
      }
      showVerifyView(cred.user);
    } catch (err) {
      authError.textContent = mapAuthError(err.code);
    }
  } else {
    try {
      await signInWithEmailAndPassword(auth, email, password);
      // onAuthStateChanged fires → redirects to chat.html
    } catch (err) {
      authError.textContent = mapAuthError(err.code);
    }
  }
});

// ── Google sign-in ─────────────────────────────────────────────────────────────
googleBtn.addEventListener("click", async () => {
  authError.textContent = "";
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
    // onAuthStateChanged fires → redirects to chat.html
  } catch (err) {
    authError.textContent = mapAuthError(err.code);
  }
});

// ── Verification screen ────────────────────────────────────────────────────────
verifyCheckBtn.addEventListener("click", async () => {
  try {
    await auth.currentUser.reload();
    if (auth.currentUser.emailVerified) {
      window.location.replace("chat.html");
    } else {
      verifyMsg.textContent = "Not verified yet — check your inbox and click the link.";
    }
  } catch {
    verifyMsg.textContent = "Could not check status. Try again.";
  }
});

verifyResendBtn.addEventListener("click", async () => {
  try {
    await sendEmailVerification(auth.currentUser, VERIFY_ACTION_SETTINGS);
    verifyMsg.textContent = "✓ Verification email sent! Check your spam folder too.";
  } catch {
    verifyMsg.textContent = "Could not resend — wait a moment and try again.";
  }
});

verifyLogoutBtn.addEventListener("click", () => signOut(auth));
