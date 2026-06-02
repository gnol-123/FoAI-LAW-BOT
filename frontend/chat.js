import { initializeApp }
  from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import {
  getAuth, signOut, onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import { getStorage, ref, uploadBytesResumable }
  from "https://www.gstatic.com/firebasejs/10.12.0/firebase-storage.js";
import { firebaseConfig, API_URL }
  from "./firebase-config.js";

const firebaseApp = initializeApp(firebaseConfig);
const auth        = getAuth(firebaseApp);
const storage     = getStorage(firebaseApp);

let currentSessionId = null;
let _batchRender = false;   // when true, appendMessage skips its per-row scroll
let isAdmin = false;        // managing the shared doc corpus is admin-only (server-enforced)

// ── DOM refs ───────────────────────────────────────────────────────────────────
const chatView        = document.getElementById("chat-view");
const sidebarEl       = document.getElementById("sidebar");
const sidebarToggle   = document.getElementById("sidebar-toggle");
const sidebarChevron  = document.getElementById("sidebar-chevron");
const logoutBtn       = document.getElementById("logout-btn");
const newSessionBtn = document.getElementById("new-session-btn");
const sessionList   = document.getElementById("session-list");
const tabChats      = document.getElementById("tab-chats");
const tabDocs       = document.getElementById("tab-docs");
const panelChats    = document.getElementById("panel-chats");
const panelDocs     = document.getElementById("panel-docs");
const docList       = document.getElementById("doc-list");
const docUpload     = document.getElementById("doc-upload");
const uploadStatus  = document.getElementById("upload-status");
const messagesEl          = document.getElementById("messages");
const emptyState          = document.getElementById("empty-state");
const userInput           = document.getElementById("user-input");
const sendBtn             = document.getElementById("send-btn");
const attachBtn           = document.getElementById("attach-btn");
const fileInput           = document.getElementById("file-input");
const attachmentPreview   = document.getElementById("attachment-preview");
const attachmentIcon      = document.getElementById("attachment-icon");
const attachmentFilename  = document.getElementById("attachment-filename");
const attachmentMeta      = document.getElementById("attachment-meta");
const attachmentRemoveBtn = document.getElementById("attachment-remove");
const chatMain            = document.getElementById("chat-main");
const dragOverlay         = document.getElementById("drag-overlay");

// Current pending attachment — cleared after each message send.
// { text: string, filename: string, type: "pdf"|"image"|"text", charCount: number }
let attachment = null;
const userEmailEl   = document.getElementById("user-email");
const themeToggle   = document.getElementById("theme-toggle");
const tokenBarWrap  = document.getElementById("token-bar-wrap");
const tokenBar      = document.getElementById("token-bar");
const tokenLabel    = document.getElementById("token-label");
const tokenReset    = document.getElementById("token-reset");

// ── Auth guard ─────────────────────────────────────────────────────────────────
// Unauthenticated or unverified users are sent back to the login page.
// The chat UI stays hidden until we confirm the user is valid.
onAuthStateChanged(auth, async (user) => {
  if (!user || !user.emailVerified) {
    window.location.replace("index.html");
    return;
  }
  userEmailEl.textContent = user.email;
  chatView.style.display  = "flex";
  applySidebar();
  await ensureUserDoc();
  await loadUserMeta();
  await loadSessions();
  await fetchTokenStatus();
});

logoutBtn.addEventListener("click", () => signOut(auth));
// After sign-out, onAuthStateChanged fires with null → replaces to index.html.

// ── Sidebar collapse ───────────────────────────────────────────────────────────
const SIDEBAR_KEY = "loraai-sidebar-collapsed";
let sidebarCollapsed = localStorage.getItem(SIDEBAR_KEY) === "1";

function applySidebar() {
  sidebarEl.classList.toggle("collapsed", sidebarCollapsed);
  sidebarToggle.title = sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar";
}

sidebarToggle.addEventListener("click", () => {
  sidebarCollapsed = !sidebarCollapsed;
  localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? "1" : "0");
  applySidebar();
});

// Ctrl+B / Cmd+B keyboard shortcut
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "b") {
    e.preventDefault();
    sidebarCollapsed = !sidebarCollapsed;
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? "1" : "0");
    applySidebar();
  }
});

// ── Theme toggle ───────────────────────────────────────────────────────────────
function applyTheme(dark) {
  document.documentElement.classList.toggle("dark", dark);
  themeToggle.textContent = dark ? "☀️" : "🌙";
  localStorage.setItem("theme", dark ? "dark" : "light");
}

