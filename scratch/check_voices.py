import os
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv()

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

try:
    voices = client.voices.get_all()
    print("\nAvailable Voices for your API Key:")
    print("=" * 60)
    for voice in voices.voices:
        # Check if it's a pre-made voice (usually category 'pre-made')
        print(f"Name: {voice.name} | ID: {voice.voice_id} | Category: {voice.category}")
    print("=" * 60)
except Exception as e:
    print(f"Error fetching voices: {e}")
