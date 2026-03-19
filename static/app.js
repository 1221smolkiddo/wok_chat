const COMMON_REACTIONS = ["\u{1F44D}", "\u2764\uFE0F", "\u{1F602}", "\u{1F62E}", "\u{1F64F}", "\u{1F525}"];
const EMOJI_SHORTCUTS = [
  "\u{1F600}",
  "\u{1F602}",
  "\u{1F970}",
  "\u{1F62D}",
  "\u{1F64F}",
  "\u2764\uFE0F",
  "\u{1F525}",
  "\u{1F44D}",
  "\u{1F389}",
  "\u{1F319}",
];

const state = {
  token: sessionStorage.getItem("wokchat_token") || "",
  theme: localStorage.getItem("wokchat_theme") || "light",
  me: null,
  peer: null,
  messages: [],
  filteredMessages: null,
  socket: null,
  config: { message_ttl_hours: 48, max_upload_size_mb: 20 },
  pendingFile: null,
  recorder: null,
  recorderStream: null,
  isRecording: false,
  presence: {},
  replyTo: null,
  typingTimeout: null,
  peerTyping: false,
  localTypingSent: false,
  searchTimeout: null,
  renderQueued: false,
  previewUrl: null,
  isUploading: false,
  activeMenuId: null,
  holdTimer: null,
  currentScreen: "home",
  cryptoKey: null,
  cryptoKeys: [],
  confirmAction: null,
};

const loginShell = document.getElementById("login-shell");
const appShell = document.getElementById("app-shell");
const homeScreen = document.getElementById("home-screen");
const chatScreen = document.getElementById("chat-screen");
const authForm = document.getElementById("auth-form");
const chatKeyInput = document.getElementById("chat-key");
const feed = document.getElementById("message-feed");
const emptyState = document.getElementById("empty-state");
const composer = document.getElementById("composer");
const messageInput = document.getElementById("message-input");
const peerName = document.getElementById("peer-name");
const chatTitle = document.getElementById("chat-title");
const connectionPill = document.getElementById("connection-pill");
const retentionPill = document.getElementById("retention-pill");
const toastRegion = document.getElementById("toast-region");
const fileInput = document.getElementById("file-input");
const attachBtn = document.getElementById("attach-btn");
const emojiBtn = document.getElementById("emoji-btn");
const emojiTray = document.getElementById("emoji-tray");
const recordBtn = document.getElementById("record-btn");
const clearChatBtn = document.getElementById("clear-chat-btn");
const attachmentPreview = document.getElementById("attachment-preview");
const composerNote = document.getElementById("composer-note");
const themeToggle = document.getElementById("theme-toggle");
const typingIndicator = document.getElementById("typing-indicator");
const searchInput = document.getElementById("search-input");
const homeSearch = document.getElementById("home-search");
const replyPreview = document.getElementById("reply-preview");
const sendBtn = document.getElementById("send-btn");
const lightbox = document.getElementById("lightbox");
const lightboxImage = document.getElementById("lightbox-image");
const lightboxClose = document.getElementById("lightbox-close");
const confirmOverlay = document.getElementById("confirm-overlay");
const confirmTitle = document.getElementById("confirm-title");
const confirmMessage = document.getElementById("confirm-message");
const confirmCancelBtn = document.getElementById("confirm-cancel-btn");
const confirmOkBtn = document.getElementById("confirm-ok-btn");
const chatList = document.getElementById("chat-list");
const welcomeLabel = document.getElementById("welcome-label");
const securityBanner = document.getElementById("security-banner");
const profileBtn = document.getElementById("profile-btn");
const profileMenu = document.getElementById("profile-menu");
const profileName = document.getElementById("profile-name");
const logoutBtn = document.getElementById("logout-btn");
const backBtn = document.getElementById("back-btn");
const chatMenuBtn = document.getElementById("chat-menu-btn");
const chatMenu = document.getElementById("chat-menu");
const chatClearBtn = document.getElementById("chat-clear-btn");

const supportedExtensions = new Set([
  "jpg",
  "jpeg",
  "png",
  "webp",
  "gif",
  "heic",
  "heif",
  "mp4",
  "mov",
  "webm",
  "mp3",
  "m4a",
  "wav",
  "ogg",
]);

function applyTheme(theme) {
  state.theme = theme;
  document.body.dataset.theme = theme;
  localStorage.setItem("wokchat_theme", theme);
}

function saveToken(token) {
  state.token = token;
  if (token) {
    sessionStorage.setItem("wokchat_token", token);
  } else {
    sessionStorage.removeItem("wokchat_token");
  }
}

