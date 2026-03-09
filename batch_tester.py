import os
import csv
import json
import time
from dotenv import load_dotenv
from backend import generate_cad_part


# --- CONFIGURATION ---
LLM_PROVIDER = "local"  # Defaulting to local for the 30-prompt batch
USE_RAG = True          
MAX_RETRIES = 15
PROMPT_TYPE = "local" # Using the optimized PROMPT_LOCAL for 7B models

load_dotenv()

def get_next_run_dir(base_dir="results"):
    """Determines the next available versioned directory for the batch test runs."""
    os.makedirs(base_dir, exist_ok=True)
    existing_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and d.startswith(f"{LLM_PROVIDER}_run_v")]
    
    max_ver = 0
    for d in existing_dirs:
        try:
            ver = int(d.split('_v')[-1])
            if ver > max_ver:
                max_ver = ver
        except ValueError:
            pass
            
    next_ver = max_ver + 1
    new_dir = os.path.join(base_dir, f"{LLM_PROVIDER}_run_v{next_ver}")
    os.makedirs(new_dir, exist_ok=True)
    return new_dir


def run_batch_test(input_csv):
    run_dir = get_next_run_dir()
    output_csv = os.path.join(run_dir, f"{LLM_PROVIDER}_results.csv")
    json_log_file = os.path.join(run_dir, f"{LLM_PROVIDER}_logs.json")
    
    results = []
    
    print(f"--- Starting {LLM_PROVIDER.upper()} API Batch Execution (Master Test) ---")
    print(f"RAG Enabled: {USE_RAG} | Prompt Type: {PROMPT_TYPE} | Max Retries: {MAX_RETRIES}")
    print(f"Output Directory: {run_dir}")
    
    fieldnames = ['id', 'category', 'success', 'retries', 'execution_time_sec', 'final_error', 'syntax_errors', 'physics_errors']
    
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
            
            try:
                result = generate_cad_part(
                    user_prompt=prompt_text, 
                    prompt_id=prompt_id, 
                    run_dir=run_dir,
                    provider=LLM_PROVIDER,
                    use_rag=USE_RAG,
                    max_retries=MAX_RETRIES,
                    prompt_type=PROMPT_TYPE
                )
                
                success = False
                retries = MAX_RETRIES
                final_error = "Unknown execution error"
                history = []
                syntax_errors = 0
                physics_errors = 0
                
                if result:
                    success = result.get("success", False)
                    retries = result.get("retries", MAX_RETRIES)
                    final_error = result.get("final_error", None)
                    history = result.get("history", [])
                    syntax_errors = result.get("syntax_errors", 0)
                    physics_errors = result.get("physics_errors", 0)
            except Exception as e:
                print(f"Catastrophic failure processing prompt {prompt_id}: {e}")
                success = False
                retries = MAX_RETRIES
                final_error = f"Catastrophic Crash: {str(e)}"
                history = []
                syntax_errors = 0
                physics_errors = 0

            execution_time = round(time.time() - start_time, 2)
            
            res_dict = {
                'id': prompt_id,
                'category': category,
                'success': success,
                'retries': retries,
                'execution_time_sec': execution_time,
                'final_error': final_error,
                'syntax_errors': syntax_errors,
                'physics_errors': physics_errors
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
                "syntax_errors": syntax_errors,
                "physics_errors": physics_errors,
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
            
    print(f"\nBatch Master executing complete! Analytics saved to {output_csv} and {json_log_file}")

if __name__ == "__main__":
    prompt_file = 'prompts.csv'
    if not os.path.exists(prompt_file):
        print(f"{prompt_file} not found!")
    else:
        run_batch_test(prompt_file)
