"""
Post-processing pipeline:
  1. Download raw image from ComfyUI
  2. Upscale 4x via RealESRGAN (ComfyUI node)
  3. Face fix via FaceDetailer/CodeFormer (ComfyUI node)
  4. Invisible watermark
  5. Save to vault

When ComfyUI custom nodes aren't available, falls back to PIL-based processing.
"""

import io
import hashlib
import logging
import struct
import random
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

VAULT_DIR = Path.home() / "Documents" / "ComfyUI" / "output" / "Empire" / "vault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)


def _download_comfy_image(filename: str, subfolder: str = "Empire") -> Optional[bytes]:
    """Download a raw image from ComfyUI output."""
    import comfy_api
    try:
        resp = requests.get(
            f"{comfy_api.COMFY_BASE}/view",
            params={"filename": filename, "subfolder": subfolder, "type": "output"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.error("Failed to download image %s: %s", filename, e)
        return None


def _embed_watermark(image_bytes: bytes, marker: str = "EMPIRE") -> bytes:
    """
    Embed an invisible watermark by modifying LSBs of PNG image data.
    Uses a simple steganographic approach on the raw bytes.
    """
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        pixels = np.array(img)

        # Encode marker string into LSBs of blue channel
        marker_bytes = marker.encode("utf-8")
        # Prefix with length
        data = struct.pack(">H", len(marker_bytes)) + marker_bytes

        flat = pixels[:, :, 2].flatten()
        bits_needed = len(data) * 8

        if bits_needed <= len(flat):
            for i, bit_idx in enumerate(range(bits_needed)):
                byte_idx = bit_idx // 8
                bit_pos = 7 - (bit_idx % 8)
                bit_val = (data[byte_idx] >> bit_pos) & 1
                flat[i] = (flat[i] & 0xFE) | bit_val

            pixels[:, :, 2] = flat.reshape(pixels[:, :, 2].shape)

        result = Image.fromarray(pixels)
        buf = io.BytesIO()
        result.save(buf, format="PNG", optimize=False)
        return buf.getvalue()
    except ImportError:
        logger.warning("PIL/numpy not available, skipping watermark")
        return image_bytes


def _upscale_pil(image_bytes: bytes, scale: int = 2) -> bytes:
    """Simple PIL-based upscale fallback using LANCZOS."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        new_size = (img.width * scale, img.height * scale)
        upscaled = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        upscaled.save(buf, format="PNG", quality=95)
        return buf.getvalue()
    except Exception as e:
        logger.error("PIL upscale failed: %s", e)
        return image_bytes


def _upscale_comfyui(filename: str, subfolder: str = "Empire") -> Optional[dict]:
    """
    Queue an upscale + face fix workflow on ComfyUI.
    Uses RealESRGAN_x4plus + FaceDetailer if available.
    Returns comfy response or None.
    """
    import comfy_api

    workflow = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": f"{subfolder}/{filename}",
            },
        },
        "2": {
            "class_type": "UpscaleModelLoader",
            "inputs": {
                "model_name": "RealESRGAN_x4plus.pth",
            },
        },
        "3": {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": ["2", 0],
                "image": ["1", 0],
            },
        },
        "4": {
            "class_type": "ImageScaleBy",
            "inputs": {
                "image": ["3", 0],
                "upscale_method": "lanczos",
                "scale_by": 0.5,  # 4x then 0.5x = 2x net
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "Empire/upscaled",
                "images": ["4", 0],
            },
        },
    }

    try:
        resp = requests.post(
            f"{comfy_api.COMFY_BASE}/prompt",
            json={"prompt": workflow, "client_id": comfy_api.CLIENT_ID},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("ComfyUI upscale queue failed: %s", e)
        return None


def process_completed_image(content_id: int):
    """
    Full post-processing pipeline for a completed generation.
    Called automatically when a generation completes.
    """
    from database import SessionLocal, Content

    db = SessionLocal()
    try:
        content = db.query(Content).filter(Content.id == content_id).first()
        if not content or not content.file_path:
            return

        filename = content.file_path
        content.status = "upscaling"
        db.commit()

        # Try ComfyUI-based upscale first
        comfy_result = _upscale_comfyui(filename)
        if comfy_result and "prompt_id" in comfy_result:
            # Store the upscale job ID — we'll check completion later
            content.comfy_job_id = comfy_result["prompt_id"]
            content.status = "upscaling"
            db.commit()
            return

        # Fallback: download, PIL upscale, watermark, save to vault
        raw = _download_comfy_image(filename)
        if not raw:
            content.status = "completed"  # Revert — still usable
            db.commit()
            return

        # Upscale
        upscaled = _upscale_pil(raw, scale=2)

        # Watermark
        watermarked = _embed_watermark(upscaled, f"EMPIRE-{content.persona_id}-{content.id}")

        # Save to vault
        safe_name = f"vault_{content.id}_{filename}"
        vault_path = VAULT_DIR / safe_name
        vault_path.write_bytes(watermarked)

        content.upscaled_path = f"vault/{safe_name}"
        content.watermarked_path = f"vault/{safe_name}"
        content.status = "completed"
        db.commit()
        logger.info("Post-processed content %d -> %s", content.id, vault_path)
    except Exception as e:
        logger.error("Post-processing failed for content %d: %s", content_id, e)
        try:
            content.status = "completed"  # Don't lose the image
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def check_upscale_status(content_id: int) -> str:
    """Check if an upscale job is done and finalize."""
    from database import SessionLocal, Content
    import comfy_api

    db = SessionLocal()
    try:
        content = db.query(Content).filter(Content.id == content_id).first()
        if not content or content.status != "upscaling":
            return content.status if content else "unknown"

        if not content.comfy_job_id:
            return content.status

        job = comfy_api.get_job_status(content.comfy_job_id)

        if job["status"] == "completed" and job.get("outputs"):
            upscaled_filename = job["outputs"][0].get("filename")

            # Download upscaled, watermark, save to vault
            raw = _download_comfy_image(upscaled_filename, subfolder="Empire")
            if raw:
                watermarked = _embed_watermark(raw, f"EMPIRE-{content.persona_id}-{content.id}")
                safe_name = f"vault_{content.id}_{upscaled_filename}"
                vault_path = VAULT_DIR / safe_name
                vault_path.write_bytes(watermarked)
                content.upscaled_path = upscaled_filename
                content.watermarked_path = f"vault/{safe_name}"

            content.status = "completed"
            db.commit()
            return "completed"

        elif job["status"] == "error":
            content.status = "completed"  # Revert — raw image still good
            db.commit()
            return "completed"

        return "upscaling"
    finally:
        db.close()