function showToast(message, type = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;
  toastRegion.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3200);
}

function detectFileKind(file) {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
  if (!supportedExtensions.has(extension)) return null;
  if (["jpg", "jpeg", "png", "webp", "gif", "heic", "heif"].includes(extension)) return "image";
  if (["mp4", "mov", "webm"].includes(extension)) return "video";
  if (["mp3", "m4a", "wav", "ogg"].includes(extension)) return "audio";
  return null;
}

function setUploadingState(isUploading) {
  state.isUploading = isUploading;
  sendBtn.disabled = isUploading;
  attachBtn.disabled = isUploading;
  emojiBtn.disabled = isUploading;
  recordBtn.disabled = isUploading;
  sendBtn.textContent = isUploading ? "Sending..." : "Send";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Request failed");
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : null;
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(new Date(timestamp));
}

function formatLastSeen(timestamp) {
  if (!timestamp) return "last seen unavailable";
  const date = new Date(timestamp);
  return `last seen ${new Intl.DateTimeFormat([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date)}`;
}

function timeLeft(expiresAt) {
  const diff = new Date(expiresAt).getTime() - Date.now();
  if (diff <= 0) return "expiring now";
  const hours = Math.floor(diff / 36e5);
  const minutes = Math.floor((diff % 36e5) / 6e4);
  return `${hours}h ${minutes}m left`;
}

function authMediaUrl(message) {
  return message.media_url ? `${message.media_url}?token=${encodeURIComponent(state.token)}` : "";
}

async function deriveCryptoKey(passphrase) {
  const encoder = new TextEncoder();
  const baseKey = await crypto.subtle.importKey("raw", encoder.encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: encoder.encode("wokchat-e2ee-v1"),
      iterations: 120000,
      hash: "SHA-256",
    },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

function normalizeChatKey(passphrase) {
  return String(passphrase || "").normalize("NFKC").trim();
}

async function ensureCryptoKey(passphrase) {
  const rawPassphrase = String(passphrase || "");
  const normalizedPassphrase = normalizeChatKey(rawPassphrase);
  const candidates = [normalizedPassphrase];
  if (rawPassphrase && rawPassphrase !== normalizedPassphrase) {
    candidates.push(rawPassphrase);
  }

  state.cryptoKeys = [];
  for (const candidate of candidates) {
    if (!candidate) continue;
    state.cryptoKeys.push(await deriveCryptoKey(candidate));
  }
  state.cryptoKey = state.cryptoKeys[0] || null;
  sessionStorage.setItem("wokchat_chat_key", normalizedPassphrase);
}

async function encryptForTransport(text) {
  if (!text) return "";
  if (!state.cryptoKey) return text;
  const encoder = new TextEncoder();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, state.cryptoKey, encoder.encode(text));
  const payload = {
    iv: btoa(String.fromCharCode(...iv)),
    data: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
  };
  return `e2ee:${JSON.stringify(payload)}`;
}

async function decryptFromTransport(text) {
  if (!text || !text.startsWith("e2ee:")) return text || "";
  if (!state.cryptoKeys.length) return "Locked message";
  try {
    const payload = JSON.parse(text.slice(5));
    const iv = Uint8Array.from(atob(payload.iv), (char) => char.charCodeAt(0));
    const encrypted = Uint8Array.from(atob(payload.data), (char) => char.charCodeAt(0));
    for (const key of state.cryptoKeys) {
      try {
        const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, encrypted);
        return new TextDecoder().decode(decrypted);
      } catch {}
    }
    return "Wrong chat key";
  } catch {
    return "Wrong chat key";
  }
}

function getMessageTextSync(text) {
  if (!text) return "";
  if (!text.startsWith("e2ee:")) return text;
  return state.cryptoKey ? "Decrypting..." : "Locked message";
}

function updateTypingLabel() {
  typingIndicator.textContent = state.peerTyping && state.peer ? `${state.peer.username} is typing...` : "";
}

function isOwnMessage(message) {
  return state.me && message.sender_id === state.me.id;
}

function visibleMessages() {
  return state.filteredMessages ?? state.messages;
}

async function hydrateMessage(message) {
  const hydrated = { ...message };
  hydrated.display_content = hydrated.is_deleted ? "This message was deleted" : await decryptFromTransport(hydrated.content);
  if (hydrated.reply_to_message) {
    hydrated.reply_to_message = {
      ...hydrated.reply_to_message,
      display_content: await decryptFromTransport(hydrated.reply_to_message.content),
    };
  }
  return hydrated;
}

