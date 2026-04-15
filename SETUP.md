# AI Content Empire — Setup Guide

## Prerequisites
- Python 3.10+
- Node.js 18+
- ComfyUI installed with Flux Schnell models
- Ollama optional for prompt refining, caption generation, and chat

## Runtime Notes
- The app is configured for a Flux-first workflow.
- The frontend now defaults to `http://localhost:8000` for the backend API.
- To use a different backend URL, set `NEXT_PUBLIC_API_URL` before starting the frontend.
- To route only ShadowVid/video generation to a different backend, set `NEXT_PUBLIC_VIDEO_API_URL`. If omitted, video uses the same backend as the rest of the app.
- To proxy ShadowVid from the backend into a dedicated true-video service, set `VIDEO_SERVICE_URL` on that backend. Optional overrides: `VIDEO_SERVICE_PRESETS_PATH`, `VIDEO_SERVICE_GENERATE_PATH`, and `VIDEO_SERVICE_REFINE_PATH`.
- To allow non-local frontend origins such as a Tailscale URL, set `FRONTEND_ORIGINS` on the backend as a comma-separated list.
- Backend startup supports both `uvicorn backend.main:app` from repo root and local backend-module execution.

## Required Flux Models (in ComfyUI folders)
Place these in your ComfyUI `models/` directories:
- `models/unet/flux1-schnell.safetensors`
- `models/clip/t5xxl_fp16.safetensors`
- `models/clip/clip_l.safetensors`
- `models/vae/ae.safetensors`

---

## Step 1: Start ComfyUI

If you have a local ComfyUI checkout in `~/Documents/ComfyUI`, the backend can try to detect and use it automatically. Manual startup is still the most reliable option.

### Windows PowerShell
```powershell
cd $HOME\Documents\ComfyUI
python main.py --force-fp16
```

### macOS / Linux
```bash
cd ~/Documents/ComfyUI   # or wherever yours is installed
python main.py --force-fp16
```
Verify it's running: http://127.0.0.1:8188

## Step 2: Start Backend

### Windows PowerShell
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
# Optional: allow Mac frontend over Tailscale
# $env:FRONTEND_ORIGINS="http://localhost:3000,http://maxbluewirks.tail891b50.ts.net:3000"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### macOS / Linux
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
# Optional: allow Mac frontend over Tailscale
# export FRONTEND_ORIGINS="http://localhost:3000,http://maxbluewirks.tail891b50.ts.net:3000"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
> **Note:** Run uvicorn from the project root (`Empire/`), not from inside `backend/`.
> The command is: `cd /path/to/Empire && uvicorn backend.main:app --reload`

Verify it's running: http://localhost:8000/health

## Step 3: Start Frontend

Tracked frontend modes:
- `npm run dev:local` copies `frontend/env/local.env` to `frontend/.env.local` and starts the app.
- `npm run dev:split` copies `frontend/env/split.env` to `frontend/.env.local` and starts the app.

### Windows PowerShell
```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL="http://your-mac-backend:8000"   # optional, keep main app traffic on your Mac
$env:NEXT_PUBLIC_VIDEO_API_URL="http://shadow-wirks.tail891b50.ts.net:8000"   # optional, send only ShadowVid traffic to the PC over Tailscale
npm run dev
# or use one of the tracked modes:
# npm run dev:local
# npm run dev:split
```

### macOS / Linux
```bash
cd frontend
npm install
# export NEXT_PUBLIC_API_URL=http://your-mac-backend:8000   # optional, keep main app traffic on your Mac
# export NEXT_PUBLIC_VIDEO_API_URL=http://shadow-wirks.tail891b50.ts.net:8000   # optional, send only ShadowVid traffic to the PC over Tailscale
npm run dev
# or use one of the tracked modes:
# npm run dev:local
# npm run dev:split
```
Open: http://localhost:3000

## Split Deployment Map
- Keep these on the main backend: personas, image generation, generations polling, image proxying, content sets, vault, chat, analytics, links, schedules, captions, prompt refine, voice features, LoRA training, cleanup.
- ShadowVid can be split to a dedicated video backend or a dedicated video service behind that backend.
- The ShadowVid frontend now uses `GET /presets/videos`, `POST /refine-video-prompt`, and `POST /generate-video/{persona_id}` on the video side.

## Dedicated Video Service
- ShadowVid no longer falls back to the built-in local 16-frame workflow. The video backend now requires `VIDEO_SERVICE_URL`.
- `GET /presets/videos` proxies to the dedicated video service path in `VIDEO_SERVICE_PRESETS_PATH`.
- `POST /refine-video-prompt` proxies to the dedicated video service path in `VIDEO_SERVICE_REFINE_PATH`.
- `POST /generate-video/{persona_id}` proxies to the dedicated video service path in `VIDEO_SERVICE_GENERATE_PATH`.
- `VIDEO_SERVICE_GENERATE_PATH` supports `{persona_id}` in the path template, for example `/api/v1/personas/{persona_id}/generate`.
- Proxied payload fields: `persona_id`, `persona_name`, `persona_prompt_base`, `prompt_extra`, `full_prompt`, `batch_size`, `negative_prompt`, `lora_override`.
- Video prompt refinement payload fields: `prompt`, `intensity`.

### Example Video Backend Environment
```powershell
$env:VIDEO_SERVICE_URL="http://your-true-video-service:9000"
$env:VIDEO_SERVICE_PRESETS_PATH="/api/v1/video-presets"
$env:VIDEO_SERVICE_REFINE_PATH="/api/v1/refine"
$env:VIDEO_SERVICE_GENERATE_PATH="/api/v1/personas/{persona_id}/generate"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## PC Verification Notes
- This PC currently does not have the required Flux model files detected under the ComfyUI model folders.
- This PC also does not currently show any ComfyUI custom nodes installed.
- If you use a dedicated external video service through `VIDEO_SERVICE_URL`, those missing local ComfyUI assets on the PC may no longer matter.

---

## Architecture
```
User → Next.js (:3000) → FastAPI (:8000) → ComfyUI (:8188) → outputs/
```

## API Endpoints
| Method | Endpoint                        | Description          |
|--------|---------------------------------|----------------------|
| GET    | /health                         | API + ComfyUI status |
| POST   | /personas/                      | Create persona       |
| GET    | /personas/                      | List all personas    |
| DELETE | /personas/{id}                  | Delete persona       |
| POST   | /generate/{persona_id}          | Trigger generation   |
| GET    | /generations/                   | List recent jobs     |
| GET    | /generations/{id}/status        | Check job status     |
| POST   | /links/                         | Add money link       |
| GET    | /links/                         | List all links       |
| DELETE | /links/{id}                     | Delete link          |

## Troubleshooting
- Frontend cannot connect: confirm the backend is running on `http://localhost:8000` or set `NEXT_PUBLIC_API_URL` to the correct URL before `npm run dev`.
- ShadowVid video errors: confirm the video backend has `VIDEO_SERVICE_URL` configured and that `VIDEO_SERVICE_PRESETS_PATH`, `VIDEO_SERVICE_REFINE_PATH`, and `VIDEO_SERVICE_GENERATE_PATH` match the real service.
- ComfyUI not detected: start ComfyUI manually first, then refresh `/health`.
- Prompt refine or chat errors: Ollama is optional, but those features require it to be running locally.
