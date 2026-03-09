import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ API Key not found in .env file!")
else:
    client = genai.Client(api_key=api_key)
    print("Searching for available models...\n")
    try:
        # List all models available to your key
        for model in client.models.list():
            name = model.name
            # Filter for "generateContent" models (the ones that write text/code)
            if "generateContent" in model.supported_actions:
                print(f"✅ Found: {name}")
    except Exception as e:
        print(f"Error listing models: {e}")