// Conversation state
const messages = [
  { role: "system", content: "You are a helpful assistant who gives short, clear answers." }
];
let isMuted = false;
let appState = "online"; // 'online', 'thinking', 'talking'
let abortController = null;

// Unique Session ID generator
function generateUUID() {
  return 'session-' + Math.random().toString(36).substring(2, 15) + '-' + Math.random().toString(36).substring(2, 15);
}

let activeSessionId = localStorage.getItem("active_session_id");
if (!activeSessionId) {
  activeSessionId = generateUUID();
  localStorage.setItem("active_session_id", activeSessionId);
}

function showWelcomeBox() {
  chatMessagesContainer.innerHTML = `
    <div class="welcome-box">
      <div class="welcome-icon">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <h1>How can I help you today?</h1>
      <p class="welcome-subtitle">Ask a question or click the microphone to speak with Grok AI.</p>
    </div>
  `;
}

function removeWelcomeBox() {
  const welcomeBox = document.querySelector(".welcome-box");
  if (welcomeBox) {
    welcomeBox.remove();
  }
}

async function loadSessions() {
  try {
    const response = await fetch("/api/sessions");
    const sessions = await response.json();
    const container = document.getElementById("chat-history-list");
    if (!container) return;
    
    container.innerHTML = "";
    
    if (sessions.length === 0) {
      container.innerHTML = '<div class="history-item empty">No past chats</div>';
      return;
    }
    
    sessions.forEach(session => {
      const item = document.createElement("div");
      item.className = "history-item";
      if (session.id === activeSessionId) {
        item.classList.add("active");
      }
      
      const textSpan = document.createElement("span");
      textSpan.className = "history-item-text";
      textSpan.innerText = session.title;
      textSpan.addEventListener("click", () => selectSession(session.id));
      
      const deleteBtn = document.createElement("button");
      deleteBtn.className = "history-item-delete-btn";
      deleteBtn.title = "Delete Chat";
      deleteBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 6 5 6 21 6"></polyline>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          <line x1="10" y1="11" x2="10" y2="17"></line>
          <line x1="14" y1="11" x2="14" y2="17"></line>
        </svg>
      `;
      deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteSession(session.id);
      });
      
      item.appendChild(textSpan);
      item.appendChild(deleteBtn);
      container.appendChild(item);
    });
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
}

async function selectSession(sessionId) {
  activeSessionId = sessionId;
  localStorage.setItem("active_session_id", sessionId);
  
  handleStop();
  
  try {
    const response = await fetch(`/api/sessions/${sessionId}`);
    const history = await response.json();
    
    chatMessagesContainer.innerHTML = "";
    messages.length = 1; // Keep only system prompt
    
    if (history.length === 0) {
      showWelcomeBox();
    } else {
      removeWelcomeBox();
      history.forEach(msg => {
        appendMessage(msg.role, msg.content, msg.audio_url);
        messages.push({ role: msg.role, content: msg.content });
      });
    }
    
    loadSessions();
  } catch (err) {
    console.error("Failed to load session messages:", err);
  }
}

async function deleteSession(sessionId) {
  if (!confirm("Are you sure you want to delete this chat session?")) return;
  try {
    await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    if (activeSessionId === sessionId) {
      activeSessionId = generateUUID();
      localStorage.setItem("active_session_id", activeSessionId);
      chatMessagesContainer.innerHTML = "";
      messages.length = 1; // Keep only system prompt
      showWelcomeBox();
    }
    loadSessions();
  } catch (err) {
    console.error("Failed to delete session:", err);
  }
}

const SEND_ICON_HTML = `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"></line>
    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
  </svg>
`;

const STOP_ICON_HTML = `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="2" ry="2" fill="currentColor"></rect>
  </svg>
`;

function setButtonState(state) {
  if (state === "stop") {
    sendBtn.innerHTML = STOP_ICON_HTML;
    sendBtn.classList.add("stop-state");
    sendBtn.title = "Stop generating/speaking";
  } else {
    sendBtn.innerHTML = SEND_ICON_HTML;
    sendBtn.classList.remove("stop-state");
    sendBtn.title = "Send message";
  }
}

function handleStop() {
  if (abortController) {
    abortController.abort();
    abortController = null;
    console.log("Fetch request aborted.");
  }
  botAudio.pause();
  botAudio.currentTime = 0;
  removeTyping();
  setStatus("online");
}

// DOM Elements
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const chatMessagesContainer = document.getElementById("chat-messages-container");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const muteBtn = document.getElementById("mute-btn");
const volumeIcon = document.getElementById("volume-icon");
const muteLabel = document.getElementById("mute-label");
const clearBtn = document.getElementById("clear-btn");
const toggleSidebarBtn = document.getElementById("toggle-sidebar-btn");
const sidebar = document.getElementById("sidebar");
const container = document.querySelector(".claude-container");
const botAudio = document.getElementById("bot-audio");
const statusText = document.getElementById("status-text");
const statusDot = document.getElementById("status-dot");
const visualizerWrapper = document.getElementById("visualizer-wrapper");
const canvas = document.getElementById("visualizer-canvas");
const sttStatusBar = document.getElementById("stt-status-text");
const modelIndicator = document.getElementById("model-indicator");

// File Attachment Elements & State
const fileAttachment = document.getElementById("file-attachment");
const attachBtn = document.getElementById("attach-btn");
const attachmentPreview = document.getElementById("attachment-preview");
let selectedFile = null;

// Canvas context
const ctx = canvas.getContext("2d");

// Web Audio API State
let audioCtx = null;
let analyser = null;
let source = null;
let dataArray = null;
let bufferLength = 0;
let audioInitialized = false;

// Speech Recognition (STT) State
let isListening = false;
let mediaRecorder = null;
let audioChunks = [];
let micStream = null;
let micSource = null;

async function startListening() {
  initAudio();
  if (audioCtx && audioCtx.state === 'suspended') {
    await audioCtx.resume();
  }
  
  // Stop current bot speech playback
  botAudio.pause();
  botAudio.currentTime = 0;
  
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    // Connect mic stream to analyser so visualizer moves
    if (audioInitialized && audioCtx) {
      micSource = audioCtx.createMediaStreamSource(micStream);
      micSource.connect(analyser);
    }
    
    audioChunks = [];
    let options = { mimeType: 'audio/webm' };
    if (!MediaRecorder.isTypeSupported('audio/webm')) {
      options = { mimeType: 'audio/ogg' };
    }
    
    mediaRecorder = new MediaRecorder(micStream, options);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };
    
    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
      
      // Check if audio is valid
      if (!audioBlob || audioBlob.size === 0) {
        sttStatusBar.innerText = "No speech detected. Try again.";
        setStatus("online");
        return;
      }
      
      sttStatusBar.innerText = "Transcribing voice...";
      sttStatusBar.style.display = "block";
      setStatus("thinking");
      
      try {
        const formData = new FormData();
        formData.append("file", audioBlob, "voice.webm");
        
        const response = await fetch("/api/transcribe", {
          method: "POST",
          body: formData
        });
        
        if (!response.ok) {
          const errorDetail = await response.json().catch(() => ({}));
          throw new Error(errorDetail.detail || `Transcription request failed: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        if (data.transcript && data.transcript.trim()) {
          userInput.value = data.transcript;
          sttStatusBar.innerText = "Transcribed: " + data.transcript;
          
          // Auto-submit the voice text
          setTimeout(() => {
            chatForm.dispatchEvent(new Event('submit'));
          }, 300);
        } else {
          sttStatusBar.innerText = "No speech detected. Try again.";
        }
      } catch (err) {
        console.error("Audio/Transcription error:", err.message);
        sttStatusBar.innerText = "Transcription error: " + err.message;
      } finally {
        setStatus("online");
        setTimeout(() => {
          if (!isListening) sttStatusBar.style.display = "none";
        }, 3000);
      }
    };
    
    mediaRecorder.start();
    isListening = true;
    micBtn.classList.add("listening");
    sttStatusBar.innerText = "Listening... Speak now (click mic again to turn off)";
    sttStatusBar.style.display = "block";
    statusDot.className = "pulse-dot recording";
    statusText.innerText = "Mic Active";
    
  } catch (err) {
    console.error("Microphone access failed:", err);
    alert("Microphone access failed. Please ensure mic permission is granted in your browser settings.");
    stopListening();
  }
}