applyTheme(document.documentElement.classList.contains("dark"));

themeToggle.addEventListener("click", () => {
  applyTheme(!document.documentElement.classList.contains("dark"));
});

// ── File attachment ────────────────────────────────────────────────────────────
const TYPE_ICONS    = { pdf: "📄", image: "🖼️", text: "📝" };
const ACCEPTED_EXTS = new Set(["pdf","png","jpg","jpeg","gif","webp","md","markdown","txt"]);

function showAttachmentPreview() {
  attachmentIcon.textContent      = TYPE_ICONS[attachment.type] ?? "📎";
  attachmentFilename.textContent  = attachment.filename;
  attachmentMeta.textContent      = `${(attachment.charCount / 1000).toFixed(1)}k chars`;
  attachmentPreview.style.display = "flex";
}

function clearAttachment() {
  attachment = null;
  attachmentPreview.style.display = "none";
  fileInput.value = "";
}

// Shared upload logic — called by both the file picker and drag-and-drop.
async function processFile(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  if (!ACCEPTED_EXTS.has(ext)) {
    showBanner(`Unsupported file type .${ext} — accepted: PDF, PNG, JPG, GIF, WEBP, MD, TXT`);
    return;
  }

  attachBtn.disabled = true;
  attachBtn.classList.add("opacity-50");

  try {
    const token    = await auth.currentUser.getIdToken();
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_URL}/context-file`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData,
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? res.statusText);

    attachment = data;
    showAttachmentPreview();
  } catch (err) {
    showBanner("Could not process file: " + err.message);
    fileInput.value = "";
  } finally {
    attachBtn.disabled = false;
    attachBtn.classList.remove("opacity-50");
  }
}

attachBtn.addEventListener("click", () => fileInput.click());
attachmentRemoveBtn.addEventListener("click", clearAttachment);
fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (file) await processFile(file);
});

// ── Drag-and-drop onto the chat area ──────────────────────────────────────────
// dragenter/dragleave fire on every child element crossing, so we use a counter
// to avoid the overlay flickering as the cursor moves between child elements.
let dragDepth = 0;

chatMain.addEventListener("dragenter", (e) => {
  e.preventDefault();
  dragDepth++;
  if (dragDepth === 1) dragOverlay.classList.remove("hidden");
});

chatMain.addEventListener("dragleave", () => {
  dragDepth--;
  if (dragDepth === 0) dragOverlay.classList.add("hidden");
});

chatMain.addEventListener("dragover", (e) => {
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
});

chatMain.addEventListener("drop", async (e) => {
  e.preventDefault();
  dragDepth = 0;
  dragOverlay.classList.add("hidden");
  const file = e.dataTransfer.files[0];
  if (file) await processFile(file);
});

// ── Token bar ─────────────────────────────────────────────────────────────────
function updateTokenBar(status) {
  if (!status) return;
  tokenBarWrap.classList.remove("hidden");
  const pct = Math.min(100, (status.used / status.limit) * 100);
  tokenBar.style.width = pct + "%";
  tokenBar.className = `h-1 rounded-full transition-all duration-500 ${
    pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-indigo-500"
  }`;
  tokenLabel.textContent = `${status.used.toLocaleString()} / ${status.limit.toLocaleString()}`;
  if (status.resetsAt) {
    const resetsDate = new Date(status.resetsAt);
    tokenReset.textContent = `Resets ${resetsDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    tokenReset.classList.remove("hidden");
  } else {
    tokenReset.classList.add("hidden");
  }
}

async function fetchTokenStatus() {
  try {
    const status = await api("GET", "/users/me/tokens");
    updateTokenBar(status);
  } catch { /* non-fatal */ }
}

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

// ── User doc ──────────────────────────────────────────────────────────────────
async function ensureUserDoc() {
  const user = auth.currentUser;
  try {
    await api("POST", "/users", { username: user.email.split("@")[0], email: user.email });
  } catch { /* already exists — non-fatal */ }
}

// Fetch the current user's profile to learn whether they may manage the shared
// document corpus. This only drives the UI — the backend enforces admin access
// on every document mutation regardless of what the client shows.
async function loadUserMeta() {
  try {
    const me = await api("GET", "/users/me");
    isAdmin = !!me.isAdmin;
  } catch {
    isAdmin = false;
  }
  applyAdminUI();
}