async function hydrateMessages(messages) {
  return Promise.all(messages.map(hydrateMessage));
}

function updateAuthState(loggedIn) {
  loginShell.classList.toggle("hidden", loggedIn);
  appShell.classList.toggle("hidden", !loggedIn);
  composer.classList.toggle("hidden", !loggedIn || state.currentScreen !== "chat");
}

function openHomeScreen() {
  state.currentScreen = "home";
  homeScreen.classList.remove("hidden");
  chatScreen.classList.add("hidden");
  composer.classList.add("hidden");
}

function openChatScreen() {
  state.currentScreen = "chat";
  homeScreen.classList.add("hidden");
  chatScreen.classList.remove("hidden");
  if (state.token) composer.classList.remove("hidden");
  scheduleRender(true);
  messageInput.focus();
}

function updatePeerStatus() {
  if (!state.peer) {
    peerName.textContent = "Waiting for the other user";
    return;
  }
  const presence = state.presence[state.peer.id] || {};
  peerName.textContent = presence.is_online ? `${state.peer.username} online` : formatLastSeen(presence.last_seen || state.peer.last_seen);
  renderChatList();
}

function updateSecurityBanner() {
  const mismatchExists = state.messages.some((message) => message.display_content === "Wrong chat key");
  const lockedExists = state.messages.some((message) => message.display_content === "Locked message");
  if (mismatchExists) {
    securityBanner.textContent = "Chat key mismatch detected. Use the same chat key on both devices to read messages.";
    securityBanner.classList.remove("hidden");
    return;
  }
  if (lockedExists) {
    securityBanner.textContent = "Encrypted messages are locked until this tab has the chat key.";
    securityBanner.classList.remove("hidden");
    return;
  }
  securityBanner.textContent = "";
  securityBanner.classList.add("hidden");
}

function openConfirmDialog({ title, message, confirmLabel, action }) {
  confirmTitle.textContent = title;
  confirmMessage.textContent = message;
  confirmOkBtn.textContent = confirmLabel;
  state.confirmAction = action;
  confirmOverlay.classList.remove("hidden");
}

function closeConfirmDialog() {
  state.confirmAction = null;
  confirmOverlay.classList.add("hidden");
}

function renderChatList() {
  chatList.innerHTML = "";
  if (!state.me || !state.peer) return;

  const item = document.createElement("button");
  item.type = "button";
  item.className = "chat-list-item";

  const name = document.createElement("span");
  name.className = "chat-list-name";
  name.textContent = state.peer.username;

  const status = document.createElement("span");
  status.className = "chat-list-status";
  const presence = state.presence[state.peer.id] || {};
  const filtered = homeSearch.value.trim().toLowerCase();
  const lastMessage = [...state.messages].reverse().find(Boolean);
  const preview = lastMessage?.is_deleted ? "This message was deleted" : lastMessage?.display_content || lastMessage?.message_type || "";
  status.textContent = presence.is_online ? `Online now${preview ? " • " + preview : ""}` : `${formatLastSeen(presence.last_seen || state.peer.last_seen)}${preview ? " • " + preview : ""}`;

  if (filtered && !`${state.peer.username} ${preview}`.toLowerCase().includes(filtered)) return;

  item.appendChild(name);
  item.appendChild(status);
  item.addEventListener("click", openChatScreen);
  chatList.appendChild(item);
}

async function mergeMessage(updatedMessage) {
  const hydratedMessage = await hydrateMessage(updatedMessage);
  const mergeInto = (messages) =>
    messages.map((message) => (message.id === hydratedMessage.id ? { ...message, ...hydratedMessage } : message));
  state.messages = mergeInto(state.messages);
  if (state.filteredMessages) {
    state.filteredMessages = mergeInto(state.filteredMessages);
  }
}

async function appendMessage(message) {
  const hydratedMessage = await hydrateMessage(message);
  if (state.messages.some((item) => item.id === hydratedMessage.id)) {
    await mergeMessage(hydratedMessage);
  } else {
    state.messages.push(hydratedMessage);
  }
  state.filteredMessages = null;
  renderChatList();
  updateSecurityBanner();
  if (state.currentScreen === "chat") scheduleRender(true);
}

function removeMessage(messageId) {
  state.messages = state.messages.filter((message) => message.id !== messageId);
  if (state.filteredMessages) {
    state.filteredMessages = state.filteredMessages.filter((message) => message.id !== messageId);
  }
  renderChatList();
  updateSecurityBanner();
}