function stopListening() {
  isListening = false;
  micBtn.classList.remove("listening");
  
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  
  if (micStream) {
    micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }
  
  if (micSource) {
    micSource.disconnect();
    micSource = null;
  }
  
  sttStatusBar.innerText = "Mic stopped. Transcribing...";
}

// Sidebar toggle logic
toggleSidebarBtn.addEventListener("click", () => {
  container.classList.toggle("sidebar-collapsed");
});

// File Attachment Event Listeners
if (attachBtn && fileAttachment) {
  attachBtn.addEventListener("click", () => {
    fileAttachment.click();
  });

  fileAttachment.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      selectedFile = e.target.files[0];
      
      // Render file chip preview
      attachmentPreview.innerHTML = `
        <div class="file-chip">
          <span class="file-chip-icon">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
          </span>
          <span class="file-chip-name" title="${selectedFile.name}">${selectedFile.name}</span>
          <button type="button" class="file-chip-remove" id="file-remove-btn" title="Remove file">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      `;
      attachmentPreview.style.display = "flex";
      
      // Wire up remove button
      const removeBtn = document.getElementById("file-remove-btn");
      if (removeBtn) {
        removeBtn.addEventListener("click", () => {
          selectedFile = null;
          fileAttachment.value = "";
          attachmentPreview.innerHTML = "";
          attachmentPreview.style.display = "none";
        });
      }
    }
  });
}

