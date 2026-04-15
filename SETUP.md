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
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### macOS / Linux
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
> **Note:** Run uvicorn from the project root (`Empire/`), not from inside `backend/`.
> The command is: `cd /path/to/Empire && uvicorn backend.main:app --reload`

Verify it's running: http://localhost:8000/health

## Step 3: Start Frontend

### Windows PowerShell
```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"   # optional, only if overriding default
npm run dev
```

### macOS / Linux
```bash
cd frontend
npm install
# export NEXT_PUBLIC_API_URL=http://localhost:8000   # optional, only if overriding default
npm run dev
```
Open: http://localhost:3000

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
- ComfyUI not detected: start ComfyUI manually first, then refresh `/health`.
- Prompt refine or chat errors: Ollama is optional, but those features require it to be running locally.
