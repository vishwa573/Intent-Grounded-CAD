import os
import re
import json
import time
import csv
from dotenv import load_dotenv

from prompts import PROMPT_GEMINI, PROMPT_GROQ
from core.validators import extract_design_intent_llm, validate_geometry
from core.rag_manager import retrieve_context
from core.logger import log_experiment
from core.llm_client import generate_response

# --- CONFIGURATION ---
LLM_PROVIDER = "groq"  # Options: "gemini", "groq", "local"
USE_RAG = False          # Set to False to disable RAG (saves tokens for Groq)
MAX_RETRIES = 15
PROMPT_TYPE = "groq" # Options: "gemini", "groq"

# Step 1: Setup and Initialization
load_dotenv()

def get_next_run_dir(base_dir="showcase_run"):
    """Determines the next available versioned directory for the unified showcase runs."""
    os.makedirs(base_dir, exist_ok=True)
    existing_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and d.startswith(f"{LLM_PROVIDER}_v")]
    
    max_ver = 0
    for d in existing_dirs:
        try:
            ver = int(d.split('_v')[-1])
            if ver > max_ver:
                max_ver = ver
        except ValueError:
            pass
            
    next_ver = max_ver + 1
    new_dir = os.path.join(base_dir, f"{LLM_PROVIDER}_v{next_ver}")
    os.makedirs(new_dir, exist_ok=True)
    return new_dir

