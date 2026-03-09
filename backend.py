import os
import re
import json
import requests
from prompts import SYSTEM_PROMPT
from core.validators import extract_design_intent_llm, validate_geometry
from core.rag_manager import retrieve_context
from core.logger import log_experiment

def call_local_llm(prompt_text):
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

def generate_cad_part(user_prompt, prompt_id="default", max_retries=8):
    design_intent = {}  
    try:
        print(f"\n🚀 NEW USER REQUEST: {user_prompt}")

        # 1. RAG Retrieval 
        print("Retrieving official build123d documentation...")
        retrieved_context = retrieve_context(user_prompt)
        formatting_anchor = "\n\nCRITICAL: Output ONLY the raw Python script inside ```python ... ``` blocks. No explanations. No markdown outside the block."
        
        if retrieved_context:
            rag_block = "\n\n".join(retrieved_context)
            base_prompt = f"{SYSTEM_PROMPT}\n\n--- OFFICIAL BUILD123D DOCS ---\n{rag_block}\n-------------------------------\n\nUSER REQUEST: {user_prompt}"
            print("RAG Context successfully injected into prompt.")
        else:
            base_prompt = f"{SYSTEM_PROMPT}\n\nUSER REQUEST: {user_prompt}"
            print("No specific RAG context found. Proceeding with default prompt.")
            
        current_prompt = f"{base_prompt}{formatting_anchor}"

        output_dir = os.path.join("generated_files", str(prompt_id))
        os.makedirs(output_dir, exist_ok=True)
        
        # 2. Agent 1 (Planner) extracts intent
        design_intent = extract_design_intent_llm(user_prompt)
        print(f"Agent 1 (Planner) extracted intent: {json.dumps(design_intent, indent=2)}")
        
        error_history = []
        last_known_error = "None" 
        
        for attempt in range(max_retries):
            print(f"\n--- Attempt {attempt + 1} of {max_retries} ---")
            print("Agent 2 (Coder) is thinking... (Local generation may take 30-60 seconds)")
            
            response_text = call_local_llm(current_prompt)
            prompt_updated_in_error = False
            
            if not response_text:
                error_msg = "Failed to communicate with local model."
                code_block = ""
            else:
                # CHANGED: Now looks for <code> blocks
                match = re.search(r"<code>(.*?)</code>", response_text, re.DOTALL | re.IGNORECASE)
                if not match:
                    # Fallback to markdown python block just in case
                    match = re.search(r"```(?:python)?(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
                
                if not match:
                    # Final fallback: just look for the import statement if they forgot wrappers entirely
                    import_idx = response_text.find("from build123d import")
                    if import_idx != -1:
                        # Strip any </plan> or similar artifacts that might preceded it incorrectly
                        code_block = response_text[import_idx:].replace("</plan>", "").strip()
                    else:
                        error_msg = "You failed to wrap your Python code in <code> ... </code> blocks."
                        code_block = ""
                else:
                    code_block = match.group(1).strip()
                    
            if code_block:
                print("\n" + "="*40)
                print(f"GENERATED CODE (Attempt {attempt + 1}):\n{code_block}")
                print("="*40 + "\n")

                for f in os.listdir(output_dir):
                    os.remove(os.path.join(output_dir, f))

                exec_globals = {}
                print("Physics Engine executing generated code...")
                error_msg = ""
                
                try:
                    # Dynamically replace the default export path with the prompt-specific output directory
                    safe_output_dir = output_dir.replace("\\", "/")
                    code_block = code_block.replace("generated_files/generated_part", f"{safe_output_dir}/generated_part")
                    
                    exec(code_block, exec_globals)
                    final_part = exec_globals.get("final_part") or exec_globals.get("part")
                    if final_part is None:
                         raise ValueError("The variable 'final_part' (or 'part') was not assigned.")

                    # 3. Validation Layer (Physics Engine)
                    is_valid, report = validate_geometry(final_part, intent=design_intent, user_prompt=user_prompt)

                    if not is_valid:
                        error_msg = report.get("message", "Unknown Validation Error")
                        print(f"Validation Failed: {error_msg}")
                        error_history.append(f"- Attempt {attempt + 1} (Physics): {error_msg}")
                        for f in os.listdir(output_dir):
                            os.remove(os.path.join(output_dir, f))
                            
                    else:
                        files_created = os.listdir(output_dir)
                        step_file = next((f for f in files_created if f.endswith('.step')), None)
                        stl_file = next((f for f in files_created if f.endswith('.stl')), None)

                        if step_file or stl_file:
                            print(f"Success! Model generated and validated on attempt {attempt + 1}.")
                            log_experiment(user_prompt, design_intent, "SUCCESS", attempt + 1)
                            return {
                                "success": True,
                                "retries": attempt + 1,
                                "final_error": None,
                                "history": error_history,
                                "step": os.path.join(output_dir, step_file) if step_file else None,
                                "stl": os.path.join(output_dir, stl_file) if stl_file else None
                            }
                        else:
                            error_msg = "CRITICAL: The geometry is valid, but you forgot to export! You MUST include these exact two lines at the end of your script:\nexport_stl(final_part, 'generated_files/generated_part.stl')\nexport_step(final_part, 'generated_files/generated_part.step')"
                
                except Exception as exec_error:
                    raw_error = f"Python Execution Error: {str(exec_error)}"
                    from core.guardrails import get_smart_feedback
                    smart_error = get_smart_feedback(raw_error)
                    
                    if "CRITICAL API FIX" in smart_error:
                        print("Guardrail caught known hallucination! Fast-tracking fix...")
                        error_msg = smart_error
                        error_history.append(f"- Attempt {attempt + 1} (Syntax Fast-Path): {error_msg}")
                        
                        history_text = "\n".join(error_history)
                        current_prompt = f"{base_prompt}\n\n[PAST FAILED ATTEMPTS - DO NOT REPEAT THESE MISTAKES]:\n{history_text}\n\n[ATTEMPT {attempt + 1} FAILED. FIX THIS ERROR:]\n{error_msg}{formatting_anchor}"
                    
                    else:
                        print("Unknown error. Querying RAG database for manual...")
                        error_docs = retrieve_context(str(exec_error), k=1)
                        rag_snippet = error_docs[0] if error_docs else ""
                        error_msg = raw_error
                        error_history.append(f"- Attempt {attempt + 1} (Syntax Slow-Path): {error_msg}")
                        
                        history_text = "\n".join(error_history)
                        current_prompt = f"{base_prompt}\n\n[PAST FAILED ATTEMPTS - DO NOT REPEAT THESE MISTAKES]:\n{history_text}\n\n[ATTEMPT {attempt + 1} FAILED. FIX THIS ERROR:]\n{raw_error}"
                        if rag_snippet:
                            current_prompt += f"\n[RELEVANT DOCS TO FIX ERROR:]\n{rag_snippet}"
                        current_prompt += formatting_anchor
                    
                    prompt_updated_in_error = True
                    print(f"Code Execution Failed: {raw_error}")

            last_known_error = error_msg 

            if attempt < max_retries - 1:
                if error_msg:
                    print(f"Sending error back to LLM... ({error_msg[:100]}...)")
                    history_text = "\n".join(error_history)
                    if not prompt_updated_in_error:
                        current_prompt = f"{base_prompt}\n\n[PAST FAILED ATTEMPTS - DO NOT REPEAT THESE MISTAKES]:\n{history_text}\n\n[ATTEMPT {attempt + 1} FAILED. FIX THIS ERROR:]\n{error_msg}{formatting_anchor}"
            else:
                print("Max retries reached. The agent could not fix the code.")
                log_experiment(user_prompt, design_intent, "FAILED", max_retries, last_known_error)
                return {
                    "success": False,
                    "retries": max_retries,
                    "final_error": last_known_error,
                    "history": error_history,
                    "step": None,
                    "stl": None
                }

    except Exception as e:
        print(f"Fatal Backend Error: {e}")
        log_experiment(user_prompt, design_intent, "FATAL_ERROR", 0, str(e))
        return {
            "success": False,
            "retries": 0,
            "final_error": str(e),
            "history": [],
            "step": None,
            "stl": None
        }
