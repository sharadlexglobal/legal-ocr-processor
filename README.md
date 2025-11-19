# Legal OCR Processor

**Dual-Engine AI Pipeline for Legal Document Processing**

## Features

- **Dual-Stage OCR Pipeline:**
  - Stage A: Gemini 1.5 Flash 002 (Fast extraction, temp=0.0)
  - Stage B: Gemini 3 Pro Preview (Legal correction, temp=0.1)

- **Rate Limiting:**
  - Flash: 50 concurrent requests
  - Pro: 40 concurrent requests

- **Multi-Format Support:**
  - PDF (page-by-page processing)
  - Images (JPG, PNG)
  - Audio (MP3, WAV, OGG)
  - Documents (DOCX, TXT)

- **Indian Legal Context:**
  - Specialized prompts for legal terminology
  - Corrects OCR errors (e.g., "petitiuner" → "Petitioner")

- **Google Drive Integration:**
  - Automatic report upload
  - Shareable links

## Deployment

### Google Cloud Run

```bash
gcloud run deploy legal-ocr-processor \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 3600 \
  --service-account YOUR_SERVICE_ACCOUNT \
  --set-env-vars PROJECT_ID=YOUR_PROJECT_ID,DRIVE_FOLDER_ID=YOUR_FOLDER_ID
```

## API Endpoints

### `POST /api/auto/external-trigger`

Process legal documents from JSON manifest.

**Request:**
```json
{
  "instructionsText": "Case description",
  "userName": "User Name",
  "userEmail": "user@example.com",
  "userPhone": "1234567890",
  "files": [
    {
      "name": "document.pdf",
      "url": "https://signed-url.com/document.pdf",
      "type": "application/pdf"
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Processing completed successfully",
  "drive_link": "https://drive.google.com/file/d/...",
  "summary": {
    "files_processed": 1,
    "total_pages": 45,
    "report_filename": "Legal_OCR_Report_20251119_120000.txt"
  }
}
```

## Architecture

- **Python 3.11**
- **Flask 3.0.0**
- **Gunicorn** (1 worker, 8 threads)
- **Vertex AI** (google-genai SDK)
- **Async Processing** (asyncio with semaphores)

## License

Proprietary - Built for CourtCraft.ai integration
