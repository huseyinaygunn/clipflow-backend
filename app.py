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
    output_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")
    if format_type == "mp3":
        return {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
        }
    quality_map = {
        "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
    }
    fmt = quality_map.get(quality, quality_map["720"])
    opts = {
        "format": fmt,
        "outtmpl": output_path,
        "merge_output_format": "mp4",
        "quiet": True,
    }
    if remove_audio:
        opts["postprocessor_args"] = ["-an"]
    return opts

def download_video(job_id, url, quality, format_type, remove_audio):
    jobs = load_jobs()
    jobs[job_id]["status"] = "processing"
    jobs[job_id]["progress"] = 0
    save_jobs(jobs)

    def progress_hook(d):
        jobs = load_jobs()
        if job_id not in jobs:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
            downloaded = d.get("downloaded_bytes", 0)
            jobs[job_id]["progress"] = round((downloaded / total) * 100, 1)
        elif d["status"] == "finished":
            jobs[job_id]["progress"] = 100
        save_jobs(jobs)

    opts = get_ydl_opts(job_id, quality, format_type, remove_audio)
    opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
        ext = "mp3" if format_type == "mp3" else "mp4"
        file_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.{ext}")
        jobs = load_jobs()
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["file_path"] = file_path
        jobs[job_id]["title"] = title
        jobs[job_id]["ext"] = ext
        save_jobs(jobs)
        cleanup_file(file_path)
    except Exception as e:
        jobs = load_jobs()
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            save_jobs(jobs)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ClipFlow Backend"})

@app.route("/download", methods=["POST"])
def start_download():
    data = request.get_json()
    url         = data.get("url", "").strip()
    quality     = data.get("quality", "720")
    format_type = data.get("format", "mp4")
    remove_audio = data.get("removeAudio", False)
    if not url:
        return jsonify({"error": "URL gerekli"}), 400
    job_id = str(uuid.uuid4())
    jobs = load_jobs()
    jobs[job_id] = {"status": "waiting", "progress": 0}
    save_jobs(jobs)
    thread = threading.Thread(
        target=download_video,
        args=(job_id, url, quality, format_type, remove_audio),
        daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id})

@app.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    jobs = load_jobs()
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "İş bulunamadı"}), 404
    response = {
        "status":   job["status"],
        "progress": job.get("progress", 0),
    }
    if job["status"] == "completed":
        response["title"] = job.get("title", "video")
        response["download_url"] = f"/file/{job_id}"
    if job["status"] == "failed":
        response["error"] = job.get("error", "Bilinmeyen hata")
    return jsonify(response)

@app.route("/file/<job_id>", methods=["GET"])
def get_file(job_id):
    jobs = load_jobs()
    job = jobs.get(job_id)
    if not job or job["status"] != "completed":
        return jsonify({"error": "Dosya hazır değil"}), 404
    file_path = job.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Dosya bulunamadı"}), 404
    ext = job.get("ext", "mp4")
    mime = "audio/mpeg" if ext == "mp3" else "video/mp4"
    return send_file(
        file_path,
        mimetype=mime,
        as_attachment=True,
        download_name=f"{job.get('title', 'video')}.{ext}"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
