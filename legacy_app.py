import os
import glob
import time
import requests
import re
import aiosqlite
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
from openai import OpenAI
from murf import Murf

def clean_text_for_tts(text: str) -> str:
    """Prepare text for TTS by removing markdown formatting, code blocks, and dividers."""
    if not text:
        return ""
    # 1. Remove code blocks
    cleaned = re.sub(r'```[\s\S]*?```', '', text)
    # 2. Remove headers
    cleaned = re.sub(r'^#+\s+', '', cleaned, flags=re.MULTILINE)
    # 3. Remove dividers
    cleaned = re.sub(r'^---$', '', cleaned, flags=re.MULTILINE)
    # 4. Remove bold/italics
    cleaned = re.sub(r'\*\*([^*]+)\*\*|__([^_]+)__', r'\1\2', cleaned)
    cleaned = re.sub(r'\*([^*]+)\*|_([^_]+)_', r'\1\2', cleaned)
    # 5. Remove blockquotes
    cleaned = re.sub(r'^>\s+', '', cleaned, flags=re.MULTILINE)
    # 6. Simplify multiple spacing/newlines
    cleaned = re.sub(r'\n+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

# Load environment variables
load_dotenv()

# Extract API Keys (stripping spaces to handle .env file typos)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip() or None
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
MURF_API_KEY = os.getenv("MURF_API_KEY", "").strip() or None
MURF_VOICE_ID = os.getenv("MURF_VOICE_ID", "en-US-natalie").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip() or None
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip() or None
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "").strip() or None

DATABASE_FILE = "chatbot.db"

# Lifecycle context manager for database setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the SQLite database and create schemas
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                audio_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        await db.commit()
    yield

# Create directories for caching audio files
os.makedirs("static", exist_ok=True)
os.makedirs("static/audio", exist_ok=True)

app = FastAPI(title="Grok & Murf AI Voice Assistant", lifespan=lifespan)

# Primary API Clients
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)
murf_client = Murf(api_key=MURF_API_KEY) if MURF_API_KEY else None

# Pydantic Schemas
class Message(BaseModel):
    role: str
    content: str

class ChatPayload(BaseModel):
    session_id: str
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

# Database APIs for Session History Persistence (Claude-style)
@app.get("/api/sessions")
async def get_sessions():
    """Retrieve list of all chat sessions for the sidebar."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

@app.get("/api/sessions/{session_id}")
async def get_session_messages(session_id: str):
    """Retrieve all messages in a specific session to restore history."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return {"status": "success"}

