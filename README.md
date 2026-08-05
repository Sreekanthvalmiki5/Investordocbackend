# InvestorDocs AI — Backend

FastAPI backend for the InvestorDocs AI platform: financial document analysis
with a local RAG pipeline, AI chat, voice queries, image analysis, Google OAuth,
email verification, and bookmarking.

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows (bash: source venv/Scripts/activate)
pip install -r requirements.txt
cp .env.example .env             # then fill in real values
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000` (`/docs` for Swagger).

## Voice queries (speech-to-text)

Voice recordings are transcribed **fully locally** with
[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) — no OpenAI key is
required for transcription. The transcript is then fed into the same RAG/chat
pipeline as a typed message.

Flow: `POST /api/chat/voice` → upload audio → Faster-Whisper (local) →
transcript → RAG retrieval → LLM answer → same response shape as `POST /api/chat`.

### Installation

```bash
pip install faster-whisper
```

Faster-Whisper ships with the `ctranslate2` + `av` (PyAV) decoding stack. On
most platforms PyAV bundles the FFmpeg libraries it needs, but a system FFmpeg
install is recommended so every container format decodes reliably.

### FFmpeg installation

- **Windows**: download from https://www.gyan.dev/ffmpeg/builds/ (or
  `winget install ffmpeg`), and add the `bin` folder to your `PATH`.
- **Linux (Debian/Ubuntu)**: `sudo apt install ffmpeg`
- **macOS**: `brew install ffmpeg`

Verify with `ffmpeg -version`.

### How the model works

The first time a voice request is made, Faster-Whisper downloads the model
weights from Hugging Face (e.g. `Systran/faster-whisper-small`, ~460 MB) into
the local HF cache and loads it into memory. Subsequent requests reuse the
already-loaded model — it is loaded **once per process** and never reloaded per
request (`app/services/transcription_service.py` is a singleton).

### Changing the model size

Set `WHISPER_MODEL` in `.env` (default `small`). No code changes needed:

```
WHISPER_MODEL=tiny        # fastest, lowest accuracy
WHISPER_MODEL=base
WHISPER_MODEL=small       # default — good balance
WHISPER_MODEL=medium
WHISPER_MODEL=large-v3    # best accuracy, slowest on CPU
```

Optional tuning (already defaulted for CPU):

```
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

Smaller models download faster and run quicker; larger models are more accurate
but need more RAM and CPU time.

### Accepted formats

`wav`, `mp3`, `m4a`, `webm` (uploads are validated by extension + MIME type and
capped at `MAX_AUDIO_UPLOAD_MB`, default 25 MB). Clean error messages are
returned for empty audio, corrupted files, and recordings with no speech.

## Environment variables

See `.env.example` for the full list. Highlights:

- `DATABASE_URL` / `VECTOR_DB_URL` — PostgreSQL + PGVector
- `JWT_SECRET_KEY` — JWT signing
- `FRONTEND_URL` — email links + Google OAuth redirect
- `OPENROUTER_API_KEY` — LLM routing + vision + embeddings fallback
- `OPENAI_API_KEY` — optional; OpenAI embeddings (voice is local now)
- `SMTP_*` — transactional email (verification, login notifications, reset)

## Feature notes

- **Email retry scheduler**: failed emails are persisted to the `email_outbox`
  table and re-sent every `EMAIL_RETRY_INTERVAL_MINUTES` (default 10).
- **Embedding scheduler**: pending documents are embedded every 30 minutes.
- **Bookmarks**: `GET/POST/DELETE /api/bookmarks` are user-scoped (ownership is
  enforced in the delete query).