async function applyConversation(conversation) {
  state.messages = await hydrateMessages(conversation.messages);
  state.filteredMessages = null;
  conversation.participants.forEach((user) => {
    state.presence[user.id] = state.presence[user.id] || {};
    state.presence[user.id].last_seen = user.last_seen;
    state.presence[user.id].is_online = user.is_online;
  });
  state.peer = conversation.participants.find((user) => user.id !== state.me.id) || null;
  chatTitle.textContent = state.peer ? state.peer.username : "Secure room";
  profileName.textContent = state.me ? state.me.username : "Signed in";
  welcomeLabel.textContent = state.me ? `Welcome, ${state.me.username}` : "Welcome";
  updatePeerStatus();
  renderChatList();
  updateSecurityBanner();
  scheduleRender();
}

async function refreshConversation() {
  if (!state.token) return;
  const conversation = await api("/api/messages");
  await applyConversation(conversation);
  if (conversation.messages.some((message) => message.receiver_id === state.me.id && !message.is_read && !message.is_deleted)) {
    await api("/api/messages/read", { method: "POST" });
  }
}

function clearPendingFile() {
  if (state.previewUrl) {
    URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
  }
  state.pendingFile = null;
  attachmentPreview.innerHTML = "";
  attachmentPreview.classList.add("hidden");
  composerNote.textContent = "Text, image, video, or voice message";
  fileInput.value = "";
}

function renderPendingFile() {
  attachmentPreview.innerHTML = "";
  if (!state.pendingFile) {
    attachmentPreview.classList.add("hidden");
    composerNote.textContent = "Text, image, video, or voice message";
    return;
  }
  attachmentPreview.classList.remove("hidden");
  composerNote.textContent = `Ready to send ${detectFileKind(state.pendingFile) || "attachment"}`;
  const chip = document.createElement("div");
  chip.className = "attachment-chip";
  chip.textContent = `${state.pendingFile.name} - ${Math.max(1, Math.round(state.pendingFile.size / 1024))} KB`;
  attachmentPreview.appendChild(chip);
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  const objectUrl = URL.createObjectURL(state.pendingFile);
  state.previewUrl = objectUrl;
  const fileKind = detectFileKind(state.pendingFile);
  if (fileKind === "image") {
    const img = document.createElement("img");
    img.src = objectUrl;
    img.alt = state.pendingFile.name;
    attachmentPreview.appendChild(img);
  } else if (fileKind === "video") {
    const video = document.createElement("video");
    video.src = objectUrl;
    video.controls = true;
    video.playsInline = true;
    attachmentPreview.appendChild(video);
  } else if (fileKind === "audio") {
    const audio = document.createElement("audio");
    audio.src = objectUrl;
    audio.controls = true;
    attachmentPreview.appendChild(audio);
  }
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "ghost-btn";
  removeBtn.textContent = "Remove attachment";
  removeBtn.addEventListener("click", clearPendingFile);
  attachmentPreview.appendChild(removeBtn);
}

function setReplyTarget(message) {
  state.replyTo = message;
  replyPreview.classList.remove("hidden");
  replyPreview.innerHTML = "";
  const label = document.createElement("div");
  label.textContent = `Replying to ${isOwnMessage(message) ? "yourself" : state.peer?.username || "message"}: ${
    message.is_deleted ? "This message was deleted" : message.display_content || message.message_type
  }`;
  replyPreview.appendChild(label);
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "ghost-btn";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", clearReplyTarget);
  replyPreview.appendChild(cancel);
}

function clearReplyTarget() {
  state.replyTo = null;
  replyPreview.classList.add("hidden");
  replyPreview.innerHTML = "";
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    showToast("Voice recording is not supported in this browser.", "error");
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const chunks = [];
  state.recorderStream = stream;
  state.recorder = new MediaRecorder(stream);
  state.isRecording = true;
  recordBtn.textContent = "Stop";
  composerNote.textContent = "Recording voice note...";
  state.recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  });
  state.recorder.addEventListener("stop", () => {
    const extension = state.recorder.mimeType.includes("ogg") ? "ogg" : "webm";
    state.pendingFile = new File(chunks, `voice-note.${extension}`, {
      type: state.recorder.mimeType || `audio/${extension}`,
    });
    renderPendingFile();
    state.recorderStream.getTracks().forEach((track) => track.stop());
    state.recorderStream = null;
    state.recorder = null;
    state.isRecording = false;
    recordBtn.textContent = "Mic";
  });
  state.recorder.start();
}