# Chat Endpoint with Automated API Failover
@app.post("/api/chat")
async def chat_endpoint(payload: ChatPayload):
    # Ensure there's a session in the DB
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute("SELECT id FROM sessions WHERE id = ?", (payload.session_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                # Deduce title from first user message
                user_msg = next((msg.content for msg in payload.messages if msg.role == "user"), "New Chat")
                title = user_msg[:35] + ("..." if len(user_msg) > 35 else "")
                await db.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", (payload.session_id, title))
                await db.commit()

    # Format messages for standard chat completion
    formatted_messages = [{"role": msg.role, "content": msg.content} for msg in payload.messages]

    # --- TEXT GENERATION API FAILOVER ROUTING ---
    bot_text = None
    text_errors = []

    # 1. Primary: OpenRouter (Grok-2 or Free model)
    if not bot_text and OPENROUTER_API_KEY:
        try:
            print("Attempting text generation with OpenRouter...")
            completion = openrouter_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=formatted_messages,
                extra_headers={
                    "HTTP-Referer": "https://github.com/murf-ai/chatbot-web",
                    "X-Title": "Python Web Chatbot",
                }
            )
            bot_text = completion.choices[0].message.content
            print("OpenRouter generation succeeded!")
        except Exception as e:
            err_msg = f"OpenRouter Fail: {str(e)}"
            print(err_msg)
            text_errors.append(err_msg)

    # 2. Secondary Fallback: OpenAI (gpt-4o-mini)
    if not bot_text and OPENAI_API_KEY:
        try:
            print("OpenRouter failed. Attempting OpenAI fallback...")
            from openai import OpenAI as RealOpenAI
            openai_client = RealOpenAI(api_key=OPENAI_API_KEY)
            completion = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=formatted_messages
            )
            bot_text = completion.choices[0].message.content
            print("OpenAI fallback generation succeeded!")
        except Exception as e:
            err_msg = f"OpenAI Fail: {str(e)}"
            print(err_msg)
            text_errors.append(err_msg)

    # 3. Tertiary Fallback: Google Gemini (gemini-1.5-flash)
    if not bot_text and GOOGLE_API_KEY:
        try:
            print("OpenAI failed. Attempting Google Gemini fallback...")
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            
            # Map OpenAI message roles to Gemini format
            gemini_messages = []
            for msg in formatted_messages:
                role = "user" if msg["role"] == "user" else "model"
                if msg["role"] == "system":
                    continue
                gemini_messages.append({"role": role, "parts": [msg["content"]]})
                
            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                system_instruction="You are a helpful assistant who gives short, clear answers."
            )
            response = model.generate_content(gemini_messages)
            bot_text = response.text
            print("Google Gemini fallback generation succeeded!")
        except Exception as e:
            err_msg = f"Google Gemini Fail: {str(e)}"
            print(err_msg)
            text_errors.append(err_msg)

    # If all fail, throw error
    if not bot_text:
        raise HTTPException(
            status_code=502,
            detail=f"All Text Generation APIs failed. Errors: {'; '.join(text_errors)}"
        )

    # --- TEXT TO SPEECH (TTS) API FAILOVER ROUTING ---
    audio_filename = f"reply_{int(time.time() * 1000)}.mp3"
    audio_path = os.path.join("static/audio", audio_filename)
    audio_url_path = f"/static/audio/{audio_filename}"
    audio_success = False
    tts_errors = []

    # Clean text for speech synthesis
    tts_text = clean_text_for_tts(bot_text)
    if not tts_text:
        tts_text = "Here is the code block you requested."

    # 1. Primary: Murf AI (Only if clean text is <= 3000 chars)
    if not audio_success and murf_client and len(tts_text) <= 3000:
        try:
            print("Attempting speech synthesis with Murf AI...")
            response = murf_client.text_to_speech.generate(
                text=tts_text,
                voice_id=MURF_VOICE_ID,
                format="MP3",
                sample_rate=44100
            )
            
            audio_url = getattr(response, "audioFile", None) or getattr(response, "audio_file", None)
            if not audio_url and isinstance(response, dict):
                audio_url = response.get("audioFile") or response.get("audio_file")
                
            if not audio_url:
                raise ValueError("No audioFile URL found in Murf response.")

            # Download the synthesized file
            audio_data = requests.get(audio_url)
            audio_data.raise_for_status()
            with open(audio_path, "wb") as f:
                f.write(audio_data.content)
            
            audio_success = True
            print("Murf AI Speech synthesis succeeded!")
        except Exception as e:
            err_msg = f"Murf AI TTS Fail: {str(e)}"
            print(err_msg)
            tts_errors.append(err_msg)
    else:
        if len(tts_text) > 3000:
            tts_errors.append("Bypassed Murf: Clean text exceeds 3000-character limit.")

    # 2. Fallback: OpenAI TTS
    if not audio_success and OPENAI_API_KEY:
        try:
            print("Murf failed. Attempting OpenAI TTS fallback...")
            from openai import OpenAI as RealOpenAI
            openai_client = RealOpenAI(api_key=OPENAI_API_KEY)
            
            response = openai_client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=tts_text
            )
            
            # Save audio bytes
            response.stream_to_file(audio_path)
            audio_success = True
            print("OpenAI TTS fallback speech synthesis succeeded!")
        except Exception as e:
            err_msg = f"OpenAI TTS Fail: {str(e)}"
            print(err_msg)
            tts_errors.append(err_msg)

    # Set URL to None if both fail
    if not audio_success:
        print(f"All TTS synthesis APIs failed. Errors: {'; '.join(tts_errors)}")
        audio_url_path = None

    # --- DATABASE STORAGE ---
    async with aiosqlite.connect(DATABASE_FILE) as db:
        # Save User prompt
        last_user_msg = payload.messages[-1]
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (payload.session_id, last_user_msg.role, last_user_msg.content)
        )
        # Save Bot reply
        await db.execute(
            "INSERT INTO messages (session_id, role, content, audio_url) VALUES (?, ?, ?, ?)",
            (payload.session_id, "assistant", bot_text, audio_url_path)
        )
        await db.commit()

    # Clean old files
    cleanup_old_audio()

    return {
        "text": bot_text,
        "audio_url": audio_url_path,
        "error": f"Speech synthesis failed: {'; '.join(tts_errors)}" if not audio_success else None
    }

