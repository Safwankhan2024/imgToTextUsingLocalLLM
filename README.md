# Local Django VL Text Extractor

Privacy-first Django app for extracting text from page images with a local vision-language model through an OpenAI-compatible endpoint.

You can organize content by book/chapter, upload multiple images, reorder them with drag-and-drop, run background extraction with Huey, and review stitched output in the app.

## What It Currently Does
- Local-first workflow with configurable local API endpoint (`VL_API_BASE`).
- Book and chapter management from the dashboard.
- Multi-image upload per chapter.
- Drag-and-drop page ordering persisted to the database.
- SHA-256 hash stored for each uploaded image.
- Background extraction using `django-huey` + SQLite Huey queue.
- Per-page extraction status (`PENDING`, `PROCESSING`, `COMPLETED`, `ERROR`).
- Fallback text backups written to `<Book>_<Chapter>_fallback.txt` in the project root.
- Publication year lookup from evidence files via `review/*.evidence.txt`.
  - Scans `TITLE:` markers in evidence files.
  - Uses DuckDuckGo search and local text LLM prompts to infer publication years.
  - Stores results in a DB-backed `TitleLookupTask` and writes a JSON artifact under `review/`.

## Requirements
- Python 3.10+
- A local VL model server that exposes an OpenAI-compatible `chat/completions` endpoint.
- `duckduckgo_search` for publication year lookup.

## Setup

1. Create and activate a virtual environment.
   ```bash
   python -m venv venv
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies.
   ```bash
   pip install -r requirements.txt
   pip install django django-huey python-dotenv requests pillow
   ```

3. Copy environment configuration.
   ```bash
   copy .env.example .env
   ```

4. Update `.env` values for your local model endpoint.
   - `VL_API_BASE`
   - `VL_MODEL`
   - `LLM_TIMEOUT`
   - `LLM_RETRIES`
   - `LLM_MAX_TOKENS`
   - `LLM_ENABLE_THINKING`

5. Run migrations.
   ```bash
   python manage.py migrate
   ```

## Run

Start both processes:

1. Django web server
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

2. Huey worker
   ```bash
   python manage.py run_huey
   ```

Open `http://127.0.0.1:8000`.

## Usage
1. Create a book.
2. Create a chapter under that book.
3. Open the chapter and upload page images.
4. Reorder pages by dragging cards.
5. Click `Start VL Extraction`.
6. Open `Review Text` to view stitched extracted content.
7. Use the `Lookup Years` navigation button to scan `review/*.evidence.txt` and infer publication years for extracted titles.
8. Check project root for generated `_fallback.txt` files.

## Notes
- A `requirements.txt` file is included and contains the `duckduckgo_search` dependency required by the title lookup feature.
- Static files are already present under `staticfiles/` in this repo snapshot.