function stopRecording() {
  if (state.recorder && state.isRecording) state.recorder.stop();
}

function sendTyping(isTyping) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN || !state.peer) return;
  if (state.localTypingSent === isTyping) return;
  state.localTypingSent = isTyping;
  state.socket.send(JSON.stringify({ type: "typing", receiver_id: state.peer.id, is_typing: isTyping }));
}

async function deleteMessage(messageId, deleteForEveryone) {
  try {
    await api(`/api/messages/${messageId}`, {
      method: "DELETE",
      body: JSON.stringify({ delete_for_everyone: deleteForEveryone }),
    });
    state.activeMenuId = null;
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function toggleReaction(messageId, emoji) {
  try {
    const updatedMessage = await api(`/api/messages/${messageId}/reactions`, {
      method: "POST",
      body: JSON.stringify({ emoji }),
    });
    mergeMessage(updatedMessage);
    state.activeMenuId = null;
    scheduleRender();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function clearChat() {
  closeConfirmDialog();
  try {
    const result = await api("/api/messages", { method: "DELETE" });
    chatMenu.classList.add("hidden");
    profileMenu.classList.add("hidden");
    state.messages = [];
    state.filteredMessages = null;
    state.activeMenuId = null;
    clearReplyTarget();
    clearPendingFile();
    renderChatList();
    scheduleRender();
    showToast(`Cleared ${result.deleted_count} messages for your account.`);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function insertEmoji(emoji) {
  const start = messageInput.selectionStart ?? messageInput.value.length;
  const end = messageInput.selectionEnd ?? messageInput.value.length;
  messageInput.value = `${messageInput.value.slice(0, start)}${emoji}${messageInput.value.slice(end)}`;
  messageInput.focus();
  const cursor = start + emoji.length;
  messageInput.setSelectionRange(cursor, cursor);
  messageInput.dispatchEvent(new Event("input"));
}

function openLightbox(src, alt) {
  lightboxImage.src = src;
  lightboxImage.alt = alt || "Expanded image";
  lightbox.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  lightbox.classList.add("hidden");
  lightboxImage.src = "";
  document.body.style.overflow = "";
}

function buildReceipt(message) {
  if (!isOwnMessage(message)) return null;
  const receipt = document.createElement("span");
  receipt.className = `status-icon ${message.is_read ? "read" : ""}`.trim();
  receipt.textContent = message.is_read || message.is_delivered ? "\u2713\u2713" : "\u2713";
  receipt.title = message.is_read ? "Read" : message.is_delivered ? "Delivered" : "Sent";
  return receipt;
}

function renderAttachment(message) {
  if (!message.media_url || message.is_deleted) return null;
  const wrapper = document.createElement("div");
  wrapper.className = "message-media";
  const url = authMediaUrl(message);
  if (message.message_type === "image") {
    const img = document.createElement("img");
    img.src = url;
    img.alt = message.media_name || "Image attachment";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("click", () => openLightbox(url, img.alt));
    img.addEventListener(
      "error",
      () => {
        wrapper.innerHTML = "";
        const fallback = document.createElement("div");
        fallback.className = "deleted-label";
        fallback.textContent = "Image unavailable";
        wrapper.appendChild(fallback);
      },
      { once: true },
    );
    wrapper.appendChild(img);
  } else if (message.message_type === "video") {
    const video = document.createElement("video");
    video.src = url;
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    wrapper.appendChild(video);
  } else if (message.message_type === "audio") {
    const audio = document.createElement("audio");
    audio.src = url;
    audio.controls = true;
    audio.preload = "none";
    wrapper.appendChild(audio);
  }
  return wrapper;
}

function buildReactionBar(message) {
  if (message.is_deleted) return null;
  const bar = document.createElement("div");
  bar.className = "reaction-bar";
  const reactions = message.reactions || [];
  reactions.forEach((reaction) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `reaction-chip ${reaction.reacted_by_me ? "active" : ""}`.trim();
    button.textContent = `${reaction.emoji} ${reaction.count}`;
    button.addEventListener("click", () => toggleReaction(message.id, reaction.emoji));
    bar.appendChild(button);
  });
  return reactions.length ? bar : null;
}

function buildMessageMenu(message, row) {
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "message-menu-trigger";
  trigger.textContent = "\u25BE";
  trigger.setAttribute("aria-label", "Message options");
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    state.activeMenuId = state.activeMenuId === message.id ? null : message.id;
    scheduleRender();
  });

  const menu = document.createElement("div");
  menu.className = `message-menu ${state.activeMenuId === message.id ? "" : "hidden"}`.trim();

  const addMenuButton = (label, onClick) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      await onClick();
    });
    menu.appendChild(button);
  };

  if (!message.is_deleted) {
    addMenuButton("Reply", async () => {
      setReplyTarget(message);
      state.activeMenuId = null;
      scheduleRender();
    });
    COMMON_REACTIONS.forEach((emoji) => {
      addMenuButton(`React ${emoji}`, async () => toggleReaction(message.id, emoji));
    });
  }
  addMenuButton("Delete for me", async () => deleteMessage(message.id, false));
  if (isOwnMessage(message) && !message.is_deleted) {
    addMenuButton("Delete for everyone", async () => deleteMessage(message.id, true));
  }

  row.appendChild(trigger);
  row.appendChild(menu);
}

