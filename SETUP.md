# AI Content Empire — Setup Guide

## Network & Machines

| Machine | Role | LAN IP | Tailscale IP |
|---------|------|--------|--------------|
| **Windows PC** | Backend + ComfyUI + GPU | `10.0.1.10` | `100.119.54.18` |
| **Mac** | Frontend (dev) | — | — |

### Ports

| Service | Port | Binding |
|---------|------|---------|
| ComfyUI | `8000` | `127.0.0.1` (local only) |
| Backend (FastAPI) | `8800` | `0.0.0.0` (LAN accessible) |
| Frontend (Next.js) | `3000` | `localhost` |

---

## Prerequisites
- **Windows PC**: Python 3.13, ComfyUI Desktop, NVIDIA GPU (RTX A4500 20GB)
- **Mac**: Node.js 18+
- **Optional**: Ollama for prompt refining, caption generation, and chat

## Required Models (already installed on Windows PC)

### Flux (image generation) — `ComfyUI/models/`
- `unet/flux1-schnell.safetensors`
- `clip/t5xxl_fp16.safetensors`
- `clip/clip_l.safetensors`
- `vae/ae.safetensors`

### Wan 2.1 (video generation) — `ComfyUI/models/`
- `diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors` (2.64 GB) — Text-to-Video
- `diffusion_models/wan2.1_i2v_480p_14B_fp8_scaled.safetensors` (15.27 GB) — Image-to-Video
- `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6.27 GB) — shared
- `vae/wan_2.1_vae.safetensors` (0.24 GB) — shared
- `clip_vision/clip_vision_h.safetensors` (1.18 GB) — for I2V

---

## Windows PC Setup (Backend + ComfyUI)

### Step 1: Start ComfyUI
Launch **ComfyUI Desktop** from Start Menu or desktop shortcut.
It listens on `http://127.0.0.1:8000`.

### Step 2: Start Backend
```powershell
cd C:\Users\Shadow\Desktop\Empire
& .\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8800 --reload
```
Verify: http://localhost:8800/health

### Step 3 (optional): Start Frontend locally on PC
```powershell
cd C:\Users\Shadow\Desktop\Empire\frontend
npm install
npm run dev
```
Open: http://localhost:3000

---

## Mac Setup (Frontend pointing to Windows PC)

### Clone & install
```bash
git clone https://github.com/Muki369-Blue/MLX-Studio-Wirks.git Empire
cd Empire/frontend
npm install
```

### Run (LAN — same network)
```bash
NEXT_PUBLIC_API_URL=http://10.0.1.10:8800 npm run dev
```

### Run (Tailscale — anywhere)
```bash
NEXT_PUBLIC_API_URL=http://100.119.54.18:8800 npm run dev
```

Open: http://localhost:3000

> All API calls (personas, generation, video, presets, etc.) go to the Windows PC.
> ComfyUI runs locally on the PC — the Mac never talks to ComfyUI directly.

---

## Environment Variables

### Backend (Windows PC)
| Variable | Default | Description |
|----------|---------|-------------|
| `COMFY_PORT` | `8000` | ComfyUI API port |
| `FRONTEND_ORIGINS` | `localhost:3000,3001` | Extra CORS origins (comma-separated) |
| `OLLAMA_MODEL` | (see code) | Ollama model name for refine/chat |

### Frontend (Mac or PC)
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8800` | Backend URL |
| `NEXT_PUBLIC_VIDEO_API_URL` | same as API | Video-specific backend URL (optional) |

---

## Architecture
```
Mac Browser → Next.js (:3000) → FastAPI on PC (:8800) → ComfyUI on PC (:8000) → outputs/
```

## API Endpoints
| Method | Endpoint                        | Description              |
|--------|---------------------------------|--------------------------|
| GET    | /health                         | API + ComfyUI status     |
| POST   | /personas/                      | Create persona           |
| GET    | /personas/                      | List all personas        |
| DELETE | /personas/{id}                  | Delete persona           |
| POST   | /generate/{persona_id}          | Trigger image generation |
| GET    | /generations/                   | List recent jobs         |
| GET    | /generations/{id}/status        | Check image job status   |
| POST   | /generate-video/{persona_id}    | Trigger video generation |
| GET    | /video-status/{content_id}      | Check video job status   |
| POST   | /upload-video-start-image       | Upload I2V start image   |
| GET    | /presets/videos                 | Video motion presets     |
| GET    | /presets/personas               | Persona presets          |
| GET    | /presets/scenes                 | Scene presets            |
| GET    | /presets/content-sets            | Content set presets      |
| GET    | /presets/negative-prompts        | Negative prompt presets  |
| GET    | /presets/voices                 | Voice presets            |
| POST   | /refine-video-prompt            | AI video prompt refine   |
| POST   | /refine-prompt                  | AI image prompt refine   |
| POST   | /links/                         | Add money link           |
| GET    | /links/                         | List all links           |
| DELETE | /links/{id}                     | Delete link              |

## Troubleshooting
- **Frontend can't connect from Mac**: Ensure backend is running on `0.0.0.0:8800` on the PC and `NEXT_PUBLIC_API_URL` is set to the PC's IP.
- **CORS errors**: Add your Mac's origin to `FRONTEND_ORIGINS` on the backend, e.g. `FRONTEND_ORIGINS=http://macbook.local:3000`.
- **Video generation stuck**: Check ComfyUI Desktop is running. First video takes longer (model loading into VRAM).
- **ComfyUI not detected**: Start ComfyUI Desktop manually, then restart the backend.
- **Prompt refine errors**: Ollama must be running locally on the PC (`ollama serve`).
