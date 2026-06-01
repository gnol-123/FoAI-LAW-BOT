import { initializeApp }
  from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged }
  from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import { getStorage, ref, uploadBytesResumable }
  from "https://www.gstatic.com/firebasejs/10.12.0/firebase-storage.js";
import { firebaseConfig, API_URL }
  from "./firebase-config.js";

const firebaseApp = initializeApp(firebaseConfig);
const auth        = getAuth(firebaseApp);
const storage     = getStorage(firebaseApp);

let currentSessionId = null;

// ── DOM refs ───────────────────────────────────────────────────────────────────
const loginView     = document.getElementById("login-view");
const chatView      = document.getElementById("chat-view");
const loginForm     = document.getElementById("login-form");
const loginError    = document.getElementById("login-error");
const logoutBtn     = document.getElementById("logout-btn");
const newSessionBtn = document.getElementById("new-session-btn");
const sessionList   = document.getElementById("session-list");
const tabChats      = document.getElementById("tab-chats");
const tabDocs       = document.getElementById("tab-docs");
const panelChats    = document.getElementById("panel-chats");
const panelDocs     = document.getElementById("panel-docs");
const docList       = document.getElementById("doc-list");
const docUpload     = document.getElementById("doc-upload");
const uploadStatus  = document.getElementById("upload-status");
const messagesEl    = document.getElementById("messages");
const emptyState    = document.getElementById("empty-state");
const userInput     = document.getElementById("user-input");
const sendBtn       = document.getElementById("send-btn");
const userEmailEl   = document.getElementById("user-email");
const themeToggle   = document.getElementById("theme-toggle");

// ── Auth ───────────────────────────────────────────────────────────────────────
onAuthStateChanged(auth, async (user) => {
  if (user) {
    loginView.style.display = "none";
    chatView.style.display  = "flex";
    userEmailEl.textContent = user.email;
    await ensureUserDoc();
    await loadSessions();
  } else {
    chatView.style.display  = "none";
    loginView.style.display = "";
    currentSessionId = null;
  }
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  try {
    await signInWithEmailAndPassword(
      auth,
      document.getElementById("email").value,
      document.getElementById("password").value,
    );
  } catch {
    loginError.textContent = "Invalid email or password.";
  }
});

logoutBtn.addEventListener("click", () => signOut(auth));

// ── API helper ─────────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const token = await auth.currentUser.getIdToken();
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    ...(body && { body: JSON.stringify(body) }),
  });
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? res.statusText);
  return data;
}

// ── Theme toggle ──────────────────────────────────────────────────────────────
function applyTheme(dark) {
  document.documentElement.classList.toggle("dark", dark);
  themeToggle.textContent = dark ? "☀️" : "🌙";
  localStorage.setItem("theme", dark ? "dark" : "light");
}

// Sync button icon with current state (class was set before JS loaded)
applyTheme(document.documentElement.classList.contains("dark"));

themeToggle.addEventListener("click", () => {
  applyTheme(!document.documentElement.classList.contains("dark"));
});

// ── Sidebar tabs ───────────────────────────────────────────────────────────────
tabChats.addEventListener("click", () => switchTab("chats"));
tabDocs.addEventListener("click",  () => switchTab("docs"));

function switchTab(tab) {
  const isChats = tab === "chats";
  panelChats.style.display = isChats ? "flex" : "none";
  panelDocs.style.display  = isChats ? "none"  : "flex";
  tabChats.className = `tab-btn flex-1 text-xs font-medium py-1.5 rounded-lg transition ${isChats  ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"}`;
  tabDocs.className  = `tab-btn flex-1 text-xs font-medium py-1.5 rounded-lg transition ${!isChats ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"}`;
  if (!isChats) loadDocs();
}

