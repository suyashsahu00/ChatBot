import os
import time
import requests
from dotenv import load_dotenv
from openai import OpenAI
from murf import Murf

# Hide the pygame greeting message in the terminal
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# Load environment variables from .env file
load_dotenv()

# Retrieve API keys and settings from environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "x-ai/grok-2")
MURF_VOICE_ID = os.getenv("MURF_VOICE_ID", "en-US-natalie")

def check_env_variables():
    """Ensure all required environment variables are set."""
    missing_vars = []
    if not OPENROUTER_API_KEY:
        missing_vars.append("OPENROUTER_API_KEY")
    if not MURF_API_KEY:
        missing_vars.append("MURF_API_KEY")
    
    if missing_vars:
        print("Error: Missing required environment variable(s):")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease configure them in your .env file or environment.")
        return False
    return True

def play_audio(file_path):
    """Play the generated audio file using pygame."""
    if not PYGAME_AVAILABLE:
        print(f"Note: pygame is not installed. Saved speech to: {file_path}")
        return

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        
        # Wait until the audio finishes playing
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
            
        pygame.mixer.music.unload()
        pygame.mixer.quit()
    except Exception as e:
        print(f"\nWarning: Could not play audio automatically. Error: {e}")
        print(f"Saved speech to: {file_path}")

def generate_text_response(client, messages):
    """Generate a text response from OpenRouter using Grok AI."""
    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            # OpenRouter headers for identifying the application (optional)
            extra_headers={
                "HTTP-Referer": "https://github.com/murf-ai/chatbot",
                "X-Title": "Python CLI Chatbot",
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"\nError communicating with OpenRouter: {e}")
        return None

def generate_speech_response(murf_client, text, output_filename="output.mp3"):
    """Convert text into speech using Murf AI and save the file."""
    try:
        print("Converting bot reply to speech...")
        
        # Request Speech generation from Murf AI Python SDK
        response = murf_client.text_to_speech.generate(
            text=text,
            voice_id=MURF_VOICE_ID,
            format="MP3",
            sample_rate=44100
        )
        
        # Get the URL of the generated audio file from the response object
        audio_url = getattr(response, "audioFile", None) or getattr(response, "audio_file", None)
        if not audio_url and isinstance(response, dict):
            audio_url = response.get("audioFile") or response.get("audio_file")
            
        if not audio_url:
            raise ValueError("No audioFile URL found in the Murf API response.")

        # Download the audio file
        audio_data = requests.get(audio_url)
        audio_data.raise_for_status()
        
        # Save to local file
        with open(output_filename, "wb") as f:
            f.write(audio_data.content)
            
        return output_filename
    except Exception as e:
        print(f"\nError communicating with Murf AI: {e}")
        return None

def main():
    if not check_env_variables():
        return

    # Initialize the OpenRouter client (using OpenAI-compatible client)
    openrouter_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY
    )

    # Initialize the Murf AI client
    murf_client = Murf(api_key=MURF_API_KEY)

    # Conversational memory history starting with the system prompt
    messages = [
        {"role": "system", "content": "You are a helpful assistant who gives short, clear answers."}
    ]

    print("=" * 60)
    print("Welcome to the Python CLI Chatbot!")
    print(f"Text model (OpenRouter): {OPENROUTER_MODEL}")
    print(f"Speech voice (Murf AI):  {MURF_VOICE_ID}")
    print("Type 'exit' to end the conversation.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nYou: ")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if user_input.strip().lower() == "exit":
            print("Goodbye!")
            break

        if not user_input.strip():
            continue

        # Add user's message to the conversation history
        messages.append({"role": "user", "content": user_input})

        # Step 1: Generate text response via OpenRouter
        bot_text = generate_text_response(openrouter_client, messages)
        if not bot_text:
            # If the API call failed, remove the user's message so history stays aligned
            messages.pop()
            continue

        print(f"Bot: {bot_text}")

        # Add the bot's response to the conversation history
        messages.append({"role": "assistant", "content": bot_text})

        # Step 2: Convert response text to speech via Murf AI
        audio_file = generate_speech_response(murf_client, bot_text)
        
        # Step 3: Play audio response automatically
        if audio_file:
            play_audio(audio_file)

if __name__ == "__main__":
    main()
