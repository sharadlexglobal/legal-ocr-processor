import os
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "letterbox-460006")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        "message": "Legal OCR Processor API - Minimal Working Version",
        "version": "1.0-minimal",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "process": "/api/auto/external-trigger"
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Legal OCR Processor",
        "version": "1.0-minimal",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

@app.route('/api/auto/external-trigger', methods=['POST'])
def process_webhook():
    try:
        data = request.json or {}
        return jsonify({
            "status": "success",
            "message": "Minimal version - endpoints working!",
            "received": {
                "files_count": len(data.get('files', [])),
                "user": data.get('userName', 'N/A')
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
