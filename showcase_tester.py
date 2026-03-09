import csv
import time
import os
import json
from backend import generate_cad_part

def run_batch_test(input_csv, output_csv, test_retries=8):
    results = []
    
    print(f"--- Starting Batch Execution with max_retries={test_retries} ---")
    
    fieldnames = ['id', 'category', 'success', 'retries', 'execution_time_sec', 'final_error']
    json_log_file = 'showcase_run/showcase_logs.json'
    
    # Initialize an empty JSON array file to append to
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
            
            # --- PIPELINE INTEGRATION ---
            # Using prompt_id to isolate output files in generated_files/<id>
            result = generate_cad_part(user_prompt=prompt_text, prompt_id=prompt_id, max_retries=test_retries)
            
            success = False
            retries = test_retries
            final_error = "Unknown execution error"
            history = []
            
            if result:
                success = result.get("success", False)
                retries = result.get("retries", test_retries)
                final_error = result.get("final_error", None)
                history = result.get("history", [])

            execution_time = round(time.time() - start_time, 2)
            
            # Log the metrics
            res_dict = {
                'id': prompt_id,
                'category': category,
                'success': success,
                'retries': retries,
                'execution_time_sec': execution_time,
                'final_error': final_error
            }
            results.append(res_dict)
            
            # Write immediately to CSV
            writer.writerow(res_dict)
            outfile.flush()
            
            # Write immediately to JSON Log
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
            
    # Close off the JSON array
    with open(json_log_file, 'a', encoding='utf-8') as jf:
        jf.write("\n]")
            
    print(f"\nBatch testing complete! Analytics saved to {output_csv} and {json_log_file}")

if __name__ == "__main__":
    # Ensure you have your showcase_run/showcase_prompts.csv created before running
    if not os.path.exists('showcase_run/showcase_prompts.csv'):
        print("showcase_run/showcase_prompts.csv not found!")
    else:
        out_file = 'showcase_run/showcase_results.csv'
        run_batch_test('showcase_run/showcase_prompts.csv', out_file, test_retries=22)
