import os
import glob
import time
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
from dotenv import load_dotenv
from openai import OpenAI
from murf import Murf

# Load environment variables
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
MURF_VOICE_ID = os.getenv("MURF_VOICE_ID", "en-US-natalie")

# Ensure required API keys are available
if not OPENROUTER_API_KEY or not MURF_API_KEY:
    print("Warning: Missing OPENROUTER_API_KEY or MURF_API_KEY in environment variables.")

# Create static directories if they don't exist
os.makedirs("static", exist_ok=True)
os.makedirs("static/audio", exist_ok=True)

app = FastAPI(title="Chatbot Web App")

# Initialize API clients
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)
murf_client = Murf(api_key=MURF_API_KEY)

class Message(BaseModel):
    role: str
    content: str

class ChatPayload(BaseModel):
    messages: List[Message]

def cleanup_old_audio(directory="static/audio", max_age_seconds=600):
    """Periodically remove audio files older than 10 minutes to save disk space."""
    if not os.path.exists(directory):
        return
    now = time.time()
    for file_path in glob.glob(os.path.join(directory, "reply_*.mp3")):
        try:
            if os.path.getmtime(file_path) < now - max_age_seconds:
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")

@app.post("/api/chat")
async def chat_endpoint(payload: ChatPayload):
    if not OPENROUTER_API_KEY or not MURF_API_KEY:
        raise HTTPException(status_code=500, detail="API keys are not configured on the server.")

    # Format messages for OpenRouter API
    formatted_messages = [{"role": msg.role, "content": msg.content} for msg in payload.messages]

    # Step 1: Query OpenRouter for the text reply
    try:
        completion = openrouter_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=formatted_messages,
            extra_headers={
                "HTTP-Referer": "https://github.com/murf-ai/chatbot-web",
                "X-Title": "Python Web Chatbot",
            }
        )
        bot_text = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenRouter Error: {str(e)}")

    # Step 2: Generate speech via Murf AI
    audio_filename = f"reply_{int(time.time() * 1000)}.mp3"
    audio_path = os.path.join("static/audio", audio_filename)
    
    try:
        # Call Murf SDK
        response = murf_client.text_to_speech.generate(
            text=bot_text,
            voice_id=MURF_VOICE_ID,
            format="MP3",
            sample_rate=44100
        )
        
        # Extract audio URL from Murf response object
        audio_url = getattr(response, "audioFile", None) or getattr(response, "audio_file", None)
        if not audio_url and isinstance(response, dict):
            audio_url = response.get("audioFile") or response.get("audio_file")
            
        if not audio_url:
            raise ValueError("No audioFile URL found in Murf AI response.")
            
        # Download and save the MP3 file
        audio_data = requests.get(audio_url)
        audio_data.raise_for_status()
        with open(audio_path, "wb") as f:
            f.write(audio_data.content)
            
    except Exception as e:
        # We still return the text response even if the audio generation fails
        print(f"Murf AI Speech Generation failed: {e}")
        return {
            "text": bot_text,
            "audio_url": None,
            "error": f"Speech generation failed: {str(e)}"
        }

    # Run background cleanup of old files
    cleanup_old_audio()

    # Return the text response and the local URL to the saved audio file
    return {
        "text": bot_text,
        "audio_url": f"/static/audio/{audio_filename}"
    }

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    # Read port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on http://localhost:{port}...")
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=True)
