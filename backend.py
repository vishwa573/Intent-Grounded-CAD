import os
import re
import json
import time

from prompts import PROMPT_GEMINI, PROMPT_GROQ, PROMPT_LOCAL
from core.validators import extract_design_intent_llm, validate_geometry
from core.rag_manager import retrieve_context
from core.logger import log_experiment
from core.llm_client import generate_response

def generate_cad_part(user_prompt, prompt_id="default", run_dir="generated_files", provider="local", use_rag=True, max_retries=15, prompt_type="groq"):
    """
    The Single Source of Truth for the AI workflow execution.
    Parameters match dynamic requirements from API testing and local benchmarking.
    """
    design_intent = {}  
    try:
        print(f"\n🚀 NEW USER REQUEST: {user_prompt}")

        if prompt_type == "gemini":
            base_prompt_text = PROMPT_GEMINI
        elif prompt_type == "groq":
            base_prompt_text = PROMPT_GROQ
        else:
            base_prompt_text = PROMPT_LOCAL
        formatting_anchor = "\n\nCRITICAL: Output ONLY the raw Python script inside ```python ... ``` blocks. No explanations. No markdown outside the block."
        
        if use_rag:
            print("Retrieving official build123d documentation...")
            retrieved_context = retrieve_context(user_prompt, k=1) 
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
        syntax_errors_caught = 0
        physics_errors_caught = 0
        
        for attempt in range(max_retries):
            print(f"\n--- Attempt {attempt + 1} of {max_retries} ---")
            print(f"Agent 2 (Coder) is thinking... (Calling {provider.upper()} API)")
            
            response_text = generate_response(current_prompt, provider=provider)
            prompt_updated_in_error = False
            
            if not response_text:
                error_msg = f"Failed to communicate with {provider} API."
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
                    code_block = code_block.replace("generated_files/generated_part", f"{safe_output_dir}/generated_part")
                    
                    code_block = re.sub(r'(export_stl|export_step)\(.*?,.*?([\'"]).*?([\'"])\)', 
                                        lambda m: f"{m.group(1)}(final_part, {m.group(2)}{safe_output_dir}/generated_part.{'stl' if m.group(1) == 'export_stl' else 'step'}{m.group(3)})", 
                                        code_block)
                    
                    exec(code_block, exec_globals)
                    final_part = exec_globals.get("final_part") or exec_globals.get("part")
                    if final_part is None:
                         raise ValueError("The variable 'final_part' (or 'part') was not assigned.")

                    # 3. Active Physics Validation (Auto-Grounding)
                    try:
                        z_min_offset = final_part.bounding_box().min.Z
                        if abs(z_min_offset) > 0.05:
                            final_part = final_part.translate((0, 0, -z_min_offset))
                            print(f"[AUTO-GROUND] Part was floating at Z={z_min_offset:.2f}. Shifted to Z=0.0")
                    except Exception as e:
                        z_min_offset = 0.0

                    is_valid, report = validate_geometry(final_part, intent=design_intent, user_prompt=user_prompt, z_offset=z_min_offset)

                    if not is_valid:
                        physics_errors_caught += 1
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
                                "stl": os.path.join(output_dir, stl_file) if stl_file else None,
                                "syntax_errors": syntax_errors_caught,
                                "physics_errors": physics_errors_caught
                            }
                        else:
                            error_msg = "CRITICAL: The geometry is valid, but you forgot to export! You MUST include these exact two lines at the end of your script:\nexport_stl(final_part, 'generated_files/generated_part.stl')\nexport_step(final_part, 'generated_files/generated_part.step')"
                
                except Exception as exec_error:
                    syntax_errors_caught += 1
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
                        print(f"Unknown error. USE_RAG is {use_rag}.")
                        rag_snippet = ""
                        if use_rag:
                            error_docs = retrieve_context(str(exec_error), k=1) 
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

            if attempt < max_retries - 1:
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
                log_experiment(user_prompt, design_intent, "FAILED", max_retries, last_known_error)
                return {
                    "success": False,
                    "retries": max_retries,
                    "final_error": last_known_error,
                    "history": error_history,
                    "step": None,
                    "stl": None,
                    "syntax_errors": syntax_errors_caught,
                    "physics_errors": physics_errors_caught
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
            "stl": None,
            "syntax_errors": 0,
            "physics_errors": 0
        }

