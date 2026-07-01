# Python CLI Chatbot: OpenRouter & Murf AI TTS

A beginner-friendly, minimal command-line interface (CLI) chatbot built in Python. It uses **OpenRouter** (configured with xAI's Grok AI model by default) to generate conversational responses and **Murf AI** to convert the text responses into lifelike speech, playing the audio automatically.

## How It Works
1. **User Input:** You type a message in the terminal.
2. **Text Generation (The Thinking):** The message is sent to OpenRouter, where **Grok AI** (or another model of your choice) processes it and generates a short, clear reply.
3. **Speech Synthesis (The Speaking):** The text reply is sent to **Murf AI**, which converts the text to a high-quality audio file.
4. **Playback:** The audio is downloaded and played automatically in the background through your speaker using `pygame`.

---

## Prerequisites
- **Python 3.8+** installed.
- API Keys:
  - **OpenRouter API Key** (Get one from [OpenRouter](https://openrouter.ai/))
  - **Murf AI API Key** (Get one from [Murf AI Developer Dashboard](https://murf.ai/))

---

## Installation

1. **Clone or navigate** to the project directory:
   ```bash
   cd ChatBot
   ```

2. **Create and activate a virtual environment** (recommended):
   ```bash
   # On Windows:
   python -m venv .venv
   .venv\Scripts\activate

   # On macOS/Linux:
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Environment Setup

1. Copy the `.env.example` file to create a `.env` file:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your API keys:
   ```env
   OPENROUTER_API_KEY=your_actual_openrouter_api_key
   MURF_API_KEY=your_actual_murf_api_key
   ```
3. *(Optional)* Customize the model or voice settings:
   - `OPENROUTER_MODEL`: Change to another model on OpenRouter (e.g. `meta-llama/llama-3-8b-instruct:free` or `google/gemini-2.5-flash`). Defaults to `x-ai/grok-2`.
   - `MURF_VOICE_ID`: Change to any other Murf voice ID (e.g., `en-US-natalie`).

---

## Running the Chatbot

You can run this project in two modes:

### Option A: Web App Interface (Recommended)
This mode launches a beautiful, dark-themed, glassmorphic webpage with a chat log and an animated Web Audio API glowing orb that visualizes the voice response in real time.

1. Start the FastAPI server:
   ```bash
   python app.py
   ```
2. Open your browser and navigate to:
   ```text
   http://localhost:8000
   ```
3. Type a message in the chat box, send it, and watch the orb pulsate as the assistant speaks the reply!

### Option B: Terminal / CLI Mode
A simple text-in, text-out chatbot that loops in the console.

1. Start the CLI chatbot:
   ```bash
   python main.py
   ```
2. Type your message at the `You: ` prompt and press **Enter**.
3. Type `exit` and press Enter to quit.

---

## Troubleshooting

- **Pygame Audio Issues:** If you hear no sound or receive a `pygame` warning, ensure your OS audio device is enabled. If audio drivers are missing, the bot will print a warning but will still function and save the `output.mp3` file successfully.
- **API Key Errors:** Double-check that your `.env` file has the correct key names and that there are no extra spaces.