function bindHoldMenu(row, message) {
  const openMenu = () => {
    state.activeMenuId = message.id;
    scheduleRender();
  };
  row.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    clearTimeout(state.holdTimer);
    state.holdTimer = window.setTimeout(openMenu, 420);
  });
  ["pointerup", "pointerleave", "pointercancel"].forEach((eventName) =>
    row.addEventListener(eventName, () => clearTimeout(state.holdTimer)),
  );
}

function renderMessages(scrollToBottom = false) {
  state.renderQueued = false;
  feed.innerHTML = "";
  const messages = visibleMessages();
  if (!messages.length) {
    feed.appendChild(emptyState);
    return;
  }

  messages.forEach((message) => {
    const row = document.createElement("article");
    const mine = isOwnMessage(message);
    row.className = `message-row ${mine ? "mine" : "theirs"} ${state.activeMenuId === message.id ? "menu-open" : ""}`.trim();

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    if (message.reply_to_message) {
      const reply = document.createElement("div");
      reply.className = "reply-snippet";
      reply.textContent = message.reply_to_message.display_content || message.reply_to_message.message_type;
      bubble.appendChild(reply);
    }

    const attachment = renderAttachment(message);
    if (attachment) bubble.appendChild(attachment);

    const caption = document.createElement("div");
    caption.className = message.is_deleted ? "message-caption deleted-label" : "message-caption";
    caption.textContent = message.is_deleted ? "This message was deleted" : message.display_content;
    if (message.is_deleted || message.display_content) bubble.appendChild(caption);

    row.appendChild(bubble);

    const reactionBar = buildReactionBar(message);
    if (reactionBar) row.appendChild(reactionBar);

    const meta = document.createElement("div");
    meta.className = "message-meta";
    const time = document.createElement("span");
    time.textContent = formatTime(message.timestamp);
    meta.appendChild(time);
    const mediaLabel = !message.is_deleted && message.message_type !== "text" ? document.createElement("span") : null;
    if (mediaLabel) {
      mediaLabel.textContent = `${message.message_type} message`;
      meta.appendChild(mediaLabel);
    }
    const receipt = buildReceipt(message);
    if (receipt) meta.appendChild(receipt);
    row.appendChild(meta);

    buildMessageMenu(message, row);
    bindHoldMenu(row, message);
    feed.appendChild(row);
  });

  if (scrollToBottom) {
    feed.scrollTop = feed.scrollHeight;
    return;
  }
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 140;
  if (nearBottom) feed.scrollTop = feed.scrollHeight;
}

function scheduleRender(scrollToBottom = false) {
  if (state.renderQueued) return;
  state.renderQueued = true;
  window.requestAnimationFrame(() => renderMessages(scrollToBottom));
}