function applyAdminUI() {
  // Upload control is admin-only; hide it (and any delete buttons) for everyone
  // else so they aren't shown actions the server would reject with 403.
  const uploadLabel = document.getElementById("doc-upload")?.closest("label");
  if (uploadLabel) uploadLabel.style.display = isAdmin ? "" : "none";
}

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
docUpload.addEventListener("change", async () => {
  const file = docUpload.files[0];
  if (!file) return;
  docUpload.value = "";

  uploadStatus.classList.remove("hidden");
  uploadStatus.textContent = `Uploading ${file.name}…`;

  const storageRef = ref(storage, `uploads/${auth.currentUser.uid}/${file.name}`);
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
    for (const doc of docs) docList.appendChild(buildDocRow(doc));
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

  row.appendChild(info);

  // Deletion is admin-only (enforced server-side); only render the control for
  // admins so other users don't get a button that 403s.
  if (isAdmin) {
    const delBtn = document.createElement("button");
    delBtn.className = "hidden group-hover:block flex-shrink-0 p-1 text-slate-500 hover:text-red-400 rounded transition-colors";
    delBtn.textContent = "✕";
    delBtn.title = "Delete document";
    delBtn.addEventListener("click", () => deleteDoc(doc.documentId, row));
    row.appendChild(delBtn);
  }

  return row;
}

async function deleteDoc(docId, rowEl) {
  if (!await showConfirm("Delete this document and remove it from the search index?")) return;
  try {
    await api("DELETE", `/documents/${docId}`);
    rowEl.remove();
  } catch (err) {
    showBanner("Could not delete document: " + err.message);
  }
}

// ── Sessions ───────────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const sessions = await api("GET", "/sessions");
    sessionList.innerHTML = "";
    for (const s of sessions) sessionList.appendChild(buildSessionRow(s));
  } catch (err) {
    showBanner("Could not load sessions: " + err.message);
  }
}

function buildSessionRow(s) {
  const row = document.createElement("div");
  row.className = "flex items-center rounded-xl transition-colors cursor-pointer group hover:bg-slate-800";
  row.dataset.id = s.sessionId;

  const btn = document.createElement("button");
  btn.className = "flex-1 min-w-0 text-left px-3 py-2.5 text-sm text-slate-400 group-hover:text-slate-200 truncate transition-colors";
  btn.textContent = s.title || "Untitled";
  btn.addEventListener("click", () => openSession(s.sessionId));

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

// In-memory cache of loaded message lists, keyed by sessionId. Re-opening a
// previously viewed chat renders instantly from here instead of waiting on a
// network round-trip; a background revalidation keeps it correct. Entries are
// invalidated when the session's messages change (send / delete).
const messageCache = new Map();

async function openSession(sessionId) {
  currentSessionId = sessionId;
  highlightSession(sessionId);

  const cached = messageCache.get(sessionId);
  if (cached) {
    renderMessages(cached);              // instant paint from cache
    revalidateSession(sessionId);        // silently confirm it's still current
    return;
  }

  clearMessages();
  showMessagesLoading();
  try {
    const msgs = await api("GET", `/sessions/${sessionId}/messages`);
    if (currentSessionId !== sessionId) return;   // user switched away mid-load
    messageCache.set(sessionId, msgs);
    renderMessages(msgs);
  } catch (err) {
    if (currentSessionId === sessionId) {
      clearMessages();          // remove the skeleton, restore the empty state
      showBanner("Could not load messages: " + err.message);
    }
  }
}

// Background re-fetch for a cached session. Re-renders only if the content
// actually changed (e.g. edited from another tab) and we're still viewing it,
// so the common "nothing changed" case causes no flicker.
async function revalidateSession(sessionId) {
  try {
    const fresh = await api("GET", `/sessions/${sessionId}/messages`);
    const prev  = messageCache.get(sessionId);
    messageCache.set(sessionId, fresh);
    if (currentSessionId === sessionId && !sameMessages(prev, fresh)) {
      renderMessages(fresh);
    }
  } catch { /* offline / transient — keep showing the cached copy */ }
}

function sameMessages(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i].role !== b[i].role
        || a[i].content !== b[i].content
        || (a[i].attachmentName ?? null) !== (b[i].attachmentName ?? null)) {
      return false;
    }
  }
  return true;
}

