import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq client conditionally
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
    except ImportError:
        groq_client = None
else:
    groq_client = None

# Initialize Gemini client conditionally
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
    except ImportError:
        genai = None
else:
    genai = None

def generate_response(prompt_text, provider="gemini"):
    """
    Universal router for LLM API calls with built-in rate limiting.
    Options for provider: 'gemini', 'groq', 'local'
    """
    if provider == "gemini":
        if not genai or not GEMINI_API_KEY:
            print("Gemini API not configured or google-generativeai not installed.")
            return None
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        while True:
            try:
                response = model.generate_content(prompt_text, generation_config=genai.types.GenerationConfig(temperature=0.1))
                time.sleep(4.1)  # Force sleep on success equivalent to 15 RPM
                return response.text
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
                    print(f"Gemini Rate limit hit. Sleeping for 60 seconds... ({e})")
                    time.sleep(60)
                else:
                    print(f"Gemini API Error: {e}")
                    time.sleep(60)
                    return None

    elif provider == "groq":
        if not groq_client:
            print("Groq API not configured or groq package not installed.")
            return None
            
        while True:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "user", "content": prompt_text}
                    ],
                    temperature=0.1
                )
                time.sleep(12)  # Force sleep on success equivalent to 5 RPM
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e).lower()
                if "rate limit" in error_str or "429" in error_str:
                    print("Groq Rate limit hit. Sleeping for 60 seconds...")
                    time.sleep(60)
                else:
                    print(f"Groq API Error: {e}")
                    time.sleep(60) 
                    return None

    elif provider == "local":
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen2.5-coder",
            "prompt": prompt_text,
            "stream": False,
            "options": {"temperature": 0.1}
        }
        try: 
            response = requests.post(url, json=payload, timeout=300) 
            response.raise_for_status()
            return response.json().get('response', '')
        except Exception as e:
            print(f"Local Model Error: {e}")
            return None
            
    else:
        print(f"Unknown provider: {provider}")
        return None
