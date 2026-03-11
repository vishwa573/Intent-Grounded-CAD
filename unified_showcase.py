import os
import csv
import json
import time
from dotenv import load_dotenv

# --- CONFIGURATION ---
LLM_PROVIDER = "local"  # Options: "gemini", "groq", "local"
USE_RAG = True          # Set to False to disable RAG (saves tokens for Groq)
MAX_RETRIES = 5
PROMPT_TYPE = "local" # Options: "gemini", "groq"

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

from backend import generate_cad_part

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
            
            result = generate_cad_part(
                user_prompt=prompt_text, 
                prompt_id=prompt_id, 
                run_dir=run_dir, 
                provider=LLM_PROVIDER, 
                use_rag=USE_RAG, 
                max_retries=MAX_RETRIES, 
                prompt_type=PROMPT_TYPE
            )

            execution_time = round(time.time() - start_time, 2)
            
            success = result.get('success', False)
            retries = result.get('retries', 0)
            final_error = result.get('final_error', None)
            history = result.get('history', [])
            
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
