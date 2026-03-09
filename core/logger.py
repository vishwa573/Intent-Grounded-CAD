 # core/logger.py
import csv
import os
import json
from datetime import datetime

LOG_FILE = "experiment_logs.csv"

def init_logger():
    """Creates the CSV file with headers if it doesn't exist."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Prompt", "Intent", "Status", "Attempts_Needed", "Final_Error"])

def log_experiment(prompt, intent, status, attempts, error_msg="None"):
    """Appends a single experiment result to the CSV."""
    init_logger()
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Convert intent dict to a compact JSON string for the CSV
        intent_str = json.dumps(intent)
        
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            prompt,
            intent_str,
            status,
            attempts,
            error_msg
        ])