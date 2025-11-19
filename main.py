import os
import time
import io
import asyncio
import json
import requests
import docx
from flask import Flask, request, jsonify
from pdf2image import convert_from_bytes
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import google.auth

app = Flask(__name__)

# --- CONFIGURATION ---
PROJECT_ID = os.environ.get("PROJECT_ID")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
LOCATION = "us-central1"

# Initialize Gemini Client with Vertex AI
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# --- RATE LIMITERS ---
# Stage A: Flash (Fast) - Limit to 50 concurrent
SEM_FLASH = asyncio.Semaphore(50)
# Stage B: Pro (Strict) - Limit to 40 concurrent (Buffer for 50 RPM limit)
SEM_PRO = asyncio.Semaphore(40)

def download_file(url):
    """Download file from URL and return content and mime type"""
    try:
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            return io.BytesIO(r.content), r.headers.get('Content-Type', '')
    except Exception as e:
        print(f"Download Error: {e}")
        return None, None

async def process_page_pipeline(image, page_num):
    """
    Executes the 2-Stage Pipeline for a single page.
    Stage 1: Gemini 1.5 Flash 002 - Raw extraction
    Stage 2: Gemini 3 Pro Preview - Legal correction
    """
    # --- STAGE 1: EXTRACTION (Gemini 1.5 Flash) ---
    raw_text = ""
    async with SEM_FLASH:
        try:
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=85)  # Compress slightly for speed
            img_bytes = img_byte_arr.getvalue()
            
            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash-002",
                contents=[
                    types.Part.from_text("Transcribe verbatim. No summary. No markdown."),
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
                ],
                config=types.GenerateContentConfig(temperature=0.0)
            )
            raw_text = response.text
        except Exception as e:
            return (page_num, f"[Stage 1 Error]: {str(e)}")

    # --- STAGE 2: CORRECTION (Gemini 3 Pro) ---
    final_text = ""
    async with SEM_PRO:
        try:
            # Small delay to smooth out RPM spikes
            await asyncio.sleep(0.5)
            
            prompt = f"""You are an expert legal editor. Correct OCR errors in the text below based on Indian legal context.
- Fix spellings (e.g. 'petitiuner' -> 'Petitioner').
- Maintain original structure.
- Do NOT summarize. Return full corrected text.

TEXT:
{raw_text}
"""
            
            response = await client.aio.models.generate_content(
                model="gemini-3-pro-preview",  # Fallback to gemini-1.5-pro-002 if quota fails
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            final_text = response.text
        except Exception as e:
            # Fallback: Return raw text if Pro fails
            return (page_num, f"{raw_text}\n[Stage 2 skipped due to error: {str(e)}]")
    
    return (page_num, final_text)

async def process_pdf(pdf_content):
    """Process PDF by converting to images and running dual-stage pipeline"""
    print("Converting PDF to images...")
    images = convert_from_bytes(pdf_content, fmt='jpeg', thread_count=4)
    total = len(images)
    print(f"Processing {total} pages...")
    
    tasks = [process_page_pipeline(img, i+1) for i, img in enumerate(images)]
    results = await asyncio.gather(*tasks)
    
    # Sort by page number
    results.sort(key=lambda x: x[0])
    
    return "\n".join([f"--- PAGE {r[0]} ---\n{r[1]}" for r in results])

async def process_image(image_bytes):
    """Process single image through dual-stage pipeline"""
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(image_bytes))
        _, text = await process_page_pipeline(image, 1)
        return text
    except Exception as e:
        return f"[Image Processing Error]: {str(e)}"

async def process_audio(audio_bytes, mime_type):
    """Process audio file using Gemini Flash"""
    async with SEM_FLASH:
        try:
            response = await client.aio.models.generate_content(
                model="gemini-1.5-flash-002",
                contents=[
                    types.Part.from_text("Transcribe this audio verbatim. Include all spoken words."),
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
                ],
                config=types.GenerateContentConfig(temperature=0.0)
            )
            return response.text
        except Exception as e:
            return f"[Audio Processing Error]: {str(e)}"

