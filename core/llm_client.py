import os
import time
import requests
import json
from dotenv import load_dotenv

from core.tools import CAD_TOOLS_SCHEMA, get_shape_blueprint

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

def generate_response(prompt_text, provider="gemini", force_tool=False, error_history=None):
    """
    Universal router for LLM API calls with built-in rate limiting and tool calling.
    Options for provider: 'gemini', 'groq', 'local'
    """
    if provider == "gemini":
        if not genai or not GEMINI_API_KEY:
            print("Gemini API not configured or google-generativeai not installed.")
            return None
        
        if force_tool:
            tool_config = {"function_calling_config": {"mode": "ANY", "allowed_function_names": ["get_shape_blueprint"]}}
            model = genai.GenerativeModel('gemini-2.0-flash', tools=[get_shape_blueprint], tool_config=tool_config)
        else:
            model = genai.GenerativeModel('gemini-2.0-flash', tools=[get_shape_blueprint])
        # If there's error_history, Gemini chat history can optionally be seeded, but sending the history directly is complex. 
        # Instead, since we already dynamically append error history to `prompt_text` in backend.py, we just need the standard start_chat.
        chat_session = model.start_chat()
        while True:
            try:
                response = chat_session.send_message(prompt_text, generation_config=genai.types.GenerationConfig(temperature=0.1))
                time.sleep(4.1)  # Force sleep on success equivalent to 15 RPM

                # Check if the model wants to call a tool
                function_call_obj = None
                if hasattr(response, 'parts') and len(response.parts) > 0 and hasattr(response.parts[0], 'function_call'):
                    function_call_obj = response.parts[0].function_call
                elif hasattr(response, 'candidates') and len(response.candidates) > 0 and hasattr(response.candidates[0].content.parts[0], 'function_call'):
                    function_call_obj = response.candidates[0].content.parts[0].function_call

                if function_call_obj:
                    # Execute our local tool
                    shape_type = function_call_obj.args.get("shape_type", "")
                    print(f"\n[AGENT DECISION] Model decided to call tool: get_shape_blueprint('{shape_type}')")
                    
                    tool_result = get_shape_blueprint(shape_type)
                    print(f"[TOOL EXECUTED] Successfully retrieved blueprint from Vault. Sending back to model...\n")
                    
                    # Clean dictionary format (No genai.protos.Part required!)
                    tool_response_parts = [
                        {
                            "function_response": {
                                "name": "get_shape_blueprint",
                                "response": {"result": tool_result}
                            }
                        }
                    ]
                    
                    # Send the tool response back to the chat session
                    final_response = chat_session.send_message(tool_response_parts, generation_config=genai.types.GenerationConfig(temperature=0.1))
                    time.sleep(4.1) # Sleep again for the second API call
                    
                    # Safely extract text to prevent 'cannot convert function_call to text' crashes
                    if hasattr(final_response, 'text'):
                        return final_response.text
                    elif hasattr(final_response, 'parts'):
                        return final_response.parts[0].text
                    else:
                        return str(final_response)
                
                # If no tool was called, just return the text
                return response.text

            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
                    if "tokens per minute" in error_str or "tpm" in error_str:
                        print(f"🛑 GEMINI TPM LIMIT HIT (Tokens per minute exceeded). Sleeping for 60 seconds...")
                    elif "requests per minute" in error_str or "rpm" in error_str:
                        print(f"🛑 GEMINI RPM LIMIT HIT (Requests per minute exceeded). Sleeping for 60 seconds...")
                    elif "requests per day" in error_str or "requestsperday" in error_str or "rpd" in error_str:
                        print(f"🔴 FATAL: GEMINI DAILY RPD LIMIT HIT. Stopping execution.")
                        return None
                    else:
                        print(f"🛑 Gemini Rate limit / Quota hit. Sleeping for 60 seconds... ({e})")
                    time.sleep(60)
                else:
                    print(f"Gemini API Error: {e}")
                    time.sleep(60)
                    return None

    elif provider == "groq":
        if not groq_client:
            print("Groq API not configured or groq package not installed.")
            return None
            
        messages = [{"role": "user", "content": prompt_text}]
        groq_tool_choice = {"type": "function", "function": {"name": "get_shape_blueprint"}} if force_tool else "auto"

        while True:
            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.1,
                    tools=CAD_TOOLS_SCHEMA,
                    tool_choice=groq_tool_choice
                )
                time.sleep(12)  # Force sleep on success equivalent to 5 RPM

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                # Check if the model wants to call a tool
                if tool_calls:
                    messages.append(response_message)
                    
                    for tool_call in tool_calls:
                        if tool_call.function.name == "get_shape_blueprint":
                            # Use json.loads instead of getattr
                            args = json.loads(tool_call.function.arguments)
                            shape_type = args.get("shape_type", "")
                            
                            print(f"\n[AGENT DECISION] Model decided to call tool: get_shape_blueprint('{shape_type}')")
                            
                            # Execute our local tool
                            tool_result = get_shape_blueprint(shape_type)
                            print(f"[TOOL EXECUTED] Successfully retrieved blueprint from Vault. Sending back to model...\n")
                            
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "content": tool_result,
                                }
                            )

                    # Make a second API call to Groq with the tool response
                    final_response = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages,
                        temperature=0.1,
                        tools=CAD_TOOLS_SCHEMA,
                        tool_choice="auto"
                    )
                    time.sleep(12) # Sleep again for the second API call
                    return final_response.choices[0].message.content
                
                # If no tool was called, return the text
                return response_message.content

            except Exception as e:
                error_str = str(e).lower()
                if "rate limit" in error_str or "429" in error_str:
                    if "tokens per minute" in error_str or "tpm" in error_str:
                        print(f"🛑 GROQ TPM LIMIT HIT (Tokens per minute exceeded). Sleeping for 60 seconds...")
                    elif "requests per minute" in error_str or "rpm" in error_str:
                        print(f"🛑 GROQ RPM LIMIT HIT (Requests per minute exceeded). Sleeping for 60 seconds...")
                    elif "requests per day" in error_str:
                        print(f"🔴 FATAL: GROQ DAILY RPD LIMIT HIT. Stopping execution.")
                        return None
                    else:
                        print(f"🛑 Groq Rate limit hit. Sleeping for 60 seconds... ({e})")
                        time.sleep(60)
                else:
                    print(f"Groq API Error: {e}")
                    time.sleep(60) 
                    return None

    elif provider == "local":
        import ollama
        messages = [{'role': 'user', 'content': prompt_text}]
        
        # 1. FORCE TOOL: Bypass weak autonomy and forcefully inject blueprint if required
        if force_tool:
            print(f"\n[🔧 FORCED TOOL EXECUTION] Fetching blueprint for: '{force_tool}'")
            blueprint_code = get_shape_blueprint(force_tool)
            messages.insert(0, {
                'role': 'system',
                'content': f"You must base your design on this functional blueprint:\n{blueprint_code}\n\nA blueprint has been provided. CRITICAL: This is just a syntax example. You MUST adjust the dimensions, coordinates, and logic to match the USER REQUEST perfectly. Do not blindly copy the blueprint dimensions."
            })
            print(f"[🧠 AGENT RESUMING] Blueprint forcefully injected into context. Generating final CAD code...\n")
            
            # Call Ollama exactly once with the injected context
            final_response = ollama.chat(model='qwen2.5-coder', messages=messages)
            return final_response.message.content

        # 2. AUTONOMOUS: If no tool forced, just give it the schema and let it decide (fallback)
        response = ollama.chat(model='qwen2.5-coder', messages=messages, tools=CAD_TOOLS_SCHEMA)

        if response.message.tool_calls:
            print(f"\n[🤖 AGENT ACTION] Model paused generation to use tools!")
            messages.append(response.message) 
            for tool in response.message.tool_calls:
                if tool.function.name == 'get_shape_blueprint':
                    shape_requested = tool.function.arguments.get('shape_type', '')
                    print(f"[🔧 TOOL EXECUTED] Fetching blueprint for: '{shape_requested}'")
                    blueprint_code = get_shape_blueprint(shape_requested)
                    messages.append({
                        'role': 'tool',
                        'content': f"{blueprint_code}\n\nA blueprint has been provided. CRITICAL: This is just a syntax example. You MUST adjust the dimensions, coordinates, and logic to match the USER REQUEST perfectly. Do not blindly copy the blueprint dimensions.",
                        'name': tool.function.name
                    })
            print(f"[🧠 AGENT RESUMING] Blueprint acquired. Generating final CAD code...\n")
            final_response = ollama.chat(model='qwen2.5-coder', messages=messages)
            return final_response.message.content
        else:
            return response.message.content
            
    else:
        print(f"Unknown provider: {provider}")
        return None
