import os
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv()

client = ElevenLabs(api_key=os.getenv("ELEVEN_API_KEY")) # Wait, the key in .env is ELEVENLABS_API_KEY

try:
    models = client.models.get_all()
    print("\nAvailable Models for your API Key:")
    print("=" * 60)
    for model in models:
        print(f"Name: {model.name} | ID: {model.model_id}")
    print("=" * 60)
except Exception as e:
    print(f"Error fetching models: {e}")
