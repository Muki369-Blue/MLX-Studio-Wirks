# AI Content Empire — Setup Guide

## Prerequisites
- Python 3.10+
- Node.js 18+
- ComfyUI installed with Flux Schnell models

## Required Flux Models (in ComfyUI folders)
Place these in your ComfyUI `models/` directories:
- `models/unet/flux1-schnell.safetensors`
- `models/clip/t5xxl_fp16.safetensors`
- `models/clip/clip_l.safetensors`
- `models/vae/ae.safetensors`

---

## Step 1: Start ComfyUI
```bash
cd ~/Documents/ComfyUI   # or wherever yours is installed
python main.py --force-fp16
```
Verify it's running: http://127.0.0.1:8188

## Step 2: Start Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
> **Note:** Run uvicorn from the project root (`Empire/`), not from inside `backend/`.
> The command is: `cd /path/to/Empire && uvicorn backend.main:app --reload`

Verify it's running: http://localhost:8000/health

## Step 3: Start Frontend
```bash
cd frontend
npm install
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
