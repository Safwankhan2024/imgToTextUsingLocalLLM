# Local Django VL Text Extractor

A privacy-first, local-only Django application designed to extract text from images using local Vision-Language (VL) models like `llama.cpp`, `vLLM`, or `LM Studio`.

It allows users to upload screenshots (e.g., pages of a book), visually sequence them via a drag-and-drop web interface, and process them asynchronously in the background. It features robust safety mechanisms, including SQLite WAL mode to prevent database locks, and immediate localized text file backups to prevent data loss.

## Features
- **100% Local Processing:** No telemetry, no external API calls, completely disconnected capabilities.
- **Real-Time Progress Tracking:** Live polling via HTMX shows page extraction status (Pending, Processing, Completed, Error) and progress counter—all without page refresh.
- **Visual Sequencer:** Drag and drop uploaded images to ensure the text extraction perfectly matches the original sequence.
- **Hash-Aware Ordering:** Each uploaded image is fingerprinted with a SHA-256 hash and reorder operations persist hash+position so stitched output always follows your exact arrangement.
- **Hierarchical Structuring:** Categorize uploads by Book and Chapter.
- **Asynchronous Execution:** Uses `Django-Huey` for background processing so the UI remains completely responsive during heavy LLM inference.
- **Failsafe Text Backups:** Automatically appends extracted text to a raw `_fallback.txt` physical file immediately upon completion, bypassing the database as an extra safety measure.

## Requirements
- Python 3.10+
- A local Vision-Language model (e.g., LLaVA running via `llama.cpp`) that provides an OpenAI-compatible API endpoint.

## Installation

1. **Clone the repository and set up a Virtual Environment**
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\Activate.ps1
   # Linux/Mac:
   source venv/bin/activate
   ```

2. **Install exact dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Environment Variables**
   Copy the example environment file and adjust it to point to your local LLM node:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to match your local setup configuration. Important settings include `VL_API_BASE`, `VL_MODEL`, and `LLM_TIMEOUT`.

4. **Apply Database Migrations**
   ```bash
   python manage.py migrate
   ```

## Running the Application

To run this application seamlessly, you must run both the Django web server and the Huey background worker at the same time.

**Terminal 1 — The Web Server:**
```bash
.\venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000
```

**Terminal 2 — The Background Worker:**
```bash
.\venv\Scripts\Activate.ps1
python manage.py run_huey
```

## Usage
1. Navigate to `http://127.0.0.1:8000` in your browser.
2. Create a **Book** (e.g., `"Manual"`).
3. Create a **Chapter** assigned to that Book (e.g., `"Preface"`).
4. Click into the Chapter and upload your screenshots.
5. Drag and drop the thumbnails to ensure they are in the exact structural order.
6. The app remembers each image hash and its new position whenever you reorder.
7. Click **`Start VL Extraction`**. 
8. The page status badges and progress counter update in real-time (every 2 seconds) as pages complete.
9. Extraction automatically stops polling when all pages reach `COMPLETED` or `ERROR` state.
10. Check your project folder; you will see physical `_fallback.txt` files generating in real time! You can also click **Review Text** on the chapter page to view the stitched result.