// Toggle Mic Listener
micBtn.addEventListener("click", () => {
  if (isListening) {
    stopListening();
  } else {
    startListening();
  }
});

// Initialize Web Audio API
function initAudio() {
  if (audioInitialized) return;
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    bufferLength = analyser.frequencyBinCount;
    dataArray = new Uint8Array(bufferLength);
    
    source = audioCtx.createMediaElementSource(botAudio);
    source.connect(analyser);
    source.connect(audioCtx.destination);
    
    audioInitialized = true;
    console.log("Audio graph initialized.");
  } catch (err) {
    console.warn("Failed to initialize web audio context:", err);
  }
}

// Waveform Draw Loop (Horizontal Wave)
function draw() {
  requestAnimationFrame(draw);
  
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  if (audioInitialized && (!botAudio.paused || isListening)) {
    analyser.getByteFrequencyData(dataArray);
    visualizerWrapper.style.display = "flex";
    
    // Draw fine horizontal audio wave line
    ctx.beginPath();
    ctx.lineWidth = 2;
    ctx.strokeStyle = '#cc7a5c'; // Warm Clay accent color
    
    const sliceWidth = canvas.width / (bufferLength / 2);
    let x = 0;
    
    for (let i = 0; i < bufferLength / 2; i++) {
      // Scale frequency values
      const val = dataArray[i] / 255.0;
      const y = (canvas.height / 2) + (val * canvas.height / 2 * (i % 2 === 0 ? 1 : -1));
      
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      
      x += sliceWidth;
    }
    
    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();
  } else {
    visualizerWrapper.style.display = "none";
  }
}

draw();