function connectSocket() {
  if (!state.token) return;
  if (state.socket) {
    state.socket.onclose = null;
    state.socket.close();
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.socket = new WebSocket(`${protocol}://${window.location.host}/ws?token=${encodeURIComponent(state.token)}`);
  state.socket.addEventListener("open", () => {
    connectionPill.textContent = "Live";
    connectionPill.classList.add("online");
  });
  state.socket.addEventListener("close", () => {
    connectionPill.textContent = "Reconnecting";
    connectionPill.classList.remove("online");
    window.setTimeout(() => {
      if (state.token) connectSocket();
    }, 2000);
  });
  state.socket.addEventListener("message", async (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "message.created") {
      await appendMessage(payload.message);
      if (payload.message.receiver_id === state.me.id && !payload.message.is_deleted) {
        await api("/api/messages/read", { method: "POST" });
      }
    }
    if (payload.type === "message.updated") {
      await mergeMessage(payload.message);
      renderChatList();
      scheduleRender();
    }
    if (payload.type === "messages.read") {
      state.messages = state.messages.map((message) =>
        payload.message_ids.includes(message.id) ? { ...message, is_read: true, is_delivered: true } : message,
      );
      if (state.filteredMessages) {
        state.filteredMessages = state.filteredMessages.map((message) =>
          payload.message_ids.includes(message.id) ? { ...message, is_read: true, is_delivered: true } : message,
        );
      }
      renderChatList();
      scheduleRender();
    }
    if (payload.type === "messages.delivered") {
      state.messages = state.messages.map((message) =>
        payload.message_ids.includes(message.id) ? { ...message, is_delivered: true } : message,
      );
      if (state.filteredMessages) {
        state.filteredMessages = state.filteredMessages.map((message) =>
          payload.message_ids.includes(message.id) ? { ...message, is_delivered: true } : message,
        );
      }
      scheduleRender();
    }
    if (payload.type === "presence.updated") {
      state.presence[payload.user_id] = {
        ...(state.presence[payload.user_id] || {}),
        is_online: payload.is_online,
        last_seen: payload.last_seen,
      };
      updatePeerStatus();
    }
    if (payload.type === "typing.updated" && state.peer && payload.user_id === state.peer.id) {
      state.peerTyping = payload.is_typing;
      updateTypingLabel();
    }
    if (payload.type === "message.deleted") {
      if (!payload.delete_for_everyone && payload.deleted_by === state.me?.id) {
        removeMessage(payload.deleted_message_id);
        scheduleRender();
      }
    }
    if (payload.type === "chat.cleared" && payload.cleared_by === state.me?.id) {
      state.messages = [];
      state.filteredMessages = null;
      state.activeMenuId = null;
      clearReplyTarget();
      clearPendingFile();
      renderChatList();
      scheduleRender();
    }
  });
}

async function bootstrap() {
  applyTheme(state.theme);
  emojiTray.innerHTML = "";
  EMOJI_SHORTCUTS.forEach((emoji) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "emoji-pill";
    button.textContent = emoji;
    button.addEventListener("click", () => insertEmoji(emoji));
    emojiTray.appendChild(button);
  });
  try {
    state.config = await api("/api/config");
    retentionPill.textContent = `${state.config.message_ttl_hours}h auto-delete`;
  } catch {}

  const storedChatKey = sessionStorage.getItem("wokchat_chat_key");
  if (storedChatKey) {
    await ensureCryptoKey(storedChatKey);
  }

  if (!state.token) {
    updateAuthState(false);
    return;
  }

  try {
    state.me = await api("/api/me");
    state.presence[state.me.id] = { ...(state.presence[state.me.id] || {}), is_online: true, last_seen: state.me.last_seen };
    updateAuthState(true);
    openHomeScreen();
    await refreshConversation();
    connectSocket();
  } catch {
    saveToken("");
    updateAuthState(false);
  }
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(authForm);
  const payload = Object.fromEntries(formData.entries());
  try {
    await ensureCryptoKey(String(payload.chat_key || ""));
    delete payload.chat_key;
    const result = await api("/api/login", { method: "POST", body: JSON.stringify(payload) });
    saveToken(result.access_token);
    state.me = await api("/api/me");
    state.presence[state.me.id] = { ...(state.presence[state.me.id] || {}), is_online: true, last_seen: state.me.last_seen };
    updateAuthState(true);
    openHomeScreen();
    await refreshConversation();
    connectSocket();
    authForm.reset();
    showToast("Secure session started.");
  } catch (error) {
    showToast(error.message, "error");
  }
});

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.peer) {
    showToast("The other user is not available yet.", "error");
    return;
  }
  const content = messageInput.value.trim();
  try {
    if (state.pendingFile) {
      setUploadingState(true);
      const body = new FormData();
      body.append("receiver_id", String(state.peer.id));
      body.append("content", content ? await encryptForTransport(content) : "");
      if (state.replyTo) body.append("reply_to_message_id", String(state.replyTo.id));
      body.append("file", state.pendingFile);
      const message = await api("/api/messages/media", { method: "POST", body });
      await appendMessage(message);
      clearPendingFile();
      clearReplyTarget();
      messageInput.value = "";
      sendTyping(false);
      setUploadingState(false);
      messageInput.style.height = "auto";
      return;
    }
    if (!content) return;
    const message = await api("/api/messages", {
      method: "POST",
      body: JSON.stringify({
        receiver_id: state.peer.id,
        content: await encryptForTransport(content),
        reply_to_message_id: state.replyTo?.id ?? null,
      }),
    });
    await appendMessage(message);
    clearReplyTarget();
    messageInput.value = "";
    sendTyping(false);
    messageInput.style.height = "auto";
  } catch (error) {
    setUploadingState(false);
    showToast(error.message, "error");
  }
});

