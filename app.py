from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time
import json

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "/tmp/clipflow"
JOBS_FILE = "/tmp/clipflow/jobs.json"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def load_jobs():
    try:
        with open(JOBS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_jobs(jobs):
    try:
        with open(JOBS_FILE, "w") as f:
            json.dump(jobs, f)
    except:
        pass

def cleanup_file(path, delay=300):
    def _delete():
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    threading.Thread(target=_delete, daemon=True).start()

def get_ydl_opts(job_id, quality="720", format_type="mp4", remove_audio=False):
    output_path = os.path.jo