// Set Status dots
function setStatus(state) {
  appState = state;
  statusDot.className = "pulse-dot";
  
  if (state === "thinking") {
    statusDot.classList.add("thinking");
    statusText.innerText = "Thinking...";
    setButtonState("stop");
  } else if (state === "talking") {
    statusDot.classList.add("thinking"); // Orange pulse
    statusText.innerText = "Speaking...";
    setButtonState("stop");
  } else if (state === "recording") {
    statusDot.classList.add("recording");
    statusText.innerText = "Listening...";
    setButtonState("send");
  } else {
    statusDot.classList.add("green");
    statusText.innerText = "Online";
    setButtonState("send");
  }
}

function parseMarkdown(text) {
  if (!text) return "";

  // Split text by fenced code blocks: ```[lang]\n[code]```
  const parts = text.split(/(```[\s\S]*?```)/g);

  return parts.map(part => {
    // If it is a code block
    if (part.startsWith("```")) {
      const match = part.match(/```(\w*)\n([\s\S]*?)```/);
      const lang = match ? match[1] : "";
      let code = match ? match[2] : part.slice(3, -3);
      
      // Escape HTML in code block
      code = code
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
      return `<pre class="code-block ${lang}"><code>${code}</code></pre>`;
    } else {
      // Parse markdown in standard text block
      let html = part
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      
      // Blockquotes (e.g. > Quote)
      html = html.replace(/^&gt;\s+(.*)$/gm, '<blockquote>$1</blockquote>');
      
      // Headings (e.g. #### Header 4)
      html = html.replace(/^#### (.*)$/gm, '<h4>$1</h4>');
      html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>');
      html = html.replace(/^## (.*)$/gm, '<h2>$1</h2>');
      html = html.replace(/^# (.*)$/gm, '<h1>$1</h1>');
      
      // Bold (e.g. **text**)
      html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      
      // Italic: only match *text* and _text_ if they are surrounded by word boundaries
      html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
      html = html.replace(/\b_(.*?)_\b/g, '<em>$1</em>');
      
      // Horizontal rules (e.g. ---)
      html = html.replace(/^---$/gm, '<hr class="msg-divider">');
      
      // Bullet lists (e.g. - item or * item)
      html = html.replace(/^[\*-]\s+(.*)$/gm, '<li>$1</li>');
      
      // Line breaks
      html = html.replace(/\n/g, '<br>');
      
      return html;
    }
  }).join("");
}

// Append Bubble
function appendMessage(role, content, audioUrl = null) {
  removeWelcomeBox();
  
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${role}`;
  
  const avatarDiv = document.createElement("div");
  avatarDiv.className = "avatar";
  avatarDiv.innerText = role === "user" ? "U" : "AI";
  
  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";
  
  const bubbleDiv = document.createElement("div");
  bubbleDiv.className = "bubble";
  bubbleDiv.innerHTML = parseMarkdown(content);
  
  contentDiv.appendChild(bubbleDiv);

  // Always show the action bar at the end of assistant responses
  if (role === "assistant") {
    const actionsDiv = document.createElement("div");
    actionsDiv.className = "msg-actions-row";

    // 1. Copy button
    const copyBtn = document.createElement("button");
    copyBtn.className = "msg-action-btn";
    copyBtn.title = "Copy response text";
    copyBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
    `;
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(content);
      // Temporary checkmark success state
      copyBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      setTimeout(() => {
        copyBtn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        `;
      }, 2000);
    });

    // 2. Read aloud (Replay audio)
    const playBtn = document.createElement("button");
    playBtn.className = "msg-action-btn";
    if (audioUrl) {
      playBtn.title = "Read aloud";
      playBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
      `;
      playBtn.addEventListener("click", () => {
        initAudio();
        if (audioCtx && audioCtx.state === 'suspended') {
          audioCtx.resume();
        }
        botAudio.src = audioUrl;
        botAudio.play();
      });
    } else {
      playBtn.classList.add("disabled");
      playBtn.disabled = true;
      playBtn.title = "Voice response not available";
      playBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.3">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
      `;
    }

    // 3. Positive Feedback (Good response)
    const likeBtn = document.createElement("button");
    likeBtn.className = "msg-action-btn";
    likeBtn.title = "Good response";
    likeBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
      </svg>
    `;
    likeBtn.addEventListener("click", () => {
      likeBtn.classList.toggle("active-like");
      dislikeBtn.classList.remove("active-dislike");
    });

    // 4. Negative Feedback (Bad response)
    const dislikeBtn = document.createElement("button");
    dislikeBtn.className = "msg-action-btn";
    dislikeBtn.title = "Bad response";
    dislikeBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path>
      </svg>
    `;
    dislikeBtn.addEventListener("click", () => {
      dislikeBtn.classList.toggle("active-dislike");
      likeBtn.classList.remove("active-like");
    });

    // 5. Retry button
    const retryBtn = document.createElement("button");
    retryBtn.className = "msg-action-btn";
    retryBtn.title = "Retry response";
    retryBtn.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
      </svg>
    `;
    retryBtn.addEventListener("click", () => {
      handleRetry();
    });

    actionsDiv.appendChild(copyBtn);
    actionsDiv.appendChild(playBtn);
    actionsDiv.appendChild(likeBtn);
    actionsDiv.appendChild(dislikeBtn);
    actionsDiv.appendChild(retryBtn);
    contentDiv.appendChild(actionsDiv);
  }
  
  msgDiv.appendChild(avatarDiv);
  msgDiv.appendChild(contentDiv);
  
  chatMessagesContainer.appendChild(msgDiv);
  chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

// Typing indicators
let typingEl = null;
function showTyping() {
  if (typingEl) return;
  removeWelcomeBox();
  
  typingEl = document.createElement("div");
  typingEl.className = "message assistant";
  
  const avatarDiv = document.createElement("div");
  avatarDiv.className = "avatar";
  avatarDiv.innerText = "AI";
  
  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";
  
  const bubbleDiv = document.createElement("div");
  bubbleDiv.className = "bubble";
  
  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  indicator.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;
  
  bubbleDiv.appendChild(indicator);
  contentDiv.appendChild(bubbleDiv);
  typingEl.appendChild(avatarDiv);
  typingEl.appendChild(contentDiv);
  
  chatMessagesContainer.appendChild(typingEl);
  chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

function removeTyping() {
  if (typingEl) {
    typingEl.remove();
    typingEl = null;
  }
}

async function triggerChatRequest() {
  showTyping();
  setStatus("thinking");
  
  try {
    abortController = new AbortController();
    const response = await fetch("/api/chat", {
      method: "POST",
      signal: abortController.signal,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        session_id: activeSessionId,
        messages: messages
      })
    });
    
    removeTyping();
    
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Server error occurred");
    }
    
    const data = await response.json();
    abortController = null;
    
    appendMessage("assistant", data.text, data.audio_url);
    messages.push({ role: "assistant", content: data.text });
    loadSessions(); // Refresh sidebar title if it's the first message
    
    if (data.audio_url && !isMuted) {
      botAudio.src = data.audio_url;
      botAudio.play().catch(err => {
        console.warn("Autoplay blocked:", err);
        setStatus("online");
      });
    } else {
      setStatus("online");
    }
    
  } catch (err) {
    removeTyping();
    setStatus("online");
    
    if (err.name === 'AbortError') {
      console.log("Fetch request successfully aborted by the user.");
      return;
    }
    
    appendMessage("assistant", `Error: ${err.message}`);
  }
}

async function handleRetry() {
  // Find user's last message index
  let lastUserMsgIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUserMsgIdx = i;
      break;
    }
  }
  if (lastUserMsgIdx === -1) return;

  // Pop all messages after the user's last message (removes the last assistant response)
  while (messages.length > lastUserMsgIdx + 1) {
    messages.pop();
  }

  // Remove the last assistant message element from the DOM
  const assistantMsgElements = document.querySelectorAll(".message.assistant");
  if (assistantMsgElements.length > 0) {
    assistantMsgElements[assistantMsgElements.length - 1].remove();
  }

  // Stop bot audio playback if speaking
  botAudio.pause();
  botAudio.currentTime = 0;

  // Run the chat query again
  await triggerChatRequest();
}

// Form Submit Handler
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  
  // If the assistant is busy thinking or speaking, treat form submission as a Stop command
  if (appState === "thinking" || appState === "talking") {
    handleStop();
    return;
  }
  
  const text = userInput.value.trim();
  if (!text && !selectedFile) return;
  
  initAudio();
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  
  botAudio.pause();
  botAudio.currentTime = 0;
  
  // Handle file attachment first if selected
  let messageContent = text;
  let fileExtractedText = "";
  let attachedName = "";
  
  if (selectedFile) {
    setStatus("thinking");
    sttStatusBar.innerText = `Uploading and extracting ${selectedFile.name}...`;
    sttStatusBar.style.display = "block";
    
    try {
      const uploadData = new FormData();
      uploadData.append("file", selectedFile);
      
      const uploadResponse = await fetch("/api/upload", {
        method: "POST",
        body: uploadData
      });
      
      if (!uploadResponse.ok) {
        const errData = await uploadResponse.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to extract file content.");
      }
      
      const uploadResult = await uploadResponse.json();
      fileExtractedText = uploadResult.extracted_text;
      attachedName = uploadResult.filename;
      
      sttStatusBar.innerText = "File content extracted successfully!";
      setTimeout(() => { sttStatusBar.style.display = "none"; }, 2000);
    } catch (err) {
      console.error(err);
      alert("File processing failed: " + err.message);
      sttStatusBar.style.display = "none";
      setStatus("online");
      return;
    }
  }
  
  // Construct final user content
  let bubbleContent = text;
  if (attachedName) {
    bubbleContent = `📎 **Attached File:** ${attachedName}` + (text ? `\n\n${text}` : "\n\nPlease summarize this file.");
    
    // Incorporate extracted text into context message
    messageContent = `[Attached File Content: ${attachedName}]\n${fileExtractedText}\n\nUser Message: ${text || "Please summarize this file."}`;
  }
  
  appendMessage("user", bubbleContent);
  messages.push({ role: "user", content: messageContent });
  
  // Clear input and attachments
  userInput.value = "";
  if (selectedFile) {
    selectedFile = null;
    fileAttachment.value = "";
    attachmentPreview.innerHTML = "";
    attachmentPreview.style.display = "none";
  }
  
  await triggerChatRequest();
});