# The Generation Loop
def generate_cad_part_unified(user_prompt, prompt_id="default", run_dir="generated_files"):
    design_intent = {}  
    try:
        print(f"\n🚀 NEW USER REQUEST: {user_prompt}")

        base_prompt_text = PROMPT_GEMINI if PROMPT_TYPE == "gemini" else PROMPT_GROQ

        formatting_anchor = "\n\nCRITICAL: Output ONLY the raw Python script inside ```python ... ``` blocks. No explanations. No markdown outside the block."
        
        if USE_RAG:
            print("Retrieving official build123d documentation...")
            retrieved_context = retrieve_context(user_prompt, k=2) # RAG Optimization: Limit to k=1
            if retrieved_context:
                rag_block = "\n\n".join(retrieved_context)
                base_prompt = f"{base_prompt_text}\n\n--- OFFICIAL BUILD123D DOCS ---\n{rag_block}\n-------------------------------\n\nUSER REQUEST: {user_prompt}"
                print("RAG Context successfully injected into prompt.")
            else:
                base_prompt = f"{base_prompt_text}\n\nUSER REQUEST: {user_prompt}"
                print("No specific RAG context found. Proceeding with default prompt.")
        else:
            base_prompt = f"{base_prompt_text}\n\nUSER REQUEST: {user_prompt}"
            
        current_prompt = f"{base_prompt}{formatting_anchor}"

        output_dir = os.path.join(run_dir, "models", str(prompt_id))
        os.makedirs(output_dir, exist_ok=True)
        
        # 2. Agent 1 (Planner) extracts intent
        design_intent = extract_design_intent_llm(user_prompt)
        print(f"Agent 1 (Planner) extracted intent: {json.dumps(design_intent, indent=2)}")
        
        error_history = []
        last_known_error = "None" 
        
        for attempt in range(MAX_RETRIES):
            print(f"\n--- Attempt {attempt + 1} of {MAX_RETRIES} ---")
            print(f"Agent 2 (Coder) is thinking... (Calling {LLM_PROVIDER.upper()} API)")
            
            response_text = generate_response(current_prompt, provider=LLM_PROVIDER)
            prompt_updated_in_error = False
            
            if not response_text:
                error_msg = f"Failed to communicate with {LLM_PROVIDER} API."
                code_block = ""
            else:
                match = re.search(r"<code>(.*?)</code>", response_text, re.DOTALL | re.IGNORECASE)
                if not match:
                    match = re.search(r"```(?:python)?(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
                
                if not match:
                    import_idx = response_text.find("from build123d import")
                    if import_idx != -1:
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
                    safe_output_dir = output_dir.replace("\\", "/")
                    # Fallback replacements to catch explicit strings
                    code_block = code_block.replace("generated_files/generated_part", f"{safe_output_dir}/generated_part")
                    
                    # More robust replacement for any hardcoded export paths to use the current output dir 
                    code_block = re.sub(r'(export_stl|export_step)\(.*?,.*?([\'"]).*?([\'"])\)', 
                                        lambda m: f"{m.group(1)}(final_part, {m.group(2)}{safe_output_dir}/generated_part.{'stl' if m.group(1) == 'export_stl' else 'step'}{m.group(3)})", 
                                        code_block)
                    
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
                        
                        def format_condensed_history(history_list):
                            if not history_list: return ""
                            if len(history_list) == 1: return history_list[0]
                            
                            condensed = []
                            for h in history_list[:-1]:
                                if len(h) > 150:
                                    condensed.append(h[:147] + "...")
                                else:
                                    condensed.append(h)
                            
                            condensed.append(history_list[-1]) # Keep latest full
                            return "\n".join(condensed)

                        history_text = format_condensed_history(error_history)
                        current_prompt = f"{base_prompt}\n\n[PAST FAILED ATTEMPTS - DO NOT REPEAT THESE MISTAKES]:\n{history_text}\n\n[ATTEMPT {attempt + 1} FAILED. FIX THIS ERROR:]\n{error_msg}{formatting_anchor}"
                    
                    else:
                        print(f"Unknown error. USE_RAG is {USE_RAG}.")
                        rag_snippet = ""
                        if USE_RAG:
                            error_docs = retrieve_context(str(exec_error), k=1) # RAG Optimization: Limit to k=1
                            rag_snippet = error_docs[0] if error_docs else ""
                            
                        error_msg = raw_error
                        error_history.append(f"- Attempt {attempt + 1} (Syntax Slow-Path): {error_msg}")
                        
                        def format_condensed_history(history_list):
                            if not history_list: return ""
                            if len(history_list) == 1: return history_list[0]
                            
                            condensed = []
                            for h in history_list[:-1]:
                                if len(h) > 150:
                                    condensed.append(h[:147] + "...")
                                else:
                                    condensed.append(h)
                            
                            condensed.append(history_list[-1]) # Keep latest full
                            return "\n".join(condensed)

                        history_text = format_condensed_history(error_history)
                        current_prompt = f"{base_prompt}\n\n[PAST FAILED ATTEMPTS - DO NOT REPEAT THESE MISTAKES]:\n{history_text}\n\n[ATTEMPT {attempt + 1} FAILED. FIX THIS ERROR:]\n{raw_error}"
                        if rag_snippet:
                            current_prompt += f"\n[RELEVANT DOCS TO FIX ERROR:]\n{rag_snippet}"
                        current_prompt += formatting_anchor
                    
                    prompt_updated_in_error = True
                    print(f"Code Execution Failed: {raw_error}")

            last_known_error = error_msg 

            if attempt < MAX_RETRIES - 1:
                if error_msg:
                    print(f"Sending error back to LLM... ({error_msg[:100]}...)")
                    
                    def format_condensed_history(history_list):
                        if not history_list: return ""
                        if len(history_list) == 1: return history_list[0]
                        
                        condensed = []
                        for h in history_list[:-1]:
                            if len(h) > 150:
                                condensed.append(h[:147] + "...")
                            else:
                                condensed.append(h)
                        
                        condensed.append(history_list[-1]) # Keep latest full
                        return "\n".join(condensed)

                    history_text = format_condensed_history(error_history)
                    
                    if not prompt_updated_in_error:
                        current_prompt = f"{base_prompt}\n\n[PAST FAILED ATTEMPTS - DO NOT REPEAT THESE MISTAKES]:\n{history_text}\n\n[ATTEMPT {attempt + 1} FAILED. FIX THIS ERROR:]\n{error_msg}{formatting_anchor}"
            else:
                print("Max retries reached. The agent could not fix the code.")
                log_experiment(user_prompt, design_intent, "FAILED", MAX_RETRIES, last_known_error)
                return {
                    "success": False,
                    "retries": MAX_RETRIES,
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

# Step 4: Output and execution loop
def run_unified_showcase(input_csv):
    run_dir = get_next_run_dir()
    output_csv = os.path.join(run_dir, f"{LLM_PROVIDER}_results.csv")
    json_log_file = os.path.join(run_dir, f"{LLM_PROVIDER}_logs.json")
    
    results = []
    
    print(f"--- Starting {LLM_PROVIDER.upper()} API Showcase Execution (Unified) ---")
    print(f"RAG Enabled: {USE_RAG} | Prompt Type: {PROMPT_TYPE} | Max Retries: {MAX_RETRIES}")
    print(f"Output Directory: {run_dir}")
    
    fieldnames = ['id', 'category', 'success', 'retries', 'execution_time_sec', 'final_error']
    
    with open(json_log_file, 'w', encoding='utf-8') as jf:
        jf.write("[\n")
    
    first_json_entry = True
    
    with open(input_csv, mode='r', encoding='utf-8') as infile, \
         open(output_csv, mode='w', newline='', encoding='utf-8') as outfile:
         
        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in reader:
            prompt_id = row['id']
            category = row['category']
            prompt_text = row['prompt']
            
            print(f"\nProcessing [{prompt_id}] ({category})...")
            start_time = time.time()
            
            result = generate_cad_part_unified(user_prompt=prompt_text, prompt_id=prompt_id, run_dir=run_dir)
            
            success = False
            retries = MAX_RETRIES
            final_error = "Unknown execution error"
            history = []
            
            if result:
                success = result.get("success", False)
                retries = result.get("retries", MAX_RETRIES)
                final_error = result.get("final_error", None)
                history = result.get("history", [])

            execution_time = round(time.time() - start_time, 2)
            
            res_dict = {
                'id': prompt_id,
                'category': category,
                'success': success,
                'retries': retries,
                'execution_time_sec': execution_time,
                'final_error': final_error
            }
            results.append(res_dict)
            
            writer.writerow(res_dict)
            outfile.flush()
            
            json_payload = {
                "prompt_id": prompt_id,
                "category": category,
                "prompt_text": prompt_text,
                "success": success,
                "retries": retries,
                "execution_time_sec": execution_time,
                "final_error": final_error,
                "history": history
            }
            with open(json_log_file, 'a', encoding='utf-8') as jf:
                if not first_json_entry:
                    jf.write(",\n")
                json.dump(json_payload, jf, indent=4)
                first_json_entry = False
            
            print(f"Result: {'PASS' if success else 'FAIL'} | Retries: {retries} | Time: {execution_time}s")
            
    with open(json_log_file, 'a', encoding='utf-8') as jf:
        jf.write("\n]")
            
    print(f"\nUnified executing complete! Analytics saved to {output_csv} and {json_log_file}")

if __name__ == "__main__":
    prompt_file = 'showcase_run/showcase_prompts.csv'
    if not os.path.exists(prompt_file):
        print(f"{prompt_file} not found!")
    else:
        run_unified_showcase(prompt_file)