def process_docx(docx_bytes):
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(io.BytesIO(docx_bytes))
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        return f"[DOCX Processing Error]: {str(e)}"

def save_to_drive(text_content, filename="Legal_Analysis_Output.txt"):
    """Save processed text to Google Drive"""
    try:
        creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        
        metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(text_content.encode('utf-8')), mimetype='text/plain')
        
        file = service.files().create(body=metadata, media_body=media, fields='id,webViewLink').execute()
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        print(f"Drive save error: {e}")
        return None, None

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return jsonify({
        "message": "Legal OCR Processor API - Dual Engine Pipeline",
        "version": "2.0",
        "models": {
            "extraction": "gemini-1.5-flash-002",
            "correction": "gemini-3-pro-preview"
        },
        "endpoints": {
            "health": "/health",
            "process": "/api/auto/external-trigger"
        }
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Legal OCR Processor - Dual Engine",
        "version": "2.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

@app.route('/api/auto/external-trigger', methods=['POST'])
def webhook():
    """Main processing endpoint for CourtCraft.ai integration"""
    data = request.json
    
    if not data or 'files' not in data:
        return jsonify({"error": "No files provided"}), 400
    
    final_report = []
    final_report.append(f"=== LEGAL OCR PROCESSING REPORT ===")
    final_report.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    final_report.append(f"Instructions: {data.get('instructionsText', 'N/A')}")
    final_report.append(f"User: {data.get('userName', 'N/A')} ({data.get('userEmail', 'N/A')})")
    final_report.append(f"\n{'='*60}\n")
    
    files_processed = 0
    total_pages = 0
    
    for f in data.get('files', []):
        url = f.get('url')
        filename = f.get('name', 'unknown')
        
        if not url:
            continue
            
        print(f"Processing: {filename}")
        final_report.append(f"\n=== FILE: {filename} ===")
        final_report.append(f"URL: {url}\n")
        
        content, mime = download_file(url)
        if not content:
            final_report.append("[ERROR] Failed to download file\n")
            continue
        
        processed_text = ""
        
        try:
            # PDF Processing
            if 'pdf' in mime.lower() or url.lower().endswith('.pdf'):
                processed_text = asyncio.run(process_pdf(content.read()))
                page_count = processed_text.count('--- PAGE')
                total_pages += page_count
                
            # Image Processing
            elif any(img_type in mime.lower() for img_type in ['image/jpeg', 'image/png', 'image/jpg']):
                processed_text = asyncio.run(process_image(content.read()))
                total_pages += 1
                
            # Audio Processing
            elif any(audio_type in mime.lower() for audio_type in ['audio/', 'video/']):
                processed_text = asyncio.run(process_audio(content.read(), mime))
                
            # DOCX Processing
            elif 'wordprocessingml' in mime.lower() or url.lower().endswith('.docx'):
                processed_text = process_docx(content.read())
                
            # Plain Text
            elif 'text/plain' in mime.lower() or url.lower().endswith('.txt'):
                processed_text = content.read().decode('utf-8', errors='ignore')
            
            else:
                processed_text = f"[UNSUPPORTED FILE TYPE: {mime}]"
            
            final_report.append(processed_text)
            files_processed += 1
            
        except Exception as e:
            final_report.append(f"[PROCESSING ERROR]: {str(e)}")
    
    # Save to Drive
    final_report_text = "\n".join(final_report)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    filename = f"Legal_OCR_Report_{timestamp}.txt"
    
    file_id, drive_link = save_to_drive(final_report_text, filename)
    
    response = {
        "status": "success",
        "message": "Processing completed successfully",
        "summary": {
            "files_processed": files_processed,
            "total_pages": total_pages,
            "report_filename": filename
        }
    }
    
    if drive_link:
        response["drive_link"] = drive_link
        response["drive_file_id"] = file_id
    else:
        response["warning"] = "Drive upload failed, returning text in response"
        response["report_text"] = final_report_text
    
    return jsonify(response), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