@app.post("/api/upload")
async def upload_file_endpoint(file: UploadFile = File(...)):
    filename = file.filename
    content_type = file.content_type or ""
    print(f"Received file upload: {filename}, type: {content_type}")
    
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
        
    ext = os.path.splitext(filename)[1].lower()
    extracted_text = ""
    
    # 1. Handle Text Files
    if ext in ['.txt', '.py', '.js', '.css', '.json', '.md', '.csv', '.html', '.xml', '.yaml', '.yml']:
        try:
            extracted_text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                extracted_text = file_bytes.decode('latin-1')
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to decode text file: {str(e)}")
                
    # 2. Handle PDF Files
    elif ext == '.pdf':
        try:
            import pypdf
            import io
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text_parts = []
            for i, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text}")
                else:
                    print(f"No text extracted on page {i+1}. Checking for page images...")
                    page_images_text = []
                    try:
                        from PIL import Image
                        images_list = list(page.images)
                        if images_list:
                            for img_idx, image_file_object in enumerate(images_list):
                                print(f"Extracting image {img_idx+1} from page {i+1}...")
                                img_bytes = image_file_object.data
                                
                                # Resolve PIL Image
                                try:
                                    image = image_file_object.image
                                except Exception:
                                    image = Image.open(io.BytesIO(img_bytes))
                                    
                                # OCR via Gemini
                                img_desc = None
                                if GOOGLE_API_KEY:
                                    try:
                                        import google.generativeai as genai
                                        genai.configure(api_key=GOOGLE_API_KEY)
                                        model = genai.GenerativeModel('gemini-2.5-flash')
                                        response = model.generate_content([
                                            "Perform OCR on this image. Extract and transcribe all visible text exactly as it appears. If it is an image, describe it briefly.",
                                            image
                                        ])
                                        img_desc = response.text
                                    except Exception as e:
                                        print(f"Gemini page image OCR failed: {e}")
                                        
                                # OCR via OpenAI fallback
                                if not img_desc and OPENAI_API_KEY:
                                    try:
                                        import base64
                                        base64_image = base64.b64encode(img_bytes).decode('utf-8')
                                        headers = {
                                            "Content-Type": "application/json",
                                            "Authorization": f"Bearer {OPENAI_API_KEY}"
                                        }
                                        payload = {
                                            "model": "gpt-4o-mini",
                                            "messages": [
                                                {
                                                    "role": "user",
                                                    "content": [
                                                        {
                                                            "type": "text",
                                                            "text": "Extract and transcribe all text from this image."
                                                        },
                                                        {
                                                            "type": "image_url",
                                                            "image_url": {
                                                                "url": f"data:image/jpeg;base64,{base64_image}"
                                                            }
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                                        if response.ok:
                                            img_desc = response.json()["choices"][0]["message"]["content"]
                                    except Exception as e:
                                        print(f"OpenAI page image OCR failed: {e}")
                                        
                                if img_desc:
                                    page_images_text.append(img_desc)
                                    
                        if page_images_text:
                            text_parts.append(f"--- Page {i+1} (OCR/Vision Extracted) ---\n" + "\n".join(page_images_text))
                        else:
                            text_parts.append(f"--- Page {i+1} ---\n[Scanned/Empty Page - No text or images extracted]")
                    except Exception as page_err:
                        print(f"Failed to extract page {i+1} image content: {page_err}")
                        text_parts.append(f"--- Page {i+1} ---\n[Scanned Page - Failed to parse images: {str(page_err)}]")
            
            extracted_text = "\n\n".join(text_parts)
            if not extracted_text.strip():
                extracted_text = "[No readable text or images found in PDF.]"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF file: {str(e)}")
            
    # 3. Handle Images (OCR / Vision description)
    elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
        description = None
        
        # Try Google Gemini Vision
        if not description and GOOGLE_API_KEY:
            try:
                print("Using Google Gemini to analyze image...")
                import google.generativeai as genai
                from PIL import Image
                import io
                
                genai.configure(api_key=GOOGLE_API_KEY)
                model = genai.GenerativeModel('gemini-2.5-flash')
                image = Image.open(io.BytesIO(file_bytes))
                response = model.generate_content([
                    "Describe this image in detail. Extract any visible text or code exactly as it appears. Provide a structured summary of the visual elements.",
                    image
                ])
                description = response.text
                print("Gemini image analysis succeeded!")
            except Exception as e:
                print(f"Gemini image analysis failed: {e}")
                
        # Try OpenAI GPT-4o-mini Vision fallback
        if not description and OPENAI_API_KEY:
            try:
                print("Using OpenAI GPT-4o-mini to analyze image...")
                import base64
                base64_image = base64.b64encode(file_bytes).decode('utf-8')
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Describe this image in detail. Extract any visible text or code exactly as it appears. Provide a structured summary of the visual elements."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{content_type or 'image/jpeg'};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ]
                }
                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                if response.ok:
                    description = response.json()["choices"][0]["message"]["content"]
                    print("OpenAI image analysis succeeded!")
                else:
                    print(f"OpenAI image analysis status {response.status_code}: {response.text}")
            except Exception as e:
                print(f"OpenAI image analysis failed: {e}")
                
        if description:
            extracted_text = description
        else:
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(file_bytes))
                extracted_text = f"[Image Attached: {filename} ({img.width}x{img.height}px, format: {img.format}). No active vision API keys were able to process description.]"
            except Exception as e:
                extracted_text = f"[Image Attached: {filename}. Vision processing unavailable.]"
                
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        
    return {
        "filename": filename,
        "extracted_text": extracted_text
    }

@app.post("/api/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    # Ensure at least one key is present
    if not DEEPGRAM_API_KEY and not OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="Missing Deepgram or OpenAI API keys for transcription.")
    
    try:
        audio_bytes = await file.read()
        print(f"Received audio recording: {len(audio_bytes)} bytes, content_type: {file.content_type}")
        
        # Save audio backup for troubleshooting
        backup_path = "static/audio/last_recording.webm"
        with open(backup_path, "wb") as f_backup:
            f_backup.write(audio_bytes)
        print(f"Saved last recording to {backup_path}")
        
        if not audio_bytes or len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="No speech detected (audio recording is too short or empty).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read audio file: {str(e)}")
        
    transcript_text = ""
    transcribe_success = False
    errors = []
    
    # 1. Primary: Deepgram Nova-2
    if DEEPGRAM_API_KEY:
        try:
            print("Attempting transcription with Deepgram...")
            # Clean content-type (e.g., audio/webm;codecs=opus -> audio/webm)
            content_type = file.content_type or "audio/webm"
            if ";" in content_type:
                content_type = content_type.split(";")[0].strip()
                
            # Deepgram REST API
            url = "https://api.deepgram.com/v1/listen?smart_format=true&model=nova-2"
            headers = {
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": content_type
            }
            response = requests.post(url, headers=headers, data=audio_bytes)
            if response.ok:
                res_data = response.json()
                transcript_text = res_data["results"]["channels"][0]["alternatives"][0]["transcript"]
                transcribe_success = True
                print(f"Deepgram transcription succeeded! Result: '{transcript_text}'")
            else:
                errors.append(f"Deepgram status {response.status_code}: {response.text}")
        except Exception as e:
            errors.append(f"Deepgram failed: {str(e)}")
            
    # 2. Fallback: OpenAI Whisper
    if not transcribe_success and OPENAI_API_KEY:
        try:
            print("Deepgram failed. Attempting OpenAI Whisper transcription fallback...")
            temp_filename = f"temp_transcribe_{int(time.time() * 1000)}.webm"
            with open(temp_filename, "wb") as temp_file:
                temp_file.write(audio_bytes)
            
            from openai import OpenAI as RealOpenAI
            openai_client = RealOpenAI(api_key=OPENAI_API_KEY)
            with open(temp_filename, "rb") as audio_file:
                result = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
                transcript_text = result.text
            
            os.remove(temp_filename)
            transcribe_success = True
            print(f"OpenAI Whisper transcription succeeded! Result: '{transcript_text}'")
        except Exception as e:
            errors.append(f"OpenAI Whisper failed: {str(e)}")
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                
    if not transcribe_success:
        raise HTTPException(status_code=502, detail=f"All Transcription APIs failed. Errors: {'; '.join(errors)}")
        
    return {"transcript": transcript_text}

# Serve static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on http://localhost:{port}...")
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=True)