// Paint a full message list into the chat pane in one batch — suppress the
// per-message auto-scroll (N reflows) and scroll just once at the end.
function renderMessages(msgs) {
  hideMessagesLoading();
  clearMessages();
  _batchRender = true;
  try {
    for (const m of msgs) appendMessage(m.role, m.content, "", m.attachmentName ?? null, null);
  } finally {
    _batchRender = false;
  }
  scrollToBottom();
}

// Animated skeleton shown while a chat's history is fetched over the network.
function showMessagesLoading() {
  hideMessagesLoading();
  emptyState.style.display = "none";
  const sk = document.createElement("div");
  sk.id = "messages-loading";
  sk.innerHTML = `${skelRow("assistant")}${skelRow("user")}${skelRow("assistant")}`;
  messagesEl.appendChild(sk);
}

function hideMessagesLoading() {
  document.getElementById("messages-loading")?.remove();
}

function skelRow(role) {
  const icon = role === "assistant"
    ? '<div class="skel-icon skel-shimmer"></div>' : "";
  return `
    <div class="msg-row msg-${role}">
      <div class="msg-inner">
        ${icon}
        <div class="skel-body ${role}">
          <div class="skel-line skel-shimmer" style="width:30%"></div>
          <div class="skel-line skel-shimmer" style="width:92%"></div>
          <div class="skel-line skel-shimmer" style="width:78%"></div>
          <div class="skel-line skel-shimmer" style="width:55%"></div>
        </div>
      </div>
    </div>`;
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
  if (!await showConfirm("Delete this chat? This cannot be undone.")) return;
  try {
    await api("DELETE", `/sessions/${sessionId}`);
    messageCache.delete(sessionId);
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

let _sending = false;

async function sendMessage() {
  if (_sending) return;
  const text = userInput.value.trim();
  if (!text) return;

  _sending = true;
  sendBtn.disabled = true;
  let sentSessionId = null;

  try {
    if (!currentSessionId) {
      const session = await api("POST", "/sessions", {
        title: "New conversation",
        jurisdiction: "Australia",
        practiceArea: "",
      });
      currentSessionId = session.sessionId;
      clearMessages();
      await loadSessions();
      highlightSession(currentSessionId);
    }

    userInput.value = "";
    userInput.style.height = "auto";

    // Snapshot and clear — the document is now saved in Firestore history and
    // the LLM will have it in context on every subsequent turn automatically.
    const pendingAttachment = attachment;
    clearAttachment();

    appendMessage("user", text, "", pendingAttachment?.filename ?? null, pendingAttachment?.type ?? null);

    const sessionId = currentSessionId;
    sentSessionId   = sessionId;   // this chat's history will change → invalidate cache
    const stream    = createStreamingAssistantMessage();

    try {
      await streamChat(sessionId, text, pendingAttachment, (evt) => {
        if (currentSessionId !== sessionId) return;
        switch (evt.type) {
          case "status":
            stream.setStatus(evt.stage === "retrieving" ? "Searching documents…" : "Thinking…");
            break;
          case "thinking":
            stream.appendThinking(evt.text);
            break;
          case "answer":
            stream.appendAnswer(evt.text);
            break;
          case "done":
            stream.finalize(evt.thinking, evt.content);
            if (evt.tokenStatus) updateTokenBar(evt.tokenStatus);
            break;
          case "error":
            stream.error(evt.message);
            break;
        }
      });
      await loadSessions();
      highlightSession(sessionId);
    } catch (err) {
      if (err.message === "token_limit_reached") {
        stream.remove();
        await fetchTokenStatus();
        showBanner("Token limit reached — your allowance resets soon. Check the sidebar for the reset time.");
      } else {
        stream.error(err.message);
      }
    }

  } catch (err) {
    showBanner("Could not create session: " + err.message);
  } finally {
    _sending = false;
    sendBtn.disabled = false;
    // The exchange added messages to this chat — drop its cached copy so the
    // next time it's opened the new turn is fetched fresh.
    if (sentSessionId) messageCache.delete(sentSessionId);
    scrollToBottom();
  }
}

// ── Streaming (SSE) ────────────────────────────────────────────────────────────
async function streamChat(sessionId, message, pendingAttachment, onEvent) {
  const token = await auth.currentUser.getIdToken();
  const body  = { message };
  if (pendingAttachment) {
    body.attachmentText = pendingAttachment.text;
    body.attachmentName = pendingAttachment.filename;
  }
  const res = await fetch(`${API_URL}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let data = {};
    try { data = await res.json(); } catch { /* not JSON */ }
    throw new Error(data.error ?? res.statusText);
  }

  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);

      const data = frame
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).replace(/^ /, ""))
        .join("\n");
      if (!data) continue;

      let evt;
      try { evt = JSON.parse(data); } catch { continue; }
      onEvent(evt);
    }
  }
}

// Build a live-updating assistant message; return handlers to drive it.
function createStreamingAssistantMessage() {
  emptyState.style.display = "none";

  const row = document.createElement("div");
  row.className = "msg-row msg-assistant";
  const inner = document.createElement("div");
  inner.className = "msg-inner";
  row.appendChild(inner);

  const icon = document.createElement("div");
  icon.className = "msg-icon";
  icon.textContent = "⚖️";

  const body = document.createElement("div");
  body.className = "msg-assistant-body";

  const label = document.createElement("div");
  label.className = "msg-sender";
  label.textContent = "LoRRAai";
  body.appendChild(label);

  const status = document.createElement("div");
  status.style.cssText = "display:flex;align-items:center";
  const dot = document.createElement("span");
  dot.className = "msg-thinking-dot";
  const statusText = document.createElement("span");
  statusText.style.cssText = "color:var(--dim-color);font-style:italic;font-size:0.875rem";
  statusText.textContent = "Thinking…";
  status.appendChild(dot);
  status.appendChild(statusText);
  body.appendChild(status);

  const details = document.createElement("details");
  details.className = "thinking-block rounded-xl overflow-hidden text-xs mb-3";
  details.open = true;
  details.style.display = "none";
  const summary = document.createElement("summary");
  summary.className = "flex items-center gap-2 px-4 py-2.5 cursor-pointer select-none font-medium list-none transition-colors";
  summary.innerHTML = `<span class="thinking-chevron transition-transform duration-200">▶</span> 🧠 Reasoning`;
  const chevron = summary.querySelector(".thinking-chevron");
  chevron.style.transform = "rotate(90deg)";
  const thinkingBody = document.createElement("div");
  thinkingBody.className = "thinking-body px-4 py-3 leading-relaxed prose prose-sm max-w-none";
  details.appendChild(summary);
  details.appendChild(thinkingBody);
  details.addEventListener("toggle", () => {
    chevron.style.transform = details.open ? "rotate(90deg)" : "";
  });
  body.appendChild(details);

  const answerEl = document.createElement("div");
  answerEl.className = "prose prose-sm max-w-none";
  body.appendChild(answerEl);

  inner.appendChild(icon);
  inner.appendChild(body);
  messagesEl.appendChild(row);
  scrollToBottom();

  let thinkingRaw = "";
  let answerRaw   = "";
  let finalized   = false;
  let rafPending  = false;

  function scheduleAnswerRender() {
    if (rafPending || finalized) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      if (finalized) return;
      answerEl.innerHTML = DOMPurify.sanitize(marked.parse(answerRaw));
      scrollToBottom();
    });
  }

  return {
    setStatus(text) {
      if (!finalized) statusText.textContent = text;
    },
    appendThinking(t) {
      thinkingRaw += t;
      status.style.display = "none";
      details.style.display = "";
      thinkingBody.textContent = thinkingRaw;
      scrollToBottom();
    },
    appendAnswer(t) {
      answerRaw += t;
      status.style.display = "none";
      scheduleAnswerRender();
    },
    finalize(finalThinking, finalAnswer) {
      finalized = true;
      status.remove();
      const th = (finalThinking ?? thinkingRaw).trim();
      const an = (finalAnswer   ?? answerRaw).trim();
      if (th) {
        thinkingBody.innerHTML = DOMPurify.sanitize(marked.parse(th));
        details.open = false;
        chevron.style.transform = "";
      } else {
        details.remove();
      }
      answerEl.innerHTML = an
        ? DOMPurify.sanitize(marked.parse(an))
        : "(empty response)";
      scrollToBottom();
    },
    error(msg) {
      finalized = true;
      status.remove();
      details.remove();
      answerEl.innerHTML = DOMPurify.sanitize(marked.parse(`⚠️ ${msg}`));
      scrollToBottom();
    },
    remove() { row.remove(); },
  };
}

// Render a completed message (used when loading chat history).
// attachmentName / attachmentType are optional and only shown for the current
// session's user messages — they are not stored per-message in the DB.
function appendMessage(role, content, thinking = "", attachmentName = null, attachmentType = null) {
  emptyState.style.display = "none";

  function makeRow(extraClass) {
    const row   = document.createElement("div");
    row.className = `msg-row ${extraClass}`;
    const inner = document.createElement("div");
    inner.className = "msg-inner";
    row.appendChild(inner);
    return { row, inner };
  }

  if (role === "user") {
    const { row, inner } = makeRow("msg-user");
    const body  = document.createElement("div");
    body.className = "msg-user-body";

    const label = document.createElement("div");
    label.className = "msg-sender";
    label.textContent = "You";

    const text = document.createElement("div");
    text.className = "msg-user-text";
    text.textContent = content;

    body.appendChild(label);
    body.appendChild(text);

    // Attachment chip shown below the message bubble when a file was sent.
    if (attachmentName) {
      const chip = document.createElement("div");
      chip.className = "flex items-center gap-1.5 mt-2 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/25 rounded-xl px-3 py-1.5 text-xs w-fit ml-auto";
      const icon = document.createElement("span");
      icon.textContent = TYPE_ICONS[attachmentType] ?? "📎";
      const name = document.createElement("span");
      name.className = "truncate max-w-[220px] text-indigo-700 dark:text-indigo-300 font-medium";
      name.textContent = attachmentName;
      chip.appendChild(icon);
      chip.appendChild(name);
      body.appendChild(chip);
    }

    inner.appendChild(body);
    messagesEl.appendChild(row);
    if (!_batchRender) scrollToBottom();
    return row;
  }

  // Assistant
  const { row, inner } = makeRow("msg-assistant");
  const icon = document.createElement("div");
  icon.className = "msg-icon";
  icon.textContent = "⚖️";

  const body = document.createElement("div");
  body.className = "msg-assistant-body";

  const label = document.createElement("div");
  label.className = "msg-sender";
  label.textContent = "LoRRAai";
  body.appendChild(label);

  if (thinking) {
    const details = document.createElement("details");
    details.className = "thinking-block rounded-xl overflow-hidden text-xs mb-3";
    const summary = document.createElement("summary");
    summary.className = "flex items-center gap-2 px-4 py-2.5 cursor-pointer select-none font-medium list-none transition-colors";
    summary.innerHTML = `<span class="thinking-chevron transition-transform duration-200">▶</span> 🧠 Reasoning`;
    const thinkingBody = document.createElement("div");
    thinkingBody.className = "thinking-body px-4 py-3 leading-relaxed prose prose-sm max-w-none";
    thinkingBody.innerHTML = DOMPurify.sanitize(marked.parse(thinking));
    details.appendChild(summary);
    details.appendChild(thinkingBody);
    body.appendChild(details);
    details.addEventListener("toggle", () => {
      summary.querySelector(".thinking-chevron").style.transform =
        details.open ? "rotate(90deg)" : "";
    });
  }

  const answer = document.createElement("div");
  answer.className = "prose prose-sm max-w-none";
  answer.innerHTML = content
    ? DOMPurify.sanitize(marked.parse(content))
    : "(empty response)";
  body.appendChild(answer);

  inner.appendChild(icon);
  inner.appendChild(body);
  messagesEl.appendChild(row);
  if (!_batchRender) scrollToBottom();
  return row;
}

// ── Utilities ──────────────────────────────────────────────────────────────────
function clearMessages() {
  messagesEl.innerHTML = "";
  messagesEl.appendChild(emptyState);
  emptyState.style.display = "";
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showConfirm(message) {
  return new Promise((resolve) => {
    const backdrop  = document.getElementById("confirm-backdrop");
    const msgEl     = document.getElementById("confirm-message");
    const okBtn     = document.getElementById("confirm-ok");
    const cancelBtn = document.getElementById("confirm-cancel");

    msgEl.textContent = message;
    backdrop.classList.remove("hidden");

    const finish = (result) => {
      backdrop.classList.add("hidden");
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      backdrop.removeEventListener("click", onBackdrop);
      resolve(result);
    };
    const onOk       = () => finish(true);
    const onCancel   = () => finish(false);
    const onBackdrop = (e) => { if (e.target === backdrop) finish(false); };

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    backdrop.addEventListener("click", onBackdrop);
  });
}

function showBanner(msg) {
  console.error("[LoRRAai]", msg);
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