// ── Documents ─────────────────────────────────────────────────────────────────
async function apiUpload(path, formData) {
  const token = await auth.currentUser.getIdToken();
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}` },
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? res.statusText);
  return data;
}

docUpload.addEventListener("change", async () => {
  const file = docUpload.files[0];
  if (!file) return;
  docUpload.value = "";

  uploadStatus.classList.remove("hidden");
  uploadStatus.textContent = `Uploading ${file.name}…`;

  const storageRef = ref(storage, `uploads/${file.name}`);
  const task = uploadBytesResumable(storageRef, file);

  task.on(
    "state_changed",
    (snap) => {
      const pct = Math.round((snap.bytesTransferred / snap.totalBytes) * 100);
      uploadStatus.textContent = `Uploading ${file.name}… ${pct}%`;
    },
    (err) => {
      uploadStatus.textContent = "Upload failed: " + err.message;
    },
    async () => {
      // File is in Storage — ask Flask to sync and index it
      uploadStatus.textContent = `Indexing ${file.name}…`;
      try {
        await api("POST", "/documents/sync");
        uploadStatus.textContent = `${file.name} indexed ✓`;
        await loadDocs();
        setTimeout(() => uploadStatus.classList.add("hidden"), 3000);
      } catch {
        uploadStatus.textContent = `${file.name} uploaded — will index on next restart`;
        setTimeout(() => uploadStatus.classList.add("hidden"), 5000);
      }
    },
  );
});

async function loadDocs() {
  try {
    const docs = await api("GET", "/documents");
    docList.innerHTML = "";
    if (!docs.length) {
      docList.innerHTML = `<p class="text-xs text-slate-500 text-center px-3 py-4">No documents yet.<br>Upload a PDF to enable RAG.</p>`;
      return;
    }
    for (const doc of docs) {
      docList.appendChild(buildDocRow(doc));
    }
  } catch (err) {
    showBanner("Could not load documents: " + err.message);
  }
}

function buildDocRow(doc) {
  const row = document.createElement("div");
  row.className = "flex items-start gap-2 px-3 py-2.5 rounded-xl bg-slate-800/60 hover:bg-slate-800 group transition-colors";

  const info = document.createElement("div");
  info.className = "flex-1 min-w-0";

  const name = document.createElement("p");
  name.className = "text-xs text-slate-200 truncate font-medium";
  name.textContent = doc.filename;

  const statusColors = { ready: "text-emerald-400", processing: "text-amber-400", error: "text-red-400" };
  const meta = document.createElement("p");
  meta.className = `text-xs mt-0.5 ${statusColors[doc.status] ?? "text-slate-500"}`;
  meta.textContent = doc.status === "ready"
    ? `${doc.chunkCount} chunks indexed`
    : doc.status === "processing" ? "Processing…" : "Error";

  info.appendChild(name);
  info.appendChild(meta);

  const delBtn = document.createElement("button");
  delBtn.className = "hidden group-hover:block flex-shrink-0 p-1 text-slate-500 hover:text-red-400 rounded transition-colors";
  delBtn.textContent = "✕";
  delBtn.title = "Delete document";
  delBtn.addEventListener("click", () => deleteDoc(doc.documentId, row));

  row.appendChild(info);
  row.appendChild(delBtn);
  return row;
}

async function deleteDoc(docId, rowEl) {
  if (!confirm("Delete this document and remove it from the search index?")) return;
  try {
    await api("DELETE", `/documents/${docId}`);
    rowEl.remove();
  } catch (err) {
    showBanner("Could not delete document: " + err.message);
  }
}

async function ensureUserDoc() {
  const user = auth.currentUser;
  try {
    await api("POST", "/users", { username: user.email.split("@")[0], email: user.email });
  } catch { /* already exists */ }
}

// ── Sessions ───────────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const sessions = await api("GET", "/sessions");
    sessionList.innerHTML = "";
    for (const s of sessions) {
      sessionList.appendChild(buildSessionRow(s));
    }
  } catch (err) {
    showBanner("Could not load sessions: " + err.message);
  }
}

function buildSessionRow(s) {
  const row = document.createElement("div");
  row.className = "flex items-center rounded-xl transition-colors cursor-pointer group hover:bg-slate-800";
  row.dataset.id = s.sessionId;

  // Title button
  const btn = document.createElement("button");
  btn.className = "flex-1 min-w-0 text-left px-3 py-2.5 text-sm text-slate-400 group-hover:text-slate-200 truncate transition-colors";
  btn.textContent = s.title || "Untitled";
  btn.addEventListener("click", () => openSession(s.sessionId));

  // Rename input (hidden until pencil is clicked)
  const input = document.createElement("input");
  input.type  = "text";
  input.value = s.title || "Untitled";
  input.style.display = "none";
  input.className = "flex-1 min-w-0 mx-2 px-2 py-1 bg-slate-700 border border-indigo-500 rounded-lg text-slate-200 text-sm outline-none";

  const saveRename = async () => {
    const newTitle = input.value.trim() || btn.textContent;
    input.style.display = "none";
    btn.style.display   = "";
    if (newTitle === btn.textContent) return;
    try {
      await api("PATCH", `/sessions/${s.sessionId}`, { title: newTitle });
      btn.textContent = newTitle;
      input.value     = newTitle;
    } catch (err) {
      showBanner("Could not rename: " + err.message);
    }
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter")  { e.preventDefault(); saveRename(); }
    if (e.key === "Escape") { input.style.display = "none"; btn.style.display = ""; }
  });
  input.addEventListener("blur", saveRename);

  // Action buttons (shown on row hover via JS)
  const actions = document.createElement("div");
  actions.className = "hidden items-center gap-0.5 pr-1 flex-shrink-0";

  row.addEventListener("mouseenter", () => actions.style.display = "flex");
  row.addEventListener("mouseleave", () => actions.style.display = "none");

  const renameBtn = document.createElement("button");
  renameBtn.className = "p-1.5 text-slate-500 hover:text-slate-300 rounded-lg hover:bg-slate-700 transition-colors text-xs";
  renameBtn.title = "Rename";
  renameBtn.textContent = "✎";
  renameBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    btn.style.display   = "none";
    input.style.display = "block";
    input.focus();
    input.select();
  });

  const delBtn = document.createElement("button");
  delBtn.className = "p-1.5 text-slate-500 hover:text-red-400 rounded-lg hover:bg-slate-700 transition-colors text-xs";
  delBtn.title = "Delete";
  delBtn.textContent = "✕";
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteSession(s.sessionId, row);
  });

  actions.appendChild(renameBtn);
  actions.appendChild(delBtn);

  row.appendChild(btn);
  row.appendChild(input);
  row.appendChild(actions);
  return row;
}

newSessionBtn.addEventListener("click", async () => {
  try {
    newSessionBtn.disabled = true;
    const session = await api("POST", "/sessions", {
      title: "New conversation",
      jurisdiction: "Australia",
      practiceArea: "",
    });
    currentSessionId = session.sessionId;
    clearMessages();
    await loadSessions();
    highlightSession(currentSessionId);
    userInput.focus();
  } catch (err) {
    showBanner("Could not create session: " + err.message);
  } finally {
    newSessionBtn.disabled = false;
  }
});

async function openSession(sessionId) {
  currentSessionId = sessionId;
  clearMessages();
  highlightSession(sessionId);
  const msgs = await api("GET", `/sessions/${sessionId}/messages`);
  for (const m of msgs) appendMessage(m.role, m.content, "");
  scrollToBottom();
}

function highlightSession(sessionId) {
  document.querySelectorAll("#session-list > div").forEach(row => {
    const isActive = row.dataset.id === sessionId;
    row.classList.toggle("bg-slate-800", isActive);
    const btn = row.querySelector("button:first-child");
    if (btn) {
      btn.classList.toggle("text-slate-200", isActive);
      btn.classList.toggle("text-slate-400", !isActive);
    }
  });
}

async function deleteSession(sessionId, rowEl) {
  if (!confirm("Delete this chat?")) return;
  try {
    await api("DELETE", `/sessions/${sessionId}`);
    rowEl.remove();
    if (currentSessionId === sessionId) {
      currentSessionId = null;
      clearMessages();
    }
  } catch (err) {
    showBanner("Could not delete chat: " + err.message);
  }
}

// ── Chat ───────────────────────────────────────────────────────────────────────
sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

userInput.addEventListener("input", () => {
  userInput.style.height = "auto";
  userInput.style.height = userInput.scrollHeight + "px";
});

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || !currentSessionId) return;

  userInput.value = "";
  userInput.style.height = "auto";
  appendMessage("user", text);

  const thinkingEl = appendMessage("assistant", "Thinking…", "", true);
  sendBtn.disabled = true;

  try {
    const res = await api("POST", `/sessions/${currentSessionId}/chat`, { message: text });
    thinkingEl.remove();
    appendMessage("assistant", res.content, res.thinking || "");
    await loadSessions();
    highlightSession(currentSessionId);
  } catch (err) {
    thinkingEl.className = thinkingEl.className.replace("text-slate-400 italic", "text-red-500");
    thinkingEl.textContent = "Error: " + err.message;
  } finally {
    sendBtn.disabled = false;
    scrollToBottom();
  }
}

function appendMessage(role, content, thinking = "", isThinking = false) {
  emptyState.style.display = "none";

  // ── Temporary "thinking" placeholder ──────────────────────────────────────
  if (isThinking) {
    const div = document.createElement("div");
    div.className = "bubble-thinking max-w-[75%] self-start italic px-4 py-3 rounded-2xl rounded-bl-sm text-sm";
    div.textContent = content;
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  // ── User message ──────────────────────────────────────────────────────────
  if (role === "user") {
    const div = document.createElement("div");
    div.className = "max-w-[75%] self-end bg-indigo-600 text-white px-4 py-3 rounded-2xl rounded-br-sm text-sm leading-relaxed break-words";
    div.textContent = content;
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  // ── Assistant message (with optional chain-of-thought) ────────────────────
  const wrapper = document.createElement("div");
  wrapper.className = "self-start max-w-[80%] flex flex-col gap-2";

  // Collapsible thinking block
  if (thinking) {
    const details = document.createElement("details");
    details.className = "thinking-block rounded-xl overflow-hidden text-xs";

    const summary = document.createElement("summary");
    summary.className = "flex items-center gap-2 px-4 py-2.5 cursor-pointer select-none font-medium list-none transition-colors";
    summary.innerHTML = `<span class="thinking-chevron transition-transform duration-200">▶</span> 🧠 Reasoning`;

    const thinkingBody = document.createElement("div");
    thinkingBody.className = "thinking-body px-4 py-3 leading-relaxed prose prose-sm max-w-none";
    thinkingBody.innerHTML = marked.parse(thinking);

    details.appendChild(summary);
    details.appendChild(thinkingBody);
    wrapper.appendChild(details);

    details.addEventListener("toggle", () => {
      const chevron = summary.querySelector(".thinking-chevron");
      chevron.style.transform = details.open ? "rotate(90deg)" : "";
    });
  }

  // Answer block
  const answerDiv = document.createElement("div");
  answerDiv.className = "bubble-assistant px-5 py-4 rounded-2xl rounded-bl-sm prose prose-sm max-w-none";
  const rendered = content ? marked.parse(content) : "";
  if (rendered) {
    answerDiv.innerHTML = rendered;
  } else {
    const stripped = (content || "").replace(/<[^>]+>/g, " ").trim();
    answerDiv.textContent = stripped || "(empty response)";
  }

  wrapper.appendChild(answerDiv);
  messagesEl.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function clearMessages() {
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyState);
  emptyState.style.display = "";
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showBanner(msg) {
  console.error("[LoRAai]", msg);
  let banner = document.getElementById("error-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "error-banner";
    document.body.appendChild(banner);
  }
  banner.textContent = msg;
  banner.style.display = "block";
  setTimeout(() => { banner.style.display = "none"; }, 6000);
}