// Audio event updates
botAudio.addEventListener("play", () => {
  setStatus("talking");
});

botAudio.addEventListener("pause", () => {
  setStatus("online");
});

botAudio.addEventListener("ended", () => {
  setStatus("online");
});

// Toggle Mute Audio
muteBtn.addEventListener("click", () => {
  isMuted = !isMuted;
  if (isMuted) {
    muteBtn.classList.add("muted");
    muteLabel.innerText = "Audio Off";
    volumeIcon.innerHTML = `
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
      <line x1="23" y1="9" x2="17" y2="15"></line>
      <line x1="17" y1="9" x2="23" y2="15"></line>
    `;
    botAudio.pause();
  } else {
    muteBtn.classList.remove("muted");
    muteLabel.innerText = "Audio On";
    volumeIcon.innerHTML = `
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
    `;
  }
});

// New Chat button clears memory and starts a new session
clearBtn.addEventListener("click", () => {
  activeSessionId = generateUUID();
  localStorage.setItem("active_session_id", activeSessionId);
  
  handleStop();
  
  messages.length = 1; // Keep only system prompt
  chatMessagesContainer.innerHTML = "";
  showWelcomeBox();
  setStatus("online");
  loadSessions();
});

// Initial Load on Page Startup
loadSessions();
if (activeSessionId) {
  selectSession(activeSessionId);
} else {
  showWelcomeBox();
}



