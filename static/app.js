// Conversation state
const messages = [
  { role: "system", content: "You are a helpful assistant who gives short, clear answers." }
];
let isMuted = false;
let appState = "online"; // 'online', 'thinking', 'talking'
let abortController = null;

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

// Canvas context
const ctx = canvas.getContext("2d");

// Web Audio API State
let audioCtx = null;
let analyser = null;
let source = null;
let dataArray = null;
let bufferLength = 0;
let audioInitialized = false;

// Speech Recognition (STT) Setup
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isListening = false;

// Initialize Speech Recognition if supported
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = true; // Stay active continuously
  recognition.interimResults = true; // Return real-time results
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add("listening");
    sttStatusBar.innerText = "Listening... Speak now (click mic again to turn off)";
    sttStatusBar.style.display = "block";
    statusDot.className = "pulse-dot recording";
    statusText.innerText = "Mic Active";
  };

  recognition.onresult = (event) => {
    let fullTranscript = '';
    let interimTranscript = '';

    for (let i = 0; i < event.results.length; ++i) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        fullTranscript += transcript;
      } else {
        interimTranscript += transcript;
      }
    }

    userInput.value = fullTranscript;
    
    if (interimTranscript) {
      sttStatusBar.innerText = "Hearing: " + interimTranscript;
      userInput.value = fullTranscript + interimTranscript;
    } else {
      sttStatusBar.innerText = "Listening... (click mic again to save and stop)";
    }
  };

  recognition.onerror = (event) => {
    if (event.error === 'no-speech') return; // Ignore silent pause errors
    console.error("Speech recognition error:", event.error);
    sttStatusBar.innerText = "Transcription error: " + event.error;
    stopListening();
  };

  recognition.onend = () => {
    // If the browser stopped it automatically but we want it to stay active until clicked:
    if (isListening) {
      try {
        recognition.start();
      } catch (err) {
        console.warn("Speech recognition restart failed:", err);
      }
    } else {
      stopListening();
    }
  };
} else {
  console.warn("SpeechRecognition is not supported in this browser.");
  micBtn.style.opacity = "0.5";
  micBtn.title = "Voice Input Unsupported in this browser";
}

function stopListening() {
  isListening = false;
  micBtn.classList.remove("listening");
  sttStatusBar.innerText = "Mic stopped. Edit or press Send.";
  setTimeout(() => {
    if (!isListening) {
      sttStatusBar.style.display = "none";
      setStatus("online");
    }
  }, 2500);
  if (recognition) {
    recognition.stop();
  }
}

// Sidebar toggle logic
toggleSidebarBtn.addEventListener("click", () => {
  container.classList.toggle("sidebar-collapsed");
});

// Toggle Mic Listener
micBtn.addEventListener("click", () => {
  if (!recognition) {
    alert("Speech recognition is not supported in this browser. Please try Google Chrome or MS Edge.");
    return;
  }
  
  if (isListening) {
    stopListening();
  } else {
    // Initialize audio context
    initAudio();
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    
    // Stop current bot speech playback
    botAudio.pause();
    botAudio.currentTime = 0;
    
    recognition.start();
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
    analyser.connect(audioCtx.destination);
    
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
  
  if (audioInitialized && !botAudio.paused) {
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
  
  // Escape HTML tags to prevent XSS
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  
  // Blockquotes (e.g. > Quote)
  html = html.replace(/^&gt;\s+(.*)$/gm, '<blockquote>$1</blockquote>');
  
  // Headings (e.g. ### Header 3)
  html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.*)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.*)$/gm, '<h1>$1</h1>');
  
  // Bold (e.g. **text**)
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  
  // Italic (e.g. *text*)
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/_(.*?)_/g, '<em>$1</em>');
  
  // Bullet lists (e.g. - item or * item)
  html = html.replace(/^[\*-]\s+(.*)$/gm, '<li>$1</li>');
  
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  
  return html;
}

// Append Bubble
function appendMessage(role, content, audioUrl = null) {
  // Hide welcome box on first message
  const welcomeBox = document.querySelector(".welcome-box");
  if (welcomeBox) {
    welcomeBox.remove();
  }
  
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

  // Always show the play option at the end of assistant responses
  if (role === "assistant") {
    const playBtn = document.createElement("button");
    playBtn.className = "msg-play-btn";
    
    if (audioUrl) {
      playBtn.title = "Play audio response";
      playBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span>Listen</span>
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
        <span>Audio Unavailable</span>
      `;
    }
    contentDiv.appendChild(playBtn);
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
  
  const welcomeBox = document.querySelector(".welcome-box");
  if (welcomeBox) {
    welcomeBox.remove();
  }
  
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

// Form Submit Handler
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  
  // If the assistant is busy thinking or speaking, treat form submission as a Stop command
  if (appState === "thinking" || appState === "talking") {
    handleStop();
    return;
  }
  
  const text = userInput.value.trim();
  if (!text) return;
  
  initAudio();
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  
  botAudio.pause();
  botAudio.currentTime = 0;
  
  appendMessage("user", text);
  messages.push({ role: "user", content: text });
  
  userInput.value = "";
  
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
      body: JSON.stringify({ messages })
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

// New Chat button clears memory
clearBtn.addEventListener("click", () => {
  botAudio.pause();
  botAudio.currentTime = 0;
  
  messages.length = 1; // Keep only system prompt
  
  // Re-render welcome box
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
  setStatus("online");
});