attachBtn.addEventListener("click", () => fileInput.click());
emojiBtn.addEventListener("click", () => emojiTray.classList.toggle("hidden"));
profileBtn.addEventListener("click", () => profileMenu.classList.toggle("hidden"));
chatMenuBtn.addEventListener("click", () => chatMenu.classList.toggle("hidden"));
backBtn.addEventListener("click", openHomeScreen);
homeSearch.addEventListener("input", renderChatList);

fileInput.addEventListener("change", () => {
  const [file] = fileInput.files;
  if (!file) return;
  const maxMb = state.config.max_upload_size_mb || 20;
  if (file.size > maxMb * 1024 * 1024) {
    showToast(`File is too large. Max allowed is ${maxMb} MB.`, "error");
    fileInput.value = "";
    return;
  }
  const kind = detectFileKind(file);
  if (!kind) {
    showToast("Only images, videos, and audio files are supported.", "error");
    fileInput.value = "";
    return;
  }
  state.pendingFile = file;
  renderPendingFile();
});

recordBtn.addEventListener("click", async () => {
  try {
    if (state.isRecording) return stopRecording();
    await startRecording();
  } catch (error) {
    showToast(error.message || "Could not record audio.", "error");
  }
});

clearChatBtn.addEventListener("click", () =>
  openConfirmDialog({
    title: "Clear chat for your account?",
    message: "This removes the current conversation from your account only. The other person will still keep their messages.",
    confirmLabel: "Clear chat",
    action: clearChat,
  }),
);
chatClearBtn.addEventListener("click", () =>
  openConfirmDialog({
    title: "Clear chat for your account?",
    message: "This removes the current conversation from your account only. The other person will still keep their messages.",
    confirmLabel: "Clear chat",
    action: clearChat,
  }),
);
themeToggle.addEventListener("click", () => {
  applyTheme(state.theme === "dark" ? "light" : "dark");
  profileMenu.classList.add("hidden");
});
logoutBtn.addEventListener("click", () => {
  saveToken("");
  sessionStorage.removeItem("wokchat_chat_key");
  state.cryptoKey = null;
  state.me = null;
  state.peer = null;
  state.messages = [];
  state.filteredMessages = null;
  state.activeMenuId = null;
  profileMenu.classList.add("hidden");
  clearPendingFile();
  clearReplyTarget();
  if (state.socket) {
    state.socket.onclose = null;
    state.socket.close();
  }
  connectionPill.textContent = "Offline";
  connectionPill.classList.remove("online");
  chatList.innerHTML = "";
  updateAuthState(false);
});

messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
  sendTyping(Boolean(messageInput.value.trim()));
  clearTimeout(state.typingTimeout);
  state.typingTimeout = setTimeout(() => sendTyping(false), 1200);
});

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim();
  clearTimeout(state.searchTimeout);
  if (!query) {
    state.filteredMessages = null;
    scheduleRender();
    return;
  }
  state.searchTimeout = setTimeout(() => {
    const lowered = query.toLowerCase();
    state.filteredMessages = state.messages.filter((message) =>
      `${message.display_content || ""} ${message.reply_to_message?.display_content || ""}`.toLowerCase().includes(lowered),
    );
    scheduleRender();
  }, 120);
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".topbar-actions")) {
    profileMenu.classList.add("hidden");
    chatMenu.classList.add("hidden");
  }
  if (!event.target.closest(".message-row")) {
    state.activeMenuId = null;
    scheduleRender();
  }
  if (!event.target.closest(".emoji-tray") && !event.target.closest("#emoji-btn")) {
    emojiTray.classList.add("hidden");
  }
});

confirmCancelBtn.addEventListener("click", closeConfirmDialog);
confirmOkBtn.addEventListener("click", async () => {
  if (!state.confirmAction) return;
  const action = state.confirmAction;
  await action();
});
confirmOverlay.addEventListener("click", (event) => {
  if (event.target === confirmOverlay) closeConfirmDialog();
});

lightbox.addEventListener("click", (event) => {
  if (event.target === lightbox) closeLightbox();
});
lightboxClose.addEventListener("click", closeLightbox);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !lightbox.classList.contains("hidden")) closeLightbox();
});

bootstrap();
