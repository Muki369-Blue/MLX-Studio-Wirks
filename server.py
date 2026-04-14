#!/usr/bin/env python3
"""
MLX Studio — Local LLM Server for Apple Silicon
v3: Flow improvements ported from AI-ArtWirks runtime.

Architecture patterns borrowed:
  - PerfTimer (utils.py) → timing all slow operations
  - _ensure_comfyui_headroom (engines.py) → memory-guarded generation
  - _prepare_for_engine (engines.py) → smart model cleanup on swap
  - SSE events (server.py) → push-based UI updates
  - _detect_model_profile (models.py) → richer model metadata detection
  - PromptMixin (prompt.py) → lightweight prompt enrichment
  - create_model_pull (models.py) → HF download from UI
"""

import asyncio
import gc
import hashlib
import json
import os
import sys
import time
import glob
import shutil
import subprocess
import platform
import re
import threading
import queue
import uuid
from html import unescape
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional, AsyncGenerator, Any
from urllib.parse import urlparse, parse_qs, quote, unquote, urljoin

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# PerfTimer — ported from AI-ArtWirks runtime/utils.py
# ---------------------------------------------------------------------------
class PerfTimer:
    """Context manager for timing operations with auto-logging."""
    __slots__ = ("label", "start", "elapsed_ms")

    def __init__(self, label: str) -> None:
        self.label = label
        self.start = 0.0
        self.elapsed_ms = 0.0

    def __enter__(self) -> "PerfTimer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
        print(f"⏱  {self.label}: {self.elapsed_ms:.0f}ms")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_DIRS = [
    "/Volumes/Wirks990/ai/models",
    "/Volumes/Wirks990/ai/models/huggingface",
    os.path.expanduser("~/.cache/huggingface/hub"),
]

HOST = "0.0.0.0"
PORT = 8899
APP_STATE_DIR = Path.home() / ".mlx_studio"
APP_STATE_FILE = APP_STATE_DIR / "app_state.json"
MAX_PAGE_CLIPS = 20
MAX_ATTACHMENT_EXCERPT_CHARS = 12000
MAX_ATTACHMENT_TEXT_BYTES = 1024 * 1024 * 2
MAX_FORM_ATTACHMENT_BYTES = 1024 * 1024 * 8
CONNECTOR_RESULT_LIMIT = 8
MAX_CONNECTOR_FETCH_CHARS = 40000
MAX_WORKSPACE_TREE_DEPTH = 4
MAX_WORKSPACE_TREE_ITEMS = 220
MAX_WORKSPACE_READ_BYTES = 1024 * 256
MAX_WORKSPACE_FIND_RESULTS = 40
MAX_WORKSPACE_WRITE_BYTES = 1024 * 1024 * 2
MAX_WORKSPACE_OPS = 128
GITHUB_API_BASE = "https://api.github.com"
HUGGINGFACE_API_BASE = "https://huggingface.co/api"
MAX_AGENT_TOOL_STEPS = 6
AGENT_TOOL_MAX_TOKENS = 6000
PLAYWRIGHT_SERVICE_HOST = os.environ.get("PLAYWRIGHT_SERVICE_HOST", "127.0.0.1")
PLAYWRIGHT_SERVICE_PORT = int(os.environ.get("PLAYWRIGHT_SERVICE_PORT", "8941"))
PLAYWRIGHT_START_TIMEOUT_SECONDS = 18.0
PLAYWRIGHT_REQUEST_TIMEOUT_SECONDS = 20.0
BROWSER_SNAPSHOT_TEXT_LIMIT = 7000
BROWSER_SNAPSHOT_ELEMENT_LIMIT = 24

# Memory safety thresholds (ported from AI-ArtWirks engines.py)
MEMORY_PRESSURE_WARN = 85      # Start warning at 85%
MEMORY_PRESSURE_BLOCK = 93     # Block generation at 93%
MIN_FREE_GB_FOR_GENERATION = 2 # Minimum free GB before blocking

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="MLX Studio", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_model = None
_tokenizer = None
_model_name: Optional[str] = None
_model_path: Optional[str] = None
_model_loading = False
_model_load_start: Optional[float] = None
_generation_stats = {
    "last_tps": 0,
    "last_latency": 0,
    "last_tokens": 0,
    "total_generated": 0,
}

# SSE event bus (ported from AI-ArtWirks server.py)
_event_queue: queue.Queue = queue.Queue(maxsize=256)

# HuggingFace pull state
_active_pulls: dict[str, dict] = {}
_cancelled_generations: set[str] = set()
_browser_service_process: Optional[subprocess.Popen] = None
_browser_service_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_project(
    project_id: str = "default",
    name: str = "Inbox",
    color: str = "#818cf8",
) -> dict:
    return {
        "id": project_id,
        "name": name,
        "color": color,
        "created": _utc_now(),
        "default_preset": "balanced",
        "system_prompt": (
            "You are a helpful, intelligent assistant. "
            "Be concise and accurate."
        ),
        "workspace_root": None,
        "workspace_label": None,
        "workspace_enabled": False,
        "workspace_pending_batch": None,
        "workflow_mode": "chat",
        "approval_mode": "manual",
        "deep_research": False,
    }


def _cancel_generation(generation_id: str) -> None:
    if generation_id:
        _cancelled_generations.add(generation_id)


def _is_generation_cancelled(generation_id: str) -> bool:
    return bool(generation_id) and generation_id in _cancelled_generations


def _clear_generation_cancel(generation_id: str) -> None:
    if generation_id:
        _cancelled_generations.discard(generation_id)


def _default_app_state() -> dict:
    return {
        "projects": [_default_project()],
        "sessions": [],
        "active_session_id": None,
        "active_project_id": "default",
        "selected_preset": "balanced",
        "system_prompt": (
            "You are a helpful, intelligent assistant. "
            "Be concise and accurate."
        ),
        "page_clips": [],
        "settings": {
            "transport_preference": "auto",
            "last_transport": "idle",
        },
        "updated_at": _utc_now(),
    }


def _deep_merge_dicts(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json_file(path: Path, default: Any) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _normalize_workspace_batch(batch: Any) -> Optional[dict]:
    if not isinstance(batch, dict):
        return None

    raw_ops = batch.get("operations")
    operations = raw_ops if isinstance(raw_ops, list) else []
    normalized_ops: list[dict] = []
    for item in operations[:MAX_WORKSPACE_OPS]:
        if not isinstance(item, dict):
            continue
        op_type = str(item.get("type") or "").strip()
        path = str(item.get("path") or "").strip()
        to_path = str(item.get("to_path") or "").strip()
        content = item.get("content")
        normalized_ops.append(
            {
                "type": op_type,
                "path": path,
                "to_path": to_path or None,
                "content": content if isinstance(content, str) else "",
                "expected_hash": str(item.get("expected_hash") or "").strip() or None,
            }
        )

    summary = batch.get("summary") if isinstance(batch.get("summary"), dict) else {}
    return {
        "id": str(batch.get("id") or "").strip() or uuid.uuid4().hex,
        "created_at": str(batch.get("created_at") or "").strip() or _utc_now(),
        "approval_required": True,
        "status": str(batch.get("status") or "pending").strip() or "pending",
        "operations": normalized_ops,
        "summary": summary,
    }


def _normalize_workflow_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"chat", "plan", "build"} else "chat"


def _normalize_approval_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"manual", "auto"} else "manual"


def _project_workflow_settings(project: Any) -> dict:
    raw = project if isinstance(project, dict) else {}
    return {
        "workflow_mode": _normalize_workflow_mode(raw.get("workflow_mode")),
        "approval_mode": _normalize_approval_mode(raw.get("approval_mode")),
        "deep_research": bool(raw.get("deep_research")),
    }


def _normalize_project(project: Any) -> dict:
    raw = project if isinstance(project, dict) else {}
    base = _default_project(
        project_id=str(raw.get("id") or f"project-{uuid.uuid4().hex[:8]}"),
        name=str(raw.get("name") or "Untitled"),
        color=str(raw.get("color") or "#818cf8"),
    )
    normalized = _deep_merge_dicts(base, raw)
    normalized["workspace_root"] = str(normalized.get("workspace_root") or "").strip() or None
    normalized["workspace_label"] = (
        str(normalized.get("workspace_label") or "").strip()
        or (Path(normalized["workspace_root"]).name if normalized["workspace_root"] else None)
    )
    normalized["workspace_enabled"] = bool(
        normalized.get("workspace_enabled") and normalized.get("workspace_root")
    )
    normalized["workspace_pending_batch"] = _normalize_workspace_batch(
        normalized.get("workspace_pending_batch")
    )
    workflow = _project_workflow_settings(normalized)
    normalized["workflow_mode"] = workflow["workflow_mode"]
    normalized["approval_mode"] = workflow["approval_mode"]
    normalized["deep_research"] = workflow["deep_research"]
    return normalized


def _normalize_app_state(raw: dict | None) -> dict:
    state = _deep_merge_dicts(_default_app_state(), raw or {})
    if not isinstance(state.get("projects"), list) or not state["projects"]:
        state["projects"] = _default_app_state()["projects"]
    state["projects"] = [_normalize_project(project) for project in state["projects"]]
    if not isinstance(state.get("sessions"), list):
        state["sessions"] = []
    if not isinstance(state.get("page_clips"), list):
        state["page_clips"] = []
    project_ids = {project["id"] for project in state["projects"]}
    if state.get("active_project_id") not in project_ids:
        state["active_project_id"] = state["projects"][0]["id"]
    state["page_clips"] = state["page_clips"][:MAX_PAGE_CLIPS]
    return state


def _load_app_state() -> dict:
    return _normalize_app_state(_read_json_file(APP_STATE_FILE, _default_app_state()))


def _save_app_state(state: dict) -> dict:
    normalized = _normalize_app_state(state)
    normalized["updated_at"] = _utc_now()
    _write_json_file(APP_STATE_FILE, normalized)
    return normalized


def _trim_text_excerpt(text: str, limit: int = MAX_ATTACHMENT_EXCERPT_CHARS) -> str:
    compact = re.sub(r"\s+\n", "\n", text or "")
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    compact = compact.strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    if b"\x00" in data[:1024]:
        return False
    try:
        data[:4096].decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            data[:4096].decode("latin-1")
            return True
        except Exception:
            return False


def _estimate_tokens(text: str, tokenizer: Any = None) -> int:
    if not text:
        return 0
    if tokenizer is not None:
        try:
            tokens = tokenizer.encode(text)
            return len(tokens)
        except Exception:
            pass
    return max(1, int(len(text) / 4))


def _capability_flags(meta: Optional[dict]) -> dict:
    modality = (meta or {}).get("modality", "text")
    engine_hint = (meta or {}).get("engine_hint", "mlx")
    chat = modality in {"text", "vision"} and engine_hint != "diffusers"
    return {
        "chat": chat,
        "attachments": chat,
        "text_files": chat,
        "folders": chat,
        "page_assist": chat,
        "compare": chat,
        "vision": modality == "vision",
        "diffusion": modality == "diffusion",
    }


def _loaded_model_meta() -> Optional[dict]:
    if not _model_path or not _model_name:
        return None
    model_path = Path(_model_path).expanduser()
    if not model_path.exists():
        return None
    return {
        "name": _model_name,
        "path": _model_path,
        **_detect_model_profile(model_path, _model_name),
    }


def _project_index(state: dict, project_id: str) -> int:
    for idx, project in enumerate(state.get("projects") or []):
        if project.get("id") == project_id:
            return idx
    raise RuntimeError(f"Unknown project: {project_id}")


def _project_record(project_id: str) -> tuple[dict, dict, int]:
    state = _load_app_state()
    idx = _project_index(state, project_id)
    return state["projects"][idx], state, idx


def _workspace_info(project: dict) -> dict:
    return {
        "enabled": bool(project.get("workspace_enabled") and project.get("workspace_root")),
        "root": project.get("workspace_root"),
        "label": project.get("workspace_label"),
        "pending_batch": project.get("workspace_pending_batch"),
    }


def _normalize_workspace_relative_path(value: str, *, allow_root: bool = True) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if not raw or raw == ".":
        if allow_root:
            return "."
        raise RuntimeError("A workspace-relative path is required.")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise RuntimeError("Workspace paths must be relative to the selected root.")
    parts = [part for part in path.parts if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise RuntimeError("Path traversal outside the workspace is not allowed.")
    if not parts:
        if allow_root:
            return "."
        raise RuntimeError("A workspace-relative path is required.")
    return "/".join(parts)


def _resolve_workspace_path(root: Path, relative_path: str, *, allow_missing: bool = False) -> Path:
    safe_path = _normalize_workspace_relative_path(relative_path)
    if safe_path == ".":
        candidate = root
    else:
        candidate = root.joinpath(*safe_path.split("/"))

    if allow_missing:
        if candidate.exists():
            resolved = candidate.resolve(strict=True)
        else:
            parent = candidate.parent.resolve(strict=True)
            resolved = parent / candidate.name
    else:
        resolved = candidate.resolve(strict=True)

    if not resolved.is_relative_to(root):
        raise RuntimeError("Resolved path escapes the selected workspace root.")
    return resolved


def _ensure_workspace_project(project_id: str) -> tuple[dict, Path, dict]:
    project, state, _ = _project_record(project_id)
    if not project.get("workspace_enabled") or not project.get("workspace_root"):
        raise RuntimeError("No workspace selected for this project.")

    root = Path(project["workspace_root"]).expanduser()
    if not root.exists() or not root.is_dir():
        raise RuntimeError("The selected workspace folder is unavailable.")
    root = root.resolve(strict=True)
    return project, root, state


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _workspace_path_stats(root: Path, path: Path) -> dict:
    rel = "." if path == root else path.relative_to(root).as_posix()
    stat = path.stat()
    kind = "directory" if path.is_dir() else "file"
    if path.is_symlink():
        kind = "symlink"
    return {
        "path": rel,
        "name": path.name or root.name,
        "kind": kind,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _workspace_tree(root: Path, relative_path: str = ".", depth: int = MAX_WORKSPACE_TREE_DEPTH) -> dict:
    target = _resolve_workspace_path(root, relative_path, allow_missing=False)
    if not target.is_dir():
        raise RuntimeError("Workspace tree can only list directories.")

    items: list[dict] = []
    max_depth = max(0, min(int(depth), MAX_WORKSPACE_TREE_DEPTH))

    def visit(directory: Path, current_depth: int) -> None:
        nonlocal items
        if len(items) >= MAX_WORKSPACE_TREE_ITEMS:
            return
        try:
            children = sorted(
                directory.iterdir(),
                key=lambda child: (not child.is_dir(), child.name.lower()),
            )
        except Exception:
            return
        for child in children:
            try:
                child_resolved = child.resolve(strict=True)
            except Exception:
                continue
            if not child_resolved.is_relative_to(root):
                continue
            info = _workspace_path_stats(root, child)
            info["depth"] = current_depth
            items.append(info)
            if len(items) >= MAX_WORKSPACE_TREE_ITEMS:
                return
            if child.is_dir() and not child.is_symlink() and current_depth < max_depth:
                visit(child, current_depth + 1)

    visit(target, 0)
    return {
        "path": "." if target == root else target.relative_to(root).as_posix(),
        "root": str(root),
        "items": items,
        "truncated": len(items) >= MAX_WORKSPACE_TREE_ITEMS,
    }


def _decode_workspace_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


def _read_workspace_file(root: Path, relative_path: str) -> dict:
    path = _resolve_workspace_path(root, relative_path, allow_missing=False)
    if path.is_dir():
        raise RuntimeError("Cannot read a directory. Use workspace tree for folders.")

    size_bytes = path.stat().st_size
    with open(path, "rb") as f:
        head = f.read(MAX_WORKSPACE_READ_BYTES + 1)
    if b"\x00" in head[:4096]:
        raise RuntimeError("Binary files are not supported in workspace read v1.")
    truncated = len(head) > MAX_WORKSPACE_READ_BYTES
    content = _decode_workspace_text(head[:MAX_WORKSPACE_READ_BYTES])
    return {
        **_workspace_path_stats(root, path),
        "content": content,
        "truncated": truncated,
        "sha256": _file_sha256(path),
    }


def _find_workspace_matches(root: Path, query: str, relative_path: str = ".") -> list[dict]:
    needle = str(query or "").strip()
    if not needle:
        raise RuntimeError("Search query is required.")

    target = _resolve_workspace_path(root, relative_path, allow_missing=False)
    results: list[dict] = []
    lowered = needle.lower()

    def add_result(item: dict) -> None:
        if len(results) < MAX_WORKSPACE_FIND_RESULTS:
            results.append(item)

    candidates = [target] if target.is_file() else list(target.rglob("*"))
    for path in candidates:
        if len(results) >= MAX_WORKSPACE_FIND_RESULTS:
            break
        try:
            resolved = path.resolve(strict=True)
        except Exception:
            continue
        if not resolved.is_relative_to(root):
            continue
        rel = "." if path == root else path.relative_to(root).as_posix()
        if lowered in rel.lower():
            add_result({"path": rel, "kind": "path", "preview": rel})
        if path.is_dir() or path.stat().st_size > MAX_WORKSPACE_READ_BYTES:
            continue
        try:
            data = path.read_bytes()
        except Exception:
            continue
        if not _is_probably_text(data):
            continue
        text = _decode_workspace_text(data[:MAX_WORKSPACE_READ_BYTES])
        for line_no, line in enumerate(text.splitlines(), start=1):
            if lowered in line.lower():
                add_result(
                    {
                        "path": rel,
                        "kind": "content",
                        "line": line_no,
                        "preview": line.strip()[:240],
                    }
                )
                if len(results) >= MAX_WORKSPACE_FIND_RESULTS:
                    break
    return results


def _sanitize_workspace_operations(raw_ops: Any) -> list[dict]:
    if not isinstance(raw_ops, list) or not raw_ops:
        raise RuntimeError("Workspace apply requires at least one operation.")
    if len(raw_ops) > MAX_WORKSPACE_OPS:
        raise RuntimeError(f"Workspace apply supports at most {MAX_WORKSPACE_OPS} operations per batch.")

    operations: list[dict] = []
    total_bytes = 0
    for idx, item in enumerate(raw_ops, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Operation {idx} must be an object.")
        op_type = str(item.get("type") or "").strip()
        path = _normalize_workspace_relative_path(item.get("path") or "", allow_root=False)
        expected_hash = str(item.get("expected_hash") or "").strip() or None
        if op_type == "write_file":
            content = item.get("content")
            if not isinstance(content, str):
                raise RuntimeError(f"Operation {idx} write_file requires string content.")
            if "\x00" in content:
                raise RuntimeError("Binary file writes are not supported in workspace apply v1.")
            total_bytes += len(content.encode("utf-8"))
            operations.append(
                {
                    "type": op_type,
                    "path": path,
                    "content": content,
                    "expected_hash": expected_hash,
                }
            )
        elif op_type == "mkdir":
            operations.append({"type": op_type, "path": path})
        elif op_type == "rename":
            to_path = _normalize_workspace_relative_path(item.get("to_path") or "", allow_root=False)
            operations.append(
                {
                    "type": op_type,
                    "path": path,
                    "to_path": to_path,
                    "expected_hash": expected_hash,
                }
            )
        elif op_type == "delete":
            operations.append({"type": op_type, "path": path, "expected_hash": expected_hash})
        else:
            raise RuntimeError(f"Unsupported workspace operation: {op_type or '<missing>'}")

    if total_bytes > MAX_WORKSPACE_WRITE_BYTES:
        raise RuntimeError("Workspace apply batch is too large for v1.")
    return operations


def _workspace_batch_summary(root: Path, operations: list[dict]) -> dict:
    counts = {
        "write_file": 0,
        "mkdir": 0,
        "rename": 0,
        "delete": 0,
    }
    preview: list[dict] = []
    for item in operations:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
        entry = {
            "type": item["type"],
            "path": item["path"],
        }
        if item["type"] == "rename":
            entry["to_path"] = item.get("to_path")
        if item["type"] == "write_file":
            target = root.joinpath(*item["path"].split("/"))
            entry["mode"] = "overwrite" if target.exists() else "create"
            entry["bytes"] = len(item.get("content", "").encode("utf-8"))
        preview.append(entry)
    return {
        "counts": counts,
        "total_operations": len(operations),
        "preview": preview[:40],
    }


def _stage_workspace_batch(project_id: str, operations: list[dict]) -> tuple[dict, dict]:
    project, root, state = _ensure_workspace_project(project_id)
    summary = _workspace_batch_summary(root, operations)
    batch = {
        "id": uuid.uuid4().hex,
        "created_at": _utc_now(),
        "approval_required": True,
        "status": "pending",
        "operations": operations,
        "summary": summary,
    }
    idx = _project_index(state, project_id)
    state["projects"][idx]["workspace_pending_batch"] = batch
    saved = _save_app_state(state)
    project = saved["projects"][idx]
    _push_event("workspace_batch_staged", {"project_id": project_id, "batch_id": batch["id"]})
    return project, batch


def _stage_or_apply_workspace_batch(
    project_id: str,
    operations: list[dict],
    *,
    auto_apply: bool = False,
) -> tuple[dict, dict, bool]:
    project, batch = _stage_workspace_batch(project_id, operations)
    if not auto_apply:
        return project, batch, False
    project, applied_batch = _apply_workspace_batch(project_id, batch.get("id") or "")
    return project, applied_batch, True


def _apply_workspace_batch(project_id: str, pending_id: str) -> tuple[dict, dict]:
    project, root, state = _ensure_workspace_project(project_id)
    batch = project.get("workspace_pending_batch")
    if not batch:
        raise RuntimeError("No pending workspace batch to apply.")
    if pending_id and batch.get("id") != pending_id:
        raise RuntimeError("Pending workspace batch does not match the requested id.")

    operations = _sanitize_workspace_operations(batch.get("operations") or [])
    for item in operations:
        op_type = item["type"]
        target = _resolve_workspace_path(root, item["path"], allow_missing=(op_type in {"write_file", "mkdir", "rename"}))
        if target == root:
            raise RuntimeError("Workspace root itself cannot be mutated.")
        if op_type == "mkdir":
            if target.exists() and not target.is_dir():
                raise RuntimeError(f"Cannot create directory over existing file: {item['path']}")
            target.mkdir(parents=True, exist_ok=True)
        elif op_type == "write_file":
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.is_dir():
                raise RuntimeError(f"Cannot overwrite directory with file content: {item['path']}")
            if target.exists() and item.get("expected_hash"):
                if _file_sha256(target) != item["expected_hash"]:
                    raise RuntimeError(f"Conflict detected while writing {item['path']}.")
            elif target.exists() and not item.get("expected_hash"):
                raise RuntimeError(f"Writing existing file requires expected_hash: {item['path']}")
            target.write_text(item["content"], encoding="utf-8")
        elif op_type == "rename":
            destination = _resolve_workspace_path(root, item.get("to_path") or "", allow_missing=True)
            if not target.exists():
                raise RuntimeError(f"Cannot rename missing path: {item['path']}")
            if destination.exists():
                raise RuntimeError(f"Cannot rename onto existing path: {item['to_path']}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            target.rename(destination)
        elif op_type == "delete":
            if not target.exists():
                raise RuntimeError(f"Cannot delete missing path: {item['path']}")
            if target.is_file() and item.get("expected_hash"):
                if _file_sha256(target) != item["expected_hash"]:
                    raise RuntimeError(f"Conflict detected while deleting {item['path']}.")
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

    idx = _project_index(state, project_id)
    state["projects"][idx]["workspace_pending_batch"] = None
    saved = _save_app_state(state)
    project = saved["projects"][idx]
    _push_event("workspace_batch_applied", {"project_id": project_id, "batch_id": batch.get("id")})
    return project, batch


def _discard_workspace_batch(project_id: str, pending_id: str = "") -> dict:
    project, _, state = _ensure_workspace_project(project_id)
    batch = project.get("workspace_pending_batch")
    if batch and pending_id and batch.get("id") != pending_id:
        raise RuntimeError("Pending workspace batch does not match the requested id.")
    idx = _project_index(state, project_id)
    state["projects"][idx]["workspace_pending_batch"] = None
    saved = _save_app_state(state)
    _push_event("workspace_batch_discarded", {"project_id": project_id, "batch_id": batch.get("id") if batch else ""})
    return saved["projects"][idx]


def _choose_workspace_folder() -> str:
    if platform.system() != "Darwin":
        raise RuntimeError("Interactive workspace selection is only supported on macOS in v1. Provide a path explicitly.")
    script = 'POSIX path of (choose folder with prompt "Select a workspace folder for MLX Studio")'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        if "User canceled" in stderr:
            raise RuntimeError("Workspace selection was cancelled.")
        raise RuntimeError(stderr or "Workspace selection failed.")
    selected = (result.stdout or "").strip()
    if not selected:
        raise RuntimeError("No workspace folder was selected.")
    return selected


def _set_project_workspace(project_id: str, path: Optional[str], suggested_label: str = "") -> dict:
    state = _load_app_state()
    idx = _project_index(state, project_id)
    if path:
        root = Path(path).expanduser().resolve(strict=True)
    else:
        root = Path(_choose_workspace_folder()).expanduser().resolve(strict=True)
    if not root.exists() or not root.is_dir():
        raise RuntimeError("Workspace path must point to an existing directory.")
    project = state["projects"][idx]
    project["workspace_root"] = str(root)
    project["workspace_label"] = suggested_label.strip() or root.name
    project["workspace_enabled"] = True
    project["workspace_pending_batch"] = None
    state["projects"][idx] = project
    saved = _save_app_state(state)
    _push_event("workspace_selected", {"project_id": project_id, "workspace_root": str(root)})
    return saved["projects"][idx]


def _clear_project_workspace(project_id: str) -> dict:
    state = _load_app_state()
    idx = _project_index(state, project_id)
    project = state["projects"][idx]
    project["workspace_root"] = None
    project["workspace_label"] = None
    project["workspace_enabled"] = False
    project["workspace_pending_batch"] = None
    state["projects"][idx] = project
    saved = _save_app_state(state)
    _push_event("workspace_cleared", {"project_id": project_id})
    return saved["projects"][idx]


def _extract_pdf_text(data: bytes) -> str:
    try:
        from io import BytesIO
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        pages: list[str] = []
        for page in reader.pages[:20]:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages)
    except Exception:
        return ""


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._capture_title = False
        self._title_parts: list[str] = []
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = (tag or "").lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = True
        if tag in {"p", "div", "section", "article", "main", "header", "footer", "aside", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = (tag or "").lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._capture_title = False
        if not self._skip_depth and tag in {"p", "div", "section", "article", "main", "header", "footer", "aside", "li", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data or "").strip()
        if not text:
            return
        if self._capture_title:
            self._title_parts.append(text)
        self._chunks.append(text)

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", unescape(" ".join(self._title_parts))).strip()

    @property
    def text(self) -> str:
        joined = "\n".join(self._chunks)
        joined = unescape(joined)
        joined = re.sub(r"[ \t]+\n", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


def _extract_html_text(data: bytes) -> tuple[str, str]:
    try:
        html = data[:MAX_ATTACHMENT_TEXT_BYTES].decode("utf-8", errors="ignore")
        parser = _HTMLTextExtractor()
        parser.feed(html)
        parser.close()
        return parser.title, parser.text
    except Exception:
        return "", ""


def _extract_attachment_record(
    filename: str,
    content_type: str,
    data: bytes,
    relative_path: str = "",
) -> dict:
    suffix = Path(filename).suffix.lower()
    kind = "binary"
    extracted_text = ""

    if content_type.startswith("image/"):
        kind = "image"
    elif suffix in {".html", ".htm"} or "html" in content_type:
        kind = "text"
        _, extracted_text = _extract_html_text(data)
    elif suffix == ".pdf" or content_type == "application/pdf":
        kind = "pdf"
        extracted_text = _extract_pdf_text(data)
    elif content_type.startswith("text/") or suffix in {
        ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
        ".html", ".css", ".scss", ".yaml", ".yml", ".toml", ".ini",
        ".sql", ".sh", ".zsh", ".csv", ".xml", ".java", ".rb",
        ".go", ".rs", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp",
    } or _is_probably_text(data):
        kind = "text"
        limited = data[:MAX_ATTACHMENT_TEXT_BYTES]
        try:
            extracted_text = limited.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = limited.decode("latin-1", errors="ignore")

    excerpt = _trim_text_excerpt(extracted_text)
    return {
        "id": uuid.uuid4().hex,
        "name": Path(filename).name,
        "relative_path": relative_path or Path(filename).name,
        "content_type": content_type or "application/octet-stream",
        "kind": kind,
        "size_bytes": len(data),
        "text_excerpt": excerpt,
        "char_count": len(extracted_text),
        "token_estimate": _estimate_tokens(excerpt),
        "summary": (
            excerpt[:240]
            if excerpt
            else f"{kind.title()} attachment: {Path(filename).name}"
        ),
    }


def _connector_catalog() -> list[dict]:
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    return [
        {
            "id": "web",
            "label": "Web",
            "description": "Search the web and add fetched page text into grounded context.",
            "configured": True,
            "requires_auth_for_private": False,
            "search_placeholder": "Search the web or paste a URL",
            "auth_hint": "Uses public search results and direct page fetches.",
        },
        {
            "id": "github",
            "label": "GitHub",
            "description": "Search repositories, issues, and pull requests and add them to grounded context.",
            "configured": bool(github_token),
            "requires_auth_for_private": True,
            "search_placeholder": "Search GitHub repos, issues, PRs, or paste a GitHub URL",
            "auth_hint": (
                "Public GitHub works without a token. Set GITHUB_TOKEN for higher rate limits "
                "and private repositories."
            ),
        },
        {
            "id": "huggingface",
            "label": "Hugging Face",
            "description": "Search public model cards and bring README context into the prompt.",
            "configured": True,
            "requires_auth_for_private": False,
            "search_placeholder": "Search public model repos or paste a Hugging Face model URL",
            "auth_hint": "Public model cards work without authentication.",
        },
    ]


def _github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "MLX-Studio/3.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def _huggingface_headers() -> dict[str, str]:
    return {
        "User-Agent": "MLX-Studio/3.0",
    }


async def _github_get(
    path: str,
    *,
    params: Optional[dict] = None,
    accept: str = "application/vnd.github+json",
    tolerate_404: bool = False,
) -> Optional[httpx.Response]:
    url = path if path.startswith("http") else f"{GITHUB_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        response = await client.get(url, headers=_github_headers(accept), params=params)
    if tolerate_404 and response.status_code == 404:
        return None
    if response.status_code >= 400:
        message = None
        try:
            payload = response.json()
            message = payload.get("message")
        except Exception:
            message = response.text[:240]
        raise RuntimeError(message or f"GitHub API error ({response.status_code})")
    return response


async def _huggingface_get(path: str, *, params: Optional[dict] = None, tolerate_404: bool = False) -> Optional[httpx.Response]:
    url = path if path.startswith("http") else f"{HUGGINGFACE_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        response = await client.get(url, headers=_huggingface_headers(), params=params)
    if tolerate_404 and response.status_code == 404:
        return None
    if response.status_code >= 400:
        message = None
        try:
            payload = response.json()
            message = payload.get("error") or payload.get("message")
        except Exception:
            message = response.text[:240]
        raise RuntimeError(message or f"Hugging Face API error ({response.status_code})")
    return response


def _connector_preview_from_url(query: str) -> Optional[dict]:
    parsed = urlparse((query or "").strip())
    if parsed.netloc not in {"github.com", "www.github.com"}:
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        return None

    repo = f"{segments[0]}/{segments[1]}"
    url = f"https://github.com/{repo}"
    if len(segments) == 2:
        return {
            "id": f"repo:{repo}",
            "provider": "github",
            "kind": "repo",
            "title": repo,
            "subtitle": "Repository",
            "description": "Fetch repository overview and README into context.",
            "url": url,
        }

    if len(segments) >= 4 and segments[2] in {"issues", "pull"} and segments[3].isdigit():
        is_pull = segments[2] == "pull"
        item_kind = "pull_request" if is_pull else "issue"
        item_id = f"{'pr' if is_pull else 'issue'}:{repo}#{segments[3]}"
        return {
            "id": item_id,
            "provider": "github",
            "kind": item_kind,
            "title": f"{repo} #{segments[3]}",
            "subtitle": "Pull request" if is_pull else "Issue",
            "description": "Fetch the thread body and recent comments into context.",
            "url": f"{url}/{segments[2]}/{segments[3]}",
        }

    return None


def _connector_preview_from_query(query: str) -> Optional[dict]:
    direct_url = _connector_preview_from_url(query)
    if direct_url:
        return direct_url

    stripped = (query or "").strip()
    repo_match = re.fullmatch(r"(?:repo:)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", stripped)
    if repo_match:
        repo = repo_match.group(1)
        return {
            "id": f"repo:{repo}",
            "provider": "github",
            "kind": "repo",
            "title": repo,
            "subtitle": "Repository",
            "description": "Fetch repository overview and README into context.",
            "url": f"https://github.com/{repo}",
        }

    return None


def _huggingface_preview_from_query(query: str) -> Optional[dict]:
    stripped = (query or "").strip()
    parsed = urlparse(stripped)

    if parsed.netloc in {"huggingface.co", "www.huggingface.co"}:
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) >= 2 and segments[0] not in {"datasets", "spaces"}:
            model_id = f"{segments[0]}/{segments[1]}"
            return {
                "id": f"model:{model_id}",
                "provider": "huggingface",
                "kind": "model",
                "title": model_id,
                "subtitle": "Model repository",
                "description": "Fetch the model card and metadata into context.",
                "url": f"https://huggingface.co/{model_id}",
            }

    repo_match = re.fullmatch(r"(?:model:)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", stripped)
    if repo_match:
        model_id = repo_match.group(1)
        return {
            "id": f"model:{model_id}",
            "provider": "huggingface",
            "kind": "model",
            "title": model_id,
            "subtitle": "Model repository",
            "description": "Fetch the model card and metadata into context.",
            "url": f"https://huggingface.co/{model_id}",
        }

    return None


def _web_result(url: str, title: str, snippet: str = "") -> dict:
    parsed = urlparse(url)
    host = parsed.netloc or "web"
    return {
        "id": f"web:{quote(url, safe='')}",
        "provider": "web",
        "kind": "web_page",
        "title": title or host,
        "subtitle": host,
        "description": _trim_text_excerpt(snippet or "", limit=220),
        "url": url,
    }


def _web_preview_from_query(query: str) -> Optional[dict]:
    parsed = urlparse((query or "").strip())
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return _web_result(parsed.geturl(), parsed.netloc, "Fetch this page into context.")
    return None


def _decode_duckduckgo_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    parsed = urlparse(candidate)
    if "duckduckgo.com" in (parsed.netloc or "") and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return candidate


def _strip_html_fragment(value: str) -> str:
    fragment = re.sub(r"<[^>]+>", " ", value or "")
    fragment = unescape(fragment)
    fragment = re.sub(r"\s+", " ", fragment)
    return fragment.strip()


def _safe_web_relative_path(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "web").replace(":", "_")
    path = parsed.path.strip("/") or "index"
    sanitized = re.sub(r"[^A-Za-z0-9._/-]+", "-", path).strip("-")
    if not sanitized:
        sanitized = "index"
    if not sanitized.endswith(".md"):
        sanitized = f"{sanitized}.md"
    return f"web/{host}/{sanitized}"


def _github_repo_result(item: dict) -> dict:
    language = item.get("language") or "mixed"
    stars = item.get("stargazers_count") or 0
    return {
        "id": f"repo:{item.get('full_name', '')}",
        "provider": "github",
        "kind": "repo",
        "title": item.get("full_name") or "GitHub repository",
        "subtitle": f"Repository · ★ {stars} · {language}",
        "description": _trim_text_excerpt(item.get("description") or "", limit=220),
        "url": item.get("html_url") or "",
    }


def _github_issue_result(item: dict) -> dict:
    repository_url = item.get("repository_url") or ""
    repo_name = "/".join(repository_url.rstrip("/").split("/")[-2:]) or "repo"
    is_pull = bool(item.get("pull_request"))
    kind = "pull_request" if is_pull else "issue"
    prefix = "pr" if is_pull else "issue"
    return {
        "id": f"{prefix}:{repo_name}#{item.get('number')}",
        "provider": "github",
        "kind": kind,
        "title": item.get("title") or f"{'PR' if is_pull else 'Issue'} #{item.get('number')}",
        "subtitle": (
            f"{'Pull request' if is_pull else 'Issue'} · {repo_name} #{item.get('number')} · "
            f"{item.get('state') or 'open'}"
        ),
        "description": _trim_text_excerpt(item.get("body") or "", limit=220),
        "url": item.get("html_url") or "",
    }


async def _github_search(query: str) -> list[dict]:
    direct_result = _connector_preview_from_query(query)
    if direct_result:
        return [direct_result]

    repo_call = _github_get(
        "/search/repositories",
        params={"q": query, "per_page": 4, "sort": "stars", "order": "desc"},
    )
    issue_call = _github_get(
        "/search/issues",
        params={"q": query, "per_page": 4, "sort": "updated", "order": "desc"},
    )
    repo_response, issue_response = await asyncio.gather(
        repo_call,
        issue_call,
        return_exceptions=True,
    )

    results: list[dict] = []
    errors: list[str] = []

    if isinstance(repo_response, Exception):
        errors.append(str(repo_response))
    else:
        repo_items = repo_response.json().get("items", [])
        results.extend(_github_repo_result(item) for item in repo_items)

    if isinstance(issue_response, Exception):
        errors.append(str(issue_response))
    else:
        issue_items = issue_response.json().get("items", [])
        results.extend(_github_issue_result(item) for item in issue_items)

    if not results and errors:
        raise RuntimeError(errors[0])

    return results[:CONNECTOR_RESULT_LIMIT]


def _huggingface_model_result(item: dict) -> dict:
    model_id = item.get("id") or item.get("modelId") or "unknown/model"
    pipeline_tag = item.get("pipeline_tag") or item.get("library_name") or "model"
    downloads = item.get("downloads") or 0
    tags = item.get("tags") or []
    short_tags = ", ".join(tag for tag in tags[:4] if isinstance(tag, str))
    return {
        "id": f"model:{model_id}",
        "provider": "huggingface",
        "kind": "model",
        "title": model_id,
        "subtitle": f"{pipeline_tag} · {downloads:,} downloads",
        "description": short_tags or "Public model repository",
        "url": f"https://huggingface.co/{model_id}",
    }


async def _huggingface_search(query: str) -> list[dict]:
    direct_result = _huggingface_preview_from_query(query)
    if direct_result:
        return [direct_result]

    response = await _huggingface_get(
        "/models",
        params={"search": query, "limit": CONNECTOR_RESULT_LIMIT},
    )
    items = response.json() or []
    return [_huggingface_model_result(item) for item in items[:CONNECTOR_RESULT_LIMIT]]


async def _web_search(query: str) -> list[dict]:
    direct_result = _web_preview_from_query(query)
    if direct_result:
        return [direct_result]

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        response = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "MLX-Studio/3.0"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Web search failed ({response.status_code})")

    pattern = re.compile(
        r'<a rel="nofollow" class="result__a" href="(?P<href>[^"]+)">(?P<title>.*?)</a>'
        r'.*?(?:<a class="result__snippet" href="[^"]+">|<div class="result__snippet">)(?P<snippet>.*?)</(?:a|div)>'
        r'.*?<a class="result__url" href="[^"]+">(?P<link>.*?)</a>',
        re.S,
    )

    results: list[dict] = []
    for match in pattern.finditer(response.text):
        href = _decode_duckduckgo_url(match.group("href"))
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        title = _strip_html_fragment(match.group("title"))
        snippet = _strip_html_fragment(match.group("snippet") or "")
        result = _web_result(href, title, snippet)
        link_text = _strip_html_fragment(match.group("link"))
        if link_text:
            result["subtitle"] = link_text
        results.append(result)
        if len(results) >= CONNECTOR_RESULT_LIMIT:
            break

    return results


def _compose_markdown_block(lines: list[str]) -> str:
    return "\n".join(lines).strip()[:MAX_CONNECTOR_FETCH_CHARS]


async def _github_fetch(item_id: str) -> dict:
    repo_match = re.fullmatch(r"repo:([^#]+/[^#]+)", item_id)
    thread_match = re.fullmatch(r"(issue|pr):([^#]+/[^#]+)#(\d+)", item_id)

    if repo_match:
        repo = repo_match.group(1)
        repo_response = await _github_get(f"/repos/{repo}")
        repo_json = repo_response.json()
        readme_response = await _github_get(
            f"/repos/{repo}/readme",
            accept="application/vnd.github.raw",
            tolerate_404=True,
        )
        readme_text = (readme_response.text or "").strip() if readme_response is not None else ""
        topics = repo_json.get("topics") or []
        lines = [
            f"# {repo_json.get('full_name') or repo}",
            "",
            repo_json.get("description") or "No repository description provided.",
            "",
            f"- URL: {repo_json.get('html_url') or ''}",
            f"- Default branch: {repo_json.get('default_branch') or 'unknown'}",
            f"- Primary language: {repo_json.get('language') or 'unknown'}",
            f"- Stars: {repo_json.get('stargazers_count') or 0}",
            f"- Open issues: {repo_json.get('open_issues_count') or 0}",
        ]
        if topics:
            lines.append(f"- Topics: {', '.join(topics[:12])}")
        if readme_text:
            lines.extend(["", "## README", "", readme_text[:MAX_CONNECTOR_FETCH_CHARS]])
        else:
            lines.extend(["", "_README not available via the GitHub API._"])

        payload = _compose_markdown_block(lines)
        attachment = _extract_attachment_record(
            filename="README.md",
            content_type="text/markdown",
            data=payload.encode("utf-8"),
            relative_path=f"github/{repo}/README.md",
        )
        attachment.update(
            {
                "provider": "github",
                "connector_kind": "repo",
                "source_url": repo_json.get("html_url") or "",
            }
        )
        return {"attachment": attachment}

    if thread_match:
        kind, repo, number = thread_match.groups()
        issue_response = await _github_get(f"/repos/{repo}/issues/{number}")
        issue_json = issue_response.json()
        comments_response = await _github_get(
            f"/repos/{repo}/issues/{number}/comments",
            params={"per_page": 5},
            tolerate_404=True,
        )
        comments = comments_response.json() if comments_response is not None else []
        labels = [label.get("name") for label in issue_json.get("labels", []) if label.get("name")]
        is_pull = kind == "pr" or bool(issue_json.get("pull_request"))
        kind_label = "Pull Request" if is_pull else "Issue"
        subdir = "pulls" if is_pull else "issues"

        lines = [
            f"# {kind_label}: {issue_json.get('title') or f'#{number}'}",
            "",
            f"- Repository: {repo}",
            f"- Number: {number}",
            f"- State: {issue_json.get('state') or 'open'}",
            f"- URL: {issue_json.get('html_url') or ''}",
        ]
        if labels:
            lines.append(f"- Labels: {', '.join(labels[:12])}")

        body = (issue_json.get("body") or "").strip()
        if body:
            lines.extend(["", "## Body", "", body[:MAX_CONNECTOR_FETCH_CHARS]])

        if comments:
            lines.extend(["", "## Recent Comments"])
            for comment in comments[:5]:
                author = ((comment.get("user") or {}).get("login")) or "unknown"
                comment_body = _trim_text_excerpt(comment.get("body") or "", limit=1800)
                if not comment_body:
                    continue
                lines.extend(["", f"### @{author}", "", comment_body])

        payload = _compose_markdown_block(lines)
        attachment = _extract_attachment_record(
            filename=f"{subdir}-{number}.md",
            content_type="text/markdown",
            data=payload.encode("utf-8"),
            relative_path=f"github/{repo}/{subdir}/{number}.md",
        )
        attachment.update(
            {
                "provider": "github",
                "connector_kind": "pull_request" if is_pull else "issue",
                "source_url": issue_json.get("html_url") or "",
            }
        )
        return {"attachment": attachment}

    raise RuntimeError(f"Unsupported GitHub item id: {item_id}")


async def _huggingface_fetch(item_id: str) -> dict:
    model_match = re.fullmatch(r"model:([^#]+/[^#]+)", item_id)
    if not model_match:
        raise RuntimeError(f"Unsupported Hugging Face item id: {item_id}")

    model_id = model_match.group(1)
    meta_response = await _huggingface_get(f"/models/{model_id}")
    meta_json = meta_response.json()

    readme_url = f"https://huggingface.co/{model_id}/raw/main/README.md"
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        readme_response = await client.get(readme_url, headers=_huggingface_headers())
    readme_text = readme_response.text.strip() if readme_response.status_code == 200 else ""

    tags = [tag for tag in (meta_json.get("tags") or []) if isinstance(tag, str)]
    lines = [
        f"# {meta_json.get('id') or model_id}",
        "",
        f"- URL: https://huggingface.co/{model_id}",
        f"- Pipeline: {meta_json.get('pipeline_tag') or 'unknown'}",
        f"- Library: {meta_json.get('library_name') or 'unknown'}",
        f"- Downloads: {meta_json.get('downloads') or 0}",
        f"- Likes: {meta_json.get('likes') or 0}",
        f"- Private: {bool(meta_json.get('private'))}",
    ]
    if tags:
        lines.append(f"- Tags: {', '.join(tags[:16])}")
    if readme_text:
        lines.extend(["", "## README", "", readme_text[:MAX_CONNECTOR_FETCH_CHARS]])
    else:
        lines.extend(["", "_README not available for this model card._"])

    payload = _compose_markdown_block(lines)
    attachment = _extract_attachment_record(
        filename="README.md",
        content_type="text/markdown",
        data=payload.encode("utf-8"),
        relative_path=f"huggingface/{model_id}/README.md",
    )
    attachment.update(
        {
            "provider": "huggingface",
            "connector_kind": "model",
            "source_url": f"https://huggingface.co/{model_id}",
        }
    )
    return {"attachment": attachment}


async def _web_fetch(item_id: str) -> dict:
    match = re.fullmatch(r"web:(.+)", item_id)
    if not match:
        raise RuntimeError(f"Unsupported web item id: {item_id}")

    url = unquote(match.group(1))
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Web fetch requires a valid http or https URL.")

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "MLX-Studio/3.0"})
    if response.status_code >= 400:
        raise RuntimeError(f"Web fetch failed ({response.status_code})")

    final_url = str(response.url)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    data = response.content
    filename = Path(urlparse(final_url).path or "").name or "page"

    if "html" in content_type or final_url.endswith((".html", ".htm")) or not Path(filename).suffix:
        title, text = _extract_html_text(data)
        lines = [
            f"# {title or final_url}",
            "",
            f"- URL: {final_url}",
            f"- Content-Type: {content_type or 'text/html'}",
        ]
        if text:
            lines.extend(["", text[:MAX_CONNECTOR_FETCH_CHARS]])
        else:
            lines.extend(["", "_No readable page text was extracted from this URL._"])
        payload = _compose_markdown_block(lines)
        attachment = _extract_attachment_record(
            filename=(f"{(title or 'page').strip()[:80]}.md").replace("/", "-"),
            content_type="text/markdown",
            data=payload.encode("utf-8"),
            relative_path=_safe_web_relative_path(final_url),
        )
    else:
        attachment = _extract_attachment_record(
            filename=filename,
            content_type=content_type or "application/octet-stream",
            data=data,
            relative_path=_safe_web_relative_path(final_url),
        )

    attachment.update(
        {
            "provider": "web",
            "connector_kind": "web_page",
            "source_url": final_url,
        }
    )
    return {"attachment": attachment}


async def _search_connector(provider: str, query: str) -> list[dict]:
    if provider == "web":
        return await _web_search(query)
    if provider == "github":
        return await _github_search(query)
    if provider == "huggingface":
        return await _huggingface_search(query)
    raise RuntimeError(f"Unknown connector: {provider}")


async def _fetch_connector(provider: str, item_id: str) -> dict:
    if provider == "web":
        return await _web_fetch(item_id)
    if provider == "github":
        return await _github_fetch(item_id)
    if provider == "huggingface":
        return await _huggingface_fetch(item_id)
    raise RuntimeError(f"Unknown connector: {provider}")


def _browser_service_base_url(path: str = "") -> str:
    return f"http://{PLAYWRIGHT_SERVICE_HOST}:{PLAYWRIGHT_SERVICE_PORT}{path}"


async def _browser_service_healthcheck() -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(_browser_service_base_url("/health"))
        if response.status_code >= 400:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


async def _ensure_browser_service() -> dict:
    global _browser_service_process

    healthy = await _browser_service_healthcheck()
    if healthy is not None:
        return healthy

    script_path = Path(__file__).parent / "scripts" / "playwright_service.mjs"
    if not script_path.exists():
        raise RuntimeError("Playwright service script is missing from scripts/playwright_service.mjs.")

    with _browser_service_lock:
        process = _browser_service_process
        if process is None or process.poll() is not None:
            env = os.environ.copy()
            env.setdefault("PLAYWRIGHT_SERVICE_HOST", PLAYWRIGHT_SERVICE_HOST)
            env.setdefault("PLAYWRIGHT_SERVICE_PORT", str(PLAYWRIGHT_SERVICE_PORT))
            _browser_service_process = subprocess.Popen(
                ["node", str(script_path)],
                cwd=str(Path(__file__).parent),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

    deadline = time.time() + PLAYWRIGHT_START_TIMEOUT_SECONDS
    while time.time() < deadline:
        healthy = await _browser_service_healthcheck()
        if healthy is not None:
            return healthy

        process = _browser_service_process
        if process is not None and process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            details = (stderr or stdout or "").strip()
            if "Cannot find package 'playwright'" in details or "ERR_MODULE_NOT_FOUND" in details:
                details = (
                    "Playwright service could not start because the repo Node dependency is missing. "
                    "Run `npm install` in the repo root."
                )
            raise RuntimeError(details or "Playwright service exited before becoming healthy.")
        await asyncio.sleep(0.25)

    raise RuntimeError(
        "Timed out waiting for the Playwright service. Run `npm install` and `npm run browser:install`."
    )


async def _browser_service_request(
    method: str,
    path: str,
    payload: Optional[dict] = None,
    *,
    timeout: float = PLAYWRIGHT_REQUEST_TIMEOUT_SECONDS,
) -> dict:
    await _ensure_browser_service()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, _browser_service_base_url(path), json=payload)
    try:
        body = response.json()
    except Exception:
        body = {"error": response.text[:400]}
    if response.status_code >= 400:
        message = body.get("error") if isinstance(body, dict) else None
        raise RuntimeError(message or f"Browser service error ({response.status_code})")
    return body if isinstance(body, dict) else {"data": body}


async def _browser_health() -> dict:
    return await _browser_service_request("GET", "/health", timeout=2.0)


async def _browser_reset() -> dict:
    return await _browser_service_request("POST", "/session/reset", {})


async def _browser_navigate(url: str) -> dict:
    return await _browser_service_request("POST", "/page/navigate", {"url": url})


async def _browser_snapshot() -> dict:
    return await _browser_service_request(
        "POST",
        "/page/snapshot",
        {
            "max_text": BROWSER_SNAPSHOT_TEXT_LIMIT,
            "max_elements": BROWSER_SNAPSHOT_ELEMENT_LIMIT,
        },
    )


async def _browser_click(*, element_id: Optional[int] = None, selector: str = "") -> dict:
    payload: dict[str, Any] = {}
    if element_id is not None:
        payload["elementId"] = int(element_id)
    if selector:
        payload["selector"] = selector
    return await _browser_service_request("POST", "/page/click", payload)


async def _browser_type(
    *,
    text: str,
    element_id: Optional[int] = None,
    selector: str = "",
    submit: bool = False,
) -> dict:
    payload: dict[str, Any] = {
        "text": text,
        "submit": bool(submit),
    }
    if element_id is not None:
        payload["elementId"] = int(element_id)
    if selector:
        payload["selector"] = selector
    return await _browser_service_request("POST", "/page/type", payload)


async def _browser_wait(*, text: str = "", seconds: float = 1.0) -> dict:
    safe_seconds = max(0.0, min(float(seconds), 30.0))
    payload: dict[str, Any] = {"seconds": safe_seconds}
    if text:
        payload["text"] = text
    return await _browser_service_request("POST", "/page/wait", payload)


def _summarize_browser_snapshot(snapshot: dict) -> str:
    lines = [
        f"Page title: {snapshot.get('title') or 'Untitled'}",
        f"URL: {snapshot.get('url') or 'about:blank'}",
    ]

    excerpt = (snapshot.get("textExcerpt") or "").strip()
    if excerpt:
        lines.extend(["", "Visible text excerpt:", excerpt[:BROWSER_SNAPSHOT_TEXT_LIMIT]])

    elements = snapshot.get("elements") or []
    if elements:
        lines.extend(["", "Actionable elements:"])
        for item in elements[:BROWSER_SNAPSHOT_ELEMENT_LIMIT]:
            label = (
                item.get("text")
                or item.get("label")
                or item.get("placeholder")
                or item.get("selector")
                or "(no label)"
            )
            detail_parts = [item.get("tag") or "element"]
            if item.get("role"):
                detail_parts.append(f"role={item.get('role')}")
            if item.get("href"):
                detail_parts.append(f"href={item.get('href')}")
            if item.get("disabled"):
                detail_parts.append("disabled")
            lines.append(f"- {item.get('id')} | {' | '.join(detail_parts)} | {label}")
        lines.append("Use browser_click or browser_type with element_id from this list.")
    else:
        lines.extend(["", "No actionable elements were detected in the current snapshot."])

    return "\n".join(lines)


def _summarize_browser_action(action: str, payload: dict) -> str:
    lines = [f"Browser action: {action}"]
    if payload.get("title"):
        lines.append(f"Page title: {payload.get('title')}")
    if payload.get("url"):
        lines.append(f"URL: {payload.get('url')}")
    if payload.get("status") is not None:
        lines.append(f"HTTP status: {payload.get('status')}")
    if payload.get("selector"):
        lines.append(f"Selector: {payload.get('selector')}")
    if payload.get("message"):
        lines.append(payload.get("message"))
    return "\n".join(lines)


def _generate_text(prompt: str, max_tokens: int, temperature: float, top_p: float, repetition_penalty: float) -> str:
    from mlx_lm import generate

    generation_runtime = _build_generation_runtime(
        temperature=temperature,
        top_p=top_p,
        repetition_penalty=repetition_penalty,
    )
    return generate(
        _model,
        _tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        **generation_runtime,
    )


def _render_prompt_from_messages(messages: list[dict], fallback_prompt: str = "") -> str:
    prompt = fallback_prompt
    if messages:
        try:
            prompt = _tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            prompt = json.dumps(messages, ensure_ascii=False)
    return prompt


def _workflow_system_prompt(
    workflow_mode: str,
    *,
    deep_research: bool = False,
    approval_mode: str = "manual",
) -> str:
    lines: list[str] = []
    if workflow_mode == "plan":
        lines.extend(
            [
                "Operating mode: plan.",
                "Inspect the available context first and return a concrete implementation plan before changing files.",
                "Do not stage or apply workspace mutations in plan mode.",
            ]
        )
    elif workflow_mode == "build":
        lines.extend(
            [
                "Operating mode: build.",
                "Inspect the available workspace and context before editing files.",
                "When changes are needed, prefer coherent repo-level batches over fragmented edits.",
            ]
        )
    else:
        lines.extend(
            [
                "Operating mode: chat.",
                "Answer directly unless the user explicitly asks for planning or implementation work.",
            ]
        )

    if deep_research:
        lines.extend(
            [
                "Extended research is enabled.",
                "Use broader source gathering, multiple searches, and longer synthesis before concluding.",
            ]
        )

    if approval_mode == "auto":
        lines.append("Workspace changes may auto-apply only in build mode when a safe batch is prepared.")
    else:
        lines.append("Workspace changes require user approval before they are applied.")

    return "\n".join(lines)


def _merge_system_prompt(messages: list[dict], workflow_prompt: str) -> list[dict]:
    merged = [dict(message) for message in (messages or []) if isinstance(message, dict)]
    if not workflow_prompt:
        return merged
    if merged and merged[0].get("role") == "system":
        existing = str(merged[0].get("content") or "").strip()
        merged[0]["content"] = (
            f"{existing}\n\n{workflow_prompt}".strip()
            if existing
            else workflow_prompt
        )
    else:
        merged.insert(0, {"role": "system", "content": workflow_prompt})
    return merged


def _workflow_min_output_tokens(workflow_mode: str, *, deep_research: bool = False) -> int:
    if deep_research:
        return 3584
    if workflow_mode == "build":
        return 3072
    if workflow_mode == "plan":
        return 2560
    return 512


def _extract_json_object(text: str) -> Optional[dict]:
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    for start in range(len(stripped)):
        if stripped[start] != "{":
            continue
        depth = 0
        for idx in range(start, len(stripped)):
            char = stripped[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : idx + 1]
                    try:
                        payload = json.loads(candidate)
                    except Exception:
                        break
                    if isinstance(payload, dict):
                        return payload
                    break
    return None


def _agent_tool_prompt(
    project: Optional[dict] = None,
    *,
    workflow_mode: str = "chat",
    deep_research: bool = False,
    approval_mode: str = "manual",
) -> str:
    providers = ", ".join(connector["id"] for connector in _connector_catalog())
    workspace_state = _workspace_info(project or {})
    workspace_line = (
        f"Workspace enabled for the active project at: {workspace_state.get('root')}\n"
        if workspace_state.get("enabled")
        else "Workspace is not selected for the active project.\n"
    )
    approval_line = (
        "Workspace auto-apply is enabled for build mode.\n"
        if workflow_mode == "build" and approval_mode == "auto"
        else "Workspace changes require explicit approval after staging.\n"
    )
    research_line = (
        "Extended research is enabled. Prefer deeper source gathering before responding.\n"
        if deep_research
        else ""
    )
    return (
        "JSON-only tool dispatcher. Output exactly one raw JSON object. No prose, no markdown, no explanation, no <tool_call> tags.\n"
        "Your entire response must be a single JSON object starting with { and ending with }.\n"
        "\n"
        f"{workspace_line}"
        f"Workflow mode: {workflow_mode}\n"
        f"{approval_line}"
        f"{research_line}"
        "\n"
        "TOOLS (use one per turn):\n"
        f'  search_source: {{"action":"tool","tool":"search_source","args":{{"provider":"PROVIDER","query":"QUERY"}}}}  providers: {providers}\n'
        '  fetch_source:  {"action":"tool","tool":"fetch_source","args":{"provider":"PROVIDER","id":"ID"}}\n'
        '  browser_navigate: {"action":"tool","tool":"browser_navigate","args":{"url":"URL"}}\n'
        '  browser_snapshot: {"action":"tool","tool":"browser_snapshot","args":{}}\n'
        '  browser_click:    {"action":"tool","tool":"browser_click","args":{"selector":"CSS_SELECTOR"}}\n'
        '  browser_type:     {"action":"tool","tool":"browser_type","args":{"selector":"CSS_SELECTOR","text":"TEXT","submit":true}}\n'
        '  browser_wait:     {"action":"tool","tool":"browser_wait","args":{"text":"TEXT","seconds":2}}\n'
        '  workspace_tree:   {"action":"tool","tool":"workspace_tree","args":{"path":".","depth":3}}\n'
        '  workspace_read:   {"action":"tool","tool":"workspace_read","args":{"path":"relative/path.txt"}}\n'
        '  workspace_find:   {"action":"tool","tool":"workspace_find","args":{"query":"needle","path":"."}}\n'
        '  workspace_apply:  {"action":"tool","tool":"workspace_apply","args":{"operations":[{"type":"write_file","path":"README.md","content":"...","expected_hash":"OPTIONAL_SHA256"}]}}\n'
        '  done:             {"action":"respond"}\n'
        "\n"
        "Rules:\n"
        "- For browser tasks: navigate first, snapshot to inspect the page, then click or type.\n"
        "- Use selector (CSS) for click/type. Do not use element_id.\n"
        "- Workspace tools operate only inside the active project's selected workspace root.\n"
        "- Use workspace_tree and workspace_read before editing files.\n"
        "- In plan mode, do not call workspace_apply.\n"
        "- In build mode with manual approval, workspace_apply stages a pending batch for review.\n"
        "- In build mode with auto approval, workspace_apply may be applied immediately after validation.\n"
        "- Include expected_hash from workspace_read before overwriting an existing file.\n"
        "- One action per response. Nothing outside the JSON object."
    )


def _summarize_search_results(provider: str, results: list[dict]) -> str:
    if not results:
        return f"No {provider} results found."
    lines = [f"{len(results)} {provider} results:"]
    for item in results[:5]:
        lines.append(
            f"- id: {item.get('id')} | title: {item.get('title')} | details: {item.get('subtitle') or item.get('description') or ''}"
        )
    lines.append("Use fetch_source with an exact id if you need one of these.")
    return "\n".join(lines)


def _summarize_fetched_attachment(attachment: dict) -> str:
    excerpt = (attachment.get("text_excerpt") or "").strip()
    lines = [
        f"Fetched source: {attachment.get('relative_path') or attachment.get('name')}",
    ]
    source_url = attachment.get("source_url")
    if source_url:
        lines.append(f"URL: {source_url}")
    if excerpt:
        lines.extend(["", excerpt[:12000]])
    return "\n".join(lines)


async def _resolve_agent_tools(
    messages: list[dict],
    prompt: str,
    temperature: float,
    top_p: float,
    repetition_penalty: float,
    project_id: str,
    workflow_mode: str,
    deep_research: bool,
    approval_mode: str,
    status_callback: Optional[Any] = None,
) -> tuple[list[dict], list[dict], Optional[dict]]:
    if _model is None or _tokenizer is None:
        return messages, [], None

    working_messages = list(messages) if messages else [{"role": "user", "content": prompt}]
    tool_runs: list[dict] = []
    pending_workspace_batch: Optional[dict] = None
    project = None
    try:
        project, _, _ = _ensure_workspace_project(project_id)
    except Exception:
        project = None

    step_limit = MAX_AGENT_TOOL_STEPS + (4 if deep_research else 0)
    planner_token_budget = AGENT_TOOL_MAX_TOKENS + (2000 if deep_research else 0)

    for step in range(step_limit):
        planner_messages = [
            {"role": "system", "content": _agent_tool_prompt(
                project,
                workflow_mode=workflow_mode,
                deep_research=deep_research,
                approval_mode=approval_mode,
            )},
            *working_messages,
        ]
        planner_prompt = _render_prompt_from_messages(planner_messages, prompt)
        # Inject partial assistant prefix to force first token to be `{`
        # This is the most reliable way to get any LLM to output JSON without prose.
        JSON_PREFIX = '{"action":'
        planner_output_raw = _generate_text(
            prompt=planner_prompt + JSON_PREFIX,
            max_tokens=planner_token_budget,
            temperature=min(temperature, 0.1),
            top_p=0.9,
            repetition_penalty=repetition_penalty,
        )
        # Re-attach the prefix we injected so _extract_json_object can parse it
        planner_output = JSON_PREFIX + (planner_output_raw or "")
        plan = _extract_json_object(planner_output)
        if not isinstance(plan, dict):
            break
        if plan.get("action") != "tool":
            break

        tool_name = str(plan.get("tool") or "").strip()
        args = plan.get("args") if isinstance(plan.get("args"), dict) else {}
        provider = str(args.get("provider") or "").strip()

        if status_callback is not None:
            await status_callback(
                {
                    "type": "agent_status",
                    "message": f"Agent step {step + 1}: {tool_name}{f' on {provider}' if provider else ''}",
                }
            )

        try:
            if tool_name == "search_source":
                query = str(args.get("query") or "").strip()
                if not provider or not query:
                    raise RuntimeError("search_source requires provider and query")
                results = await _search_connector(provider, query)
                tool_runs.append({"tool": tool_name, "provider": provider, "query": query, "count": len(results)})
                tool_feedback = _summarize_search_results(provider, results)
            elif tool_name == "fetch_source":
                item_id = str(args.get("id") or "").strip()
                if not provider or not item_id:
                    raise RuntimeError("fetch_source requires provider and id")
                fetched = await _fetch_connector(provider, item_id)
                attachment = fetched.get("attachment") or {}
                tool_runs.append({"tool": tool_name, "provider": provider, "id": item_id})
                tool_feedback = _summarize_fetched_attachment(attachment)
            elif tool_name == "browser_navigate":
                url = str(args.get("url") or "").strip()
                if not url:
                    raise RuntimeError("browser_navigate requires url")
                result = await _browser_navigate(url)
                tool_runs.append({"tool": tool_name, "url": url})
                tool_feedback = _summarize_browser_action("navigate", result)
            elif tool_name == "browser_snapshot":
                snapshot = await _browser_snapshot()
                tool_runs.append({"tool": tool_name, "url": snapshot.get("url") or ""})
                tool_feedback = _summarize_browser_snapshot(snapshot)
            elif tool_name == "browser_click":
                raw_element_id = args.get("element_id")
                selector = str(args.get("selector") or "").strip()
                if raw_element_id in (None, "") and not selector:
                    raise RuntimeError("browser_click requires element_id or selector")
                element_id = int(raw_element_id) if raw_element_id not in (None, "") else None
                result = await _browser_click(element_id=element_id, selector=selector)
                tool_runs.append({"tool": tool_name, "element_id": element_id, "selector": selector})
                tool_feedback = _summarize_browser_action("click", result)
            elif tool_name == "browser_type":
                raw_element_id = args.get("element_id")
                selector = str(args.get("selector") or "").strip()
                text_value = str(args.get("text") or "")
                if not text_value:
                    raise RuntimeError("browser_type requires text")
                if raw_element_id in (None, "") and not selector:
                    raise RuntimeError("browser_type requires element_id or selector")
                element_id = int(raw_element_id) if raw_element_id not in (None, "") else None
                submit = bool(args.get("submit"))
                result = await _browser_type(
                    text=text_value,
                    element_id=element_id,
                    selector=selector,
                    submit=submit,
                )
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "element_id": element_id,
                        "selector": selector,
                        "text": text_value,
                        "submit": submit,
                    }
                )
                tool_feedback = _summarize_browser_action("type", result)
            elif tool_name == "browser_wait":
                text_value = str(args.get("text") or "").strip()
                seconds = args.get("seconds", 1)
                result = await _browser_wait(text=text_value, seconds=float(seconds))
                tool_runs.append({"tool": tool_name, "text": text_value, "seconds": seconds})
                tool_feedback = _summarize_browser_action("wait", result)
            elif tool_name == "workspace_tree":
                relative_path = str(args.get("path") or ".").strip() or "."
                depth = int(args.get("depth") or 3)
                project, root, _ = _ensure_workspace_project(project_id)
                result = _workspace_tree(root, relative_path, depth=depth)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "path": relative_path,
                        "depth": depth,
                        "count": len(result.get("items") or []),
                    }
                )
                lines = [f"Workspace tree for {result.get('path')}:"]
                for item in (result.get("items") or [])[:40]:
                    prefix = "dir" if item.get("kind") == "directory" else "file"
                    lines.append(f"- {prefix}: {item.get('path')}")
                tool_feedback = "\n".join(lines)
            elif tool_name == "workspace_read":
                relative_path = str(args.get("path") or "").strip()
                if not relative_path:
                    raise RuntimeError("workspace_read requires path")
                project, root, _ = _ensure_workspace_project(project_id)
                result = _read_workspace_file(root, relative_path)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "path": relative_path,
                        "sha256": result.get("sha256"),
                    }
                )
                tool_feedback = (
                    f"Read file: {result.get('path')}\n"
                    f"sha256: {result.get('sha256')}\n"
                    f"size_bytes: {result.get('size_bytes')}\n\n"
                    f"{(result.get('content') or '')[:12000]}"
                )
            elif tool_name == "workspace_find":
                query = str(args.get("query") or "").strip()
                relative_path = str(args.get("path") or ".").strip() or "."
                if not query:
                    raise RuntimeError("workspace_find requires query")
                project, root, _ = _ensure_workspace_project(project_id)
                results = _find_workspace_matches(root, query, relative_path)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "query": query,
                        "path": relative_path,
                        "count": len(results),
                    }
                )
                tool_feedback = (
                    "\n".join(
                        [f"{len(results)} workspace matches:"]
                        + [
                            f"- {item.get('path')}:{item.get('line') or ''} {item.get('preview') or ''}".rstrip()
                            for item in results[:40]
                        ]
                    )
                    if results
                    else "No workspace matches found."
                )
            elif tool_name == "workspace_apply":
                if workflow_mode != "build":
                    raise RuntimeError("workspace_apply is only available in build mode.")
                operations = _sanitize_workspace_operations(args.get("operations"))
                auto_apply = approval_mode == "auto"
                project, batch, applied = _stage_or_apply_workspace_batch(
                    project_id,
                    operations,
                    auto_apply=auto_apply,
                )
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "pending_batch_id": None if applied else batch.get("id"),
                        "applied_batch_id": batch.get("id") if applied else None,
                        "count": len(operations),
                        "auto_applied": applied,
                    }
                )
                if applied:
                    pending_workspace_batch = None
                    tool_feedback = (
                        f"Workspace batch applied automatically: {batch.get('id')}\n"
                        f"Operations: {batch.get('summary', {}).get('total_operations', len(operations))}\n"
                        "Continue with verification or the next build step."
                    )
                    if status_callback is not None:
                        await status_callback(
                            {
                                "type": "agent_status",
                                "message": (
                                    f"Workspace batch {batch.get('id')} auto-applied "
                                    f"with {batch.get('summary', {}).get('total_operations', len(operations))} operations."
                                ),
                            }
                        )
                else:
                    pending_workspace_batch = batch
                    tool_feedback = (
                        f"Pending workspace batch staged: {batch.get('id')}\n"
                        f"Operations: {batch.get('summary', {}).get('total_operations', len(operations))}\n"
                        "Changes are NOT applied yet. Tell the user to review and approve them."
                    )
                    if status_callback is not None:
                        await status_callback(
                            {
                                "type": "workspace_pending",
                                "project_id": project_id,
                                "batch": batch,
                            }
                        )
            else:
                raise RuntimeError(f"Unknown tool: {tool_name}")
        except Exception as exc:
            tool_feedback = f"Tool execution failed: {exc}"
            tool_runs.append({"tool": tool_name, "provider": provider, "error": str(exc)})

        working_messages.append(
            {
                "role": "assistant",
                "content": json.dumps(plan, ensure_ascii=False),
            }
        )
        working_messages.append(
            {
                "role": "user",
                "content": (
                    f"Tool result:\n{tool_feedback}\n\n"
                    "If you need another tool, return one JSON object. Otherwise return "
                    '{"action":"respond"}.'
                ),
            }
        )

    return working_messages, tool_runs, pending_workspace_batch


def _push_event(event_type: str, data: dict) -> None:
    """Push an event to all connected SSE clients."""
    event = {"type": event_type, **data, "timestamp": time.time()}
    try:
        _event_queue.put_nowait(event)
    except queue.Full:
        # Drop oldest event to prevent backpressure
        try:
            _event_queue.get_nowait()
        except queue.Empty:
            pass
        _event_queue.put_nowait(event)


# ---------------------------------------------------------------------------
# System Info
# ---------------------------------------------------------------------------
_cached_system_info: Optional[dict] = None


def _system_info() -> dict:
    """Gather Apple Silicon system info (cached after first call)."""
    global _cached_system_info
    if _cached_system_info is not None:
        return _cached_system_info

    with PerfTimer("system_info"):
        info = {
            "chip": "Unknown",
            "memory_gb": 0,
            "gpu_cores": 0,
            "metal_version": "Unknown",
            "os_version": platform.mac_ver()[0],
        }
        try:
            mem = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
            info["memory_gb"] = round(mem / (1024 ** 3), 1)
        except Exception:
            pass
        try:
            brand = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"]
            ).decode().strip()
            info["chip"] = brand
        except Exception:
            pass
        try:
            sp = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"], text=True
            )
            for line in sp.splitlines():
                if "Total Number of Cores" in line:
                    info["gpu_cores"] = int(line.split(":")[-1].strip())
                if "Metal Support" in line:
                    info["metal_version"] = line.split(":")[-1].strip()
        except Exception:
            pass

        _cached_system_info = info
    return info


# ---------------------------------------------------------------------------
# Memory Management — ported from AI-ArtWirks engines.py
# ---------------------------------------------------------------------------
def _get_memory_usage() -> dict:
    """Get current memory pressure and usage via vm_stat."""
    info = {
        "used_gb": 0,
        "available_gb": 0,
        "total_gb": 0,
        "pressure_percent": 0,
        "swap_used_gb": 0,
    }
    try:
        mem = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip())
        info["total_gb"] = round(mem / (1024 ** 3), 1)
    except Exception:
        pass

    try:
        vm = subprocess.check_output(["vm_stat"], text=True)
        page_size = 16384  # Apple Silicon default
        pages = {}
        for line in vm.splitlines():
            if "page size of" in line:
                try:
                    page_size = int(re.search(r"(\d+) bytes", line).group(1))
                except Exception:
                    pass
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip().lower()
                val = parts[1].strip().rstrip(".")
                try:
                    pages[key] = int(val)
                except ValueError:
                    pass

        free = pages.get("pages free", 0)
        active = pages.get("pages active", 0)
        inactive = pages.get("pages inactive", 0)
        speculative = pages.get("pages speculative", 0)
        wired = pages.get("pages wired down", 0)
        compressed = pages.get("pages occupied by compressor", 0)

        used_pages = active + wired + compressed
        available_pages = free + inactive + speculative

        info["used_gb"] = round((used_pages * page_size) / (1024 ** 3), 1)
        info["available_gb"] = round((available_pages * page_size) / (1024 ** 3), 1)
        if info["total_gb"] > 0:
            info["pressure_percent"] = round(
                (info["used_gb"] / info["total_gb"]) * 100, 1
            )
    except Exception:
        pass

    try:
        swap_out = subprocess.check_output(
            ["sysctl", "-n", "vm.swapusage"], text=True
        )
        match = re.search(r"used\s*=\s*([\d.]+)M", swap_out)
        if match:
            info["swap_used_gb"] = round(float(match.group(1)) / 1024, 2)
    except Exception:
        pass

    return info


def _ensure_memory_headroom(operation: str = "generation") -> None:
    """
    Pre-operation memory pressure check.
    Ported from AI-ArtWirks _ensure_comfyui_headroom().
    
    Raises RuntimeError if system is under dangerous pressure,
    preventing OOM crashes that brick the machine.
    """
    mem = _get_memory_usage()
    pressure = mem.get("pressure_percent", 0)
    available = mem.get("available_gb", 0)
    used = mem.get("used_gb", 0)
    total = mem.get("total_gb", 0)

    if pressure >= MEMORY_PRESSURE_BLOCK or available < MIN_FREE_GB_FOR_GENERATION:
        _push_event("memory_warning", {
            "level": "critical",
            "pressure_percent": pressure,
            "available_gb": available,
        })
        raise RuntimeError(
            f"Generation blocked — system memory at {pressure}% "
            f"({used}GB used / {available}GB free of {total}GB). "
            f"Unload the model, close memory-heavy apps, or wait for "
            f"current tasks to finish. "
            f"Safety floor: {MIN_FREE_GB_FOR_GENERATION}GB free required."
        )
    elif pressure >= MEMORY_PRESSURE_WARN:
        _push_event("memory_warning", {
            "level": "warning",
            "pressure_percent": pressure,
            "available_gb": available,
        })
        print(f"⚠️  Memory pressure at {pressure}% — generation allowed but close to limit")


def _smart_cleanup(reason: str = "") -> float:
    """
    Force-cleanup model and memory state.
    Ported from AI-ArtWirks _unload_diffusers_pipelines() + _prepare_for_engine().
    
    Returns: estimated freed MB (approximate from gc collection).
    """
    global _model, _tokenizer

    mem_before = _get_memory_usage()

    # Explicitly delete model references
    if _model is not None:
        del _model
        _model = None
    if _tokenizer is not None:
        del _tokenizer
        _tokenizer = None

    # Force garbage collection
    gc.collect()

    # MPS cache cleanup (equivalent to torch.mps.empty_cache in AI-ArtWirks engines.py)
    try:
        import torch
        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
            print(f"   ↳ MPS cache cleared ({reason})")
    except ImportError:
        pass

    # MLX cache cleanup
    try:
        import mlx.core as mx
        mx.metal.clear_cache()
        print(f"   ↳ MLX Metal cache cleared ({reason})")
    except (ImportError, AttributeError):
        pass

    gc.collect()

    mem_after = _get_memory_usage()
    freed = mem_before.get("used_gb", 0) - mem_after.get("used_gb", 0)
    if freed > 0:
        print(f"   ↳ Freed ~{freed:.1f}GB ({reason})")

    return freed


# ---------------------------------------------------------------------------
# Mixed Quantization Detection
# ---------------------------------------------------------------------------
def _load_json_file(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _checkpoint_key_to_module_path(weight_key: str) -> Optional[str]:
    """
    Translate sanitized checkpoint keys back to MLX module paths used by
    ``nn.quantize(class_predicate=...)``.

    Example:
      model.language_model.layers.0.self_attn.q_proj.weight
      -> language_model.model.layers.0.self_attn.q_proj
    """
    if not weight_key.endswith(".weight"):
        return None
    if not weight_key.startswith("model.language_model."):
        return None
    module_key = weight_key[: -len(".weight")]
    module_suffix = module_key[len("model.language_model.") :]
    return f"language_model.model.{module_suffix}"


def _infer_quant_bits(weight_shape: list[int], scale_shape: list[int], group_size: int) -> Optional[int]:
    """
    Infer packed bit-width from MLX quantized tensor shapes.

    MLX packs quantized weights into uint32 blocks, so the packed column count
    scales with ``32 / bits`` relative to the logical input dimension.
    """
    if group_size <= 0:
        return None
    if len(weight_shape) != 2 or len(scale_shape) != 2:
        return None
    logical_in_features = scale_shape[-1] * group_size
    packed_cols = weight_shape[-1]
    if logical_in_features <= 0 or packed_cols <= 0:
        return None
    numerator = packed_cols * 32
    if numerator % logical_in_features != 0:
        return None
    bits = numerator // logical_in_features
    if bits <= 0 or bits > 32:
        return None
    return bits


def _scan_mixed_quantization_overrides(model_path: Path) -> Optional[dict]:
    """
    Detect per-module MLX quantization overrides for mixed-bit checkpoints.

    Returns a full ``quantization`` config dict compatible with
    ``mlx_lm.load(..., model_config=...)`` when overrides are needed.
    """
    config_path = model_path / "config.json"
    if not config_path.exists():
        return None

    config = _load_json_file(config_path)
    quantization = config.get("quantization")
    if not isinstance(quantization, dict):
        return None

    try:
        default_bits = int(quantization["bits"])
        group_size = int(quantization["group_size"])
    except (KeyError, TypeError, ValueError):
        return None

    shard_files = sorted(model_path.glob("model*.safetensors"))
    if not shard_files:
        return None

    try:
        from safetensors import safe_open
    except Exception:
        return None

    overrides: dict[str, dict] = {}
    mode = quantization.get("mode")

    for shard_path in shard_files:
        try:
            with safe_open(str(shard_path), framework="np") as shard:
                shard_keys = set(shard.keys())
                for key in shard_keys:
                    if not key.endswith(".weight"):
                        continue
                    module_path = _checkpoint_key_to_module_path(key)
                    if not module_path:
                        continue

                    scales_key = key[: -len(".weight")] + ".scales"
                    if scales_key not in shard_keys:
                        continue

                    weight_shape = shard.get_slice(key).get_shape()
                    scale_shape = shard.get_slice(scales_key).get_shape()
                    bits = _infer_quant_bits(weight_shape, scale_shape, group_size)
                    if bits is None or bits == default_bits:
                        continue

                    override = {
                        "group_size": group_size,
                        "bits": bits,
                    }
                    if mode:
                        override["mode"] = mode
                    overrides[module_path] = override
        except Exception as exc:
            print(f"⚠️  Mixed-quant scan skipped for {shard_path.name}: {exc}")
            return None

    if not overrides:
        return None

    merged_quantization = dict(quantization)
    merged_quantization.update(dict(sorted(overrides.items())))
    print(
        f"↳ Detected mixed quantization for {model_path.name}: "
        f"default {default_bits}-bit with {len(overrides)} module overrides"
    )
    return merged_quantization


# ---------------------------------------------------------------------------
# Model Detection — ported from AI-ArtWirks runtime/models.py
# ---------------------------------------------------------------------------
def _is_valid_model_dir(p: Path) -> bool:
    """Check if a directory looks like a valid HF model."""
    if not p.is_dir():
        return False
    has_config = (p / "config.json").exists()
    has_safetensors = any(p.glob("*.safetensors")) or any(p.glob("**/*.safetensors"))
    has_tokenizer = (
        (p / "tokenizer.json").exists()
        or (p / "tokenizer_config.json").exists()
        or (p / "tokenizer.model").exists()
    )
    # Also detect MLX models (from AI-ArtWirks _is_model_repo_dir)
    has_mlx_weights = any(p.glob("*.npz")) or (p / "mlx_model.safetensors").exists()
    return has_config and (has_safetensors or has_tokenizer or has_mlx_weights)


def _detect_model_profile(p: Path, name: str) -> dict:
    """
    Rich model profiling — ported from AI-ArtWirks _detect_model_profile().
    
    Detects: quantization, modality, family, engine_hint, params, context_length.
    Uses config.json analysis + filename patterns for comprehensive detection.
    """
    meta = {
        "quantization": "unknown",
        "modality": "text",
        "family": "unknown",
        "engine_hint": "mlx",
        "params": "",
        "context_length": 0,
    }

    name_lower = name.lower()

    # ── config.json deep analysis (from AI-ArtWirks _detect_model_profile) ──
    config_path = p / "config.json"
    config: dict = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception:
            pass

    model_type = str(config.get("model_type", "")).lower()
    architectures = [str(a).lower() for a in config.get("architectures", [])]

    # ── Context length detection ──
    for key in ("max_position_embeddings", "max_seq_len", "seq_length",
                "max_sequence_length", "sliding_window"):
        if key in config:
            try:
                meta["context_length"] = int(config[key])
                break
            except (ValueError, TypeError):
                pass

    # ── VLM detection (from AI-ArtWirks — checks config tokens) ──
    has_vlm_tokens = any(key in config for key in (
        "image_token_id", "video_token_id",
        "vision_start_token_id", "vision_end_token_id",
    ))
    if has_vlm_tokens or "vl" in model_type or \
       any(("vl" in a or "vision" in a or "llava" in a) for a in architectures):
        meta["modality"] = "vision"
        meta["family"] = "vlm"
        meta["engine_hint"] = "mlx-vlm"

    # ── Diffusion detection ──
    has_diffusers_index = (p / "model_index.json").exists()
    if has_diffusers_index:
        meta["modality"] = "diffusion"
        meta["family"] = "diffusers"
        meta["engine_hint"] = "diffusers"

    diffusion_keywords = ["flux", "sdxl", "stable-diffusion", "sd3", "playground",
                          "kandinsky", "dall"]
    for kw in diffusion_keywords:
        if kw in name_lower:
            meta["modality"] = "diffusion"
            meta["family"] = "diffusers"
            meta["engine_hint"] = "diffusers"
            break

    # ── MLX-specific detection (from AI-ArtWirks _detect_model_profile) ──
    has_mlx_weights = any(p.glob("*.npz")) or (p / "mlx_model.safetensors").exists()
    if has_mlx_weights or "mlx-community" in name_lower or "mlx" in name_lower:
        if meta["family"] == "unknown":
            meta["family"] = "mlx-llm"
            meta["engine_hint"] = "mlx"

    # ── Quantization detection (enhanced from AI-ArtWirks) ──
    # First check config.json quantization metadata
    quant_config = config.get("quantization_config") or config.get("quantization") or {}
    if quant_config:
        bits = quant_config.get("bits") or quant_config.get("quant_method")
        if bits is not None:
            if isinstance(bits, int):
                meta["quantization"] = f"{bits}-bit"
            else:
                meta["quantization"] = str(bits).upper()

    jang_config_path = p / "jang_config.json"
    if jang_config_path.exists():
        jang_config = _load_json_file(jang_config_path)
        bit_widths = jang_config.get("quantization", {}).get("bit_widths_used", [])
        bit_widths = sorted({int(bits) for bits in bit_widths if isinstance(bits, int) or str(bits).isdigit()})
        if len(bit_widths) > 1:
            joined = "/".join(str(bits) for bits in bit_widths)
            meta["quantization"] = f"mixed {joined}-bit"
        elif len(bit_widths) == 1 and meta["quantization"] == "unknown":
            meta["quantization"] = f"{bit_widths[0]}-bit"

    # Fallback to name-based detection
    if meta["quantization"] == "unknown":
        quant_patterns = [
            ("4bit", "4-bit"), ("8bit", "8-bit"), ("3bit", "3-bit"),
            ("q4_", "Q4"), ("q8_", "Q8"), ("q6_", "Q6"),
            ("int4", "INT4"), ("int8", "INT8"),
            ("fp16", "FP16"), ("bf16", "BF16"), ("fp32", "FP32"),
            ("awq", "AWQ"), ("gptq", "GPTQ"), ("gguf", "GGUF"),
        ]
        for pattern, label in quant_patterns:
            if pattern in name_lower:
                meta["quantization"] = label
                break

    # ── Parameter count detection ──
    param_patterns = re.findall(r"(\d+\.?\d*)[bB]", name)
    if param_patterns:
        meta["params"] = param_patterns[-1] + "B"
    elif not meta["params"]:
        # Estimate from config (hidden_size × num_layers × ~12 for typical LLM)
        hidden = config.get("hidden_size", 0)
        layers = config.get("num_hidden_layers", 0)
        if hidden and layers:
            approx_b = round((hidden * hidden * layers * 12) / 1e9, 1)
            if approx_b > 0.1:
                meta["params"] = f"~{approx_b}B"

    # ── Family fallback: detect from model_type ──
    if meta["family"] == "unknown" and meta["modality"] == "text":
        family_map = {
            "llama": "llama", "mistral": "mistral", "gemma": "gemma",
            "qwen": "qwen", "phi": "phi", "starcoder": "starcoder",
            "codellama": "codellama", "deepseek": "deepseek",
            "command": "command-r", "cohere": "command-r",
        }
        for key, fam in family_map.items():
            if key in model_type or key in name_lower:
                meta["family"] = fam
                break

    return meta


def _scan_models() -> list[dict]:
    """Scan all model directories for available models."""
    with PerfTimer("model_scan"):
        models = []
        seen = set()

        for model_dir in MODEL_DIRS:
            base = Path(model_dir)
            if not base.exists():
                continue

            # Direct children
            for child in sorted(base.iterdir()):
                if child.name.startswith("."):
                    continue

                # HuggingFace cache format: models--org--name
                if child.name.startswith("models--"):
                    parts = child.name.split("--", 2)
                    if len(parts) == 3:
                        display_name = f"{parts[1]}/{parts[2]}"
                        # Find the actual snapshot dir
                        snapshots = child / "snapshots"
                        if snapshots.exists():
                            snap_dirs = sorted(snapshots.iterdir(), reverse=True)
                            if snap_dirs:
                                real_path = str(snap_dirs[0])
                                if display_name not in seen:
                                    seen.add(display_name)
                                    size = _dir_size_gb(snap_dirs[0])
                                    meta = _detect_model_profile(
                                        snap_dirs[0], display_name
                                    )
                                    models.append({
                                        "name": display_name,
                                        "path": real_path,
                                        "size_gb": size,
                                        "source": "huggingface_cache",
                                        **meta,
                                    })
                    continue

                if _is_valid_model_dir(child):
                    name = child.name
                    if name not in seen:
                        seen.add(name)
                        size = _dir_size_gb(child)
                        meta = _detect_model_profile(child, name)
                        models.append({
                            "name": name,
                            "path": str(child),
                            "size_gb": size,
                            "source": str(base),
                            **meta,
                        })

    return models


def _dir_size_gb(p: Path) -> float:
    """Estimate directory size in GB."""
    total = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return round(total / (1024 ** 3), 2)


# ---------------------------------------------------------------------------
# Prompt Enrichment — lightweight port from AI-ArtWirks runtime/prompt.py
# ---------------------------------------------------------------------------
PROMPT_ENRICHMENTS: dict[str, dict[str, Any]] = {
    "general": {
        "label": "General Assistant",
        "system_prefix": "You are a helpful, concise AI assistant.",
        "enrichments": [],
    },
    "coding": {
        "label": "Code Assistant",
        "system_prefix": (
            "You are an expert software engineer. Write clean, efficient, "
            "well-documented code. Explain your reasoning step by step."
        ),
        "enrichments": [
            "Use modern best practices and idiomatic patterns.",
            "Include error handling and edge cases.",
            "Prefer readability over cleverness.",
        ],
        "detect_keywords": ["code", "function", "debug", "implement", "python",
                           "javascript", "rust", "class", "api", "sql", "fix", "bug"],
    },
    "creative": {
        "label": "Creative Writer",
        "system_prefix": (
            "You are a creative writing assistant. Write vivid, engaging prose "
            "with rich imagery and compelling narratives."
        ),
        "enrichments": [
            "Use sensory details and metaphorical language.",
            "Vary sentence structure for rhythm.",
        ],
        "detect_keywords": ["story", "poem", "write", "creative", "fiction",
                           "narrative", "character", "dialogue"],
    },
    "analysis": {
        "label": "Data Analyst",
        "system_prefix": (
            "You are a data analyst and research assistant. Provide thorough, "
            "evidence-based analysis with clear reasoning."
        ),
        "enrichments": [
            "Structure your response with clear sections.",
            "Distinguish facts from inferences.",
        ],
        "detect_keywords": ["analyze", "explain", "compare", "evaluate",
                           "research", "data", "statistics", "trends"],
    },
}


def _detect_prompt_context(prompt: str) -> str:
    """Detect the best enrichment context from prompt keywords (from PromptMixin)."""
    lowered = prompt.lower()
    scores: dict[str, int] = {}
    for ctx, config in PROMPT_ENRICHMENTS.items():
        keywords = config.get("detect_keywords", [])
        score = sum(1 for kw in keywords if kw in lowered)
        if score > 0:
            scores[ctx] = score
    if scores:
        return max(scores, key=scores.get)
    return "general"


def _enrich_system_prompt(user_prompt: str, system_prompt: str = "") -> dict:
    """
    Lightweight prompt enrichment inspired by AI-ArtWirks PromptMixin.refine_prompt().
    
    Detects context from user's message and suggests/enriches the system prompt.
    """
    context = _detect_prompt_context(user_prompt)
    enrichment = PROMPT_ENRICHMENTS.get(context, PROMPT_ENRICHMENTS["general"])

    result = {
        "detected_context": context,
        "context_label": enrichment["label"],
        "suggested_system_prompt": enrichment["system_prefix"],
        "enrichments": enrichment.get("enrichments", []),
        "user_prompt": user_prompt,
    }

    # If user has a custom system prompt, respect it
    if system_prompt:
        result["active_system_prompt"] = system_prompt
    else:
        result["active_system_prompt"] = enrichment["system_prefix"]

    return result


def _build_generation_runtime(
    temperature: float,
    top_p: float,
    repetition_penalty: float,
) -> dict[str, Any]:
    """
    Build generation helpers for the current mlx_lm API.

    Recent mlx_lm versions expect ``sampler=`` and ``logits_processors=``
    instead of raw ``temp=`` / ``top_p=`` keyword arguments.
    """
    from mlx_lm.sample_utils import make_logits_processors, make_sampler

    sampler = make_sampler(
        temp=max(float(temperature), 0.0),
        top_p=max(float(top_p), 0.0),
    )
    logits_processors = make_logits_processors(
        repetition_penalty=float(repetition_penalty) if repetition_penalty else None,
    )
    return {
        "sampler": sampler,
        "logits_processors": logits_processors,
    }


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.get("/api/system")
async def get_system_info():
    return _system_info()


@app.get("/api/metrics")
async def get_metrics():
    """Live metrics endpoint: memory, generation stats."""
    mem = _get_memory_usage()
    return {
        "memory": mem,
        "generation": _generation_stats,
        "model_loaded": _model_name is not None,
        "model_name": _model_name,
        "memory_guarded": mem.get("pressure_percent", 0) >= MEMORY_PRESSURE_BLOCK,
        "memory_warning": mem.get("pressure_percent", 0) >= MEMORY_PRESSURE_WARN,
    }


@app.get("/api/health")
async def get_health():
    """Compact dashboard payload for model health and capability routing."""
    mem = _get_memory_usage()
    model_meta = _loaded_model_meta()
    return {
        "system": _system_info(),
        "memory": mem,
        "generation": _generation_stats,
        "loaded_model": model_meta,
        "capabilities": _capability_flags(model_meta),
        "transport": {
            "websocket": True,
            "http_fallback": True,
        },
        "warnings": {
            "memory_warning": mem.get("pressure_percent", 0) >= MEMORY_PRESSURE_WARN,
            "memory_blocked": mem.get("pressure_percent", 0) >= MEMORY_PRESSURE_BLOCK,
        },
    }


@app.get("/api/app-state")
async def get_app_state():
    return _load_app_state()


@app.post("/api/app-state")
async def save_app_state(request: dict):
    current = _load_app_state()
    incoming = dict(request or {})
    if isinstance(incoming.get("projects"), list):
        current_by_id = {
            project.get("id"): project
            for project in current.get("projects") or []
            if isinstance(project, dict) and project.get("id")
        }
        merged_projects: list[dict] = []
        for project in incoming.get("projects") or []:
            if not isinstance(project, dict):
                continue
            existing = current_by_id.get(project.get("id"))
            merged_projects.append(_deep_merge_dicts(existing or {}, project))
        incoming["projects"] = merged_projects
    merged = _deep_merge_dicts(current, incoming)
    state = _save_app_state(merged)
    return {"status": "saved", "state": state}


@app.post("/api/workspace/select")
async def select_workspace(request: dict):
    project_id = str(request.get("project_id") or "").strip()
    if not project_id:
        return JSONResponse({"error": "Missing project_id."}, status_code=400)
    try:
        if request.get("clear"):
            project = _clear_project_workspace(project_id)
            return {
                "status": "cleared",
                "project": project,
                "workspace": _workspace_info(project),
            }
        project = _set_project_workspace(
            project_id,
            str(request.get("path") or "").strip() or None,
            suggested_label=str(request.get("suggested_label") or "").strip(),
        )
        return {
            "status": "selected",
            "project": project,
            "workspace": _workspace_info(project),
        }
    except FileNotFoundError:
        return JSONResponse({"error": "Workspace path does not exist."}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/workspace/tree")
async def workspace_tree(project_id: str, path: str = ".", depth: int = MAX_WORKSPACE_TREE_DEPTH):
    try:
        project, root, _ = _ensure_workspace_project(project_id)
        tree = _workspace_tree(root, path, depth=depth)
        return {
            "project": project,
            "workspace": _workspace_info(project),
            **tree,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/workspace/read")
async def workspace_read(request: dict):
    project_id = str(request.get("project_id") or "").strip()
    path = str(request.get("path") or "").strip()
    if not project_id or not path:
        return JSONResponse({"error": "workspace_read requires project_id and path."}, status_code=400)
    try:
        project, root, _ = _ensure_workspace_project(project_id)
        payload = _read_workspace_file(root, path)
        return {
            "project": project,
            "workspace": _workspace_info(project),
            **payload,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/workspace/find")
async def workspace_find(request: dict):
    project_id = str(request.get("project_id") or "").strip()
    query = str(request.get("query") or "").strip()
    path = str(request.get("path") or ".").strip() or "."
    if not project_id or not query:
        return JSONResponse({"error": "workspace_find requires project_id and query."}, status_code=400)
    try:
        project, root, _ = _ensure_workspace_project(project_id)
        results = _find_workspace_matches(root, query, path)
        return {
            "project": project,
            "workspace": _workspace_info(project),
            "results": results,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/workspace/apply")
async def workspace_apply(request: dict):
    project_id = str(request.get("project_id") or "").strip()
    if not project_id:
        return JSONResponse({"error": "Missing project_id."}, status_code=400)
    pending_id = str(request.get("pending_id") or "").strip()
    auto_approve = bool(request.get("auto_approve"))
    try:
        if request.get("discard_pending"):
            project = _discard_workspace_batch(project_id, pending_id)
            return {
                "status": "discarded",
                "project": project,
                "workspace": _workspace_info(project),
            }

        if request.get("approve"):
            project, batch = _apply_workspace_batch(project_id, pending_id)
            return {
                "status": "applied",
                "project": project,
                "workspace": _workspace_info(project),
                "applied_batch": batch,
            }

        operations = _sanitize_workspace_operations(request.get("operations"))
        project_state, _, _ = _project_record(project_id)
        workflow = _project_workflow_settings(project_state)
        auto_apply = auto_approve and workflow["workflow_mode"] == "build"
        project, batch, applied = _stage_or_apply_workspace_batch(
            project_id,
            operations,
            auto_apply=auto_apply,
        )
        payload = {
            "status": "applied" if applied else "pending_approval",
            "project": project,
            "workspace": _workspace_info(project),
        }
        if applied:
            payload["applied_batch"] = batch
        else:
            payload["batch"] = batch
        return payload
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/models")
async def list_models():
    models = _scan_models()
    return {
        "models": models,
        "loaded_model": _model_name,
        "loaded_model_path": _model_path,
        "is_loading": _model_loading,
    }


@app.post("/api/models/load")
async def load_model(request: dict):
    global _model, _tokenizer, _model_name, _model_path, _model_loading, _model_load_start

    model_path = request.get("path") or request.get("name")
    if not model_path:
        return JSONResponse({"error": "No model path provided"}, status_code=400)

    if _model_path == model_path:
        return {"status": "already_loaded", "model": _model_name}

    _model_loading = True
    _model_load_start = time.time()
    _push_event("model_loading", {"model": request.get("name", model_path)})

    try:
        # ── Smart cleanup before loading (from AI-ArtWirks _prepare_for_engine) ──
        with PerfTimer("model_cleanup"):
            _smart_cleanup(reason=f"swapping to {request.get('name', model_path)}")

        _model_name = None
        _model_path = None

        # ── Memory headroom check before load ──
        try:
            _ensure_memory_headroom("model_load")
        except RuntimeError as mem_err:
            _model_loading = False
            _push_event("model_load_failed", {"error": str(mem_err)})
            return JSONResponse({"error": str(mem_err)}, status_code=503)

        # ── Load new model with PerfTimer ──
        with PerfTimer(f"model_load:{model_path}"):
            from mlx_lm import load
            load_kwargs: dict[str, Any] = {}
            local_model_path = Path(model_path).expanduser()
            if local_model_path.exists():
                quantization_overrides = _scan_mixed_quantization_overrides(local_model_path)
                if quantization_overrides is not None:
                    load_kwargs["model_config"] = {"quantization": quantization_overrides}
            _model, _tokenizer = load(model_path, **load_kwargs)

        _model_name = request.get("name") or model_path
        _model_path = model_path
        load_time = round(time.time() - _model_load_start, 2)
        _model_loading = False

        _push_event("model_loaded", {
            "model": _model_name,
            "load_time_seconds": load_time,
        })

        app_state = _load_app_state()
        app_state.setdefault("settings", {})
        app_state["settings"]["last_loaded_model_path"] = _model_path
        _save_app_state(app_state)

        return {
            "status": "loaded",
            "model": _model_name,
            "load_time_seconds": load_time,
        }
    except Exception as e:
        _model_loading = False
        _push_event("model_load_failed", {"error": str(e)})
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/models/unload")
async def unload_model():
    global _model, _tokenizer, _model_name, _model_path

    old_name = _model_name
    with PerfTimer("model_unload"):
        _smart_cleanup(reason=f"unloading {_model_name or 'model'}")
    _model_name = None
    _model_path = None

    app_state = _load_app_state()
    app_state.setdefault("settings", {})
    app_state["settings"]["last_loaded_model_path"] = None
    _save_app_state(app_state)

    _push_event("model_unloaded", {"model": old_name})
    return {"status": "unloaded"}


@app.post("/api/generate")
async def generate_sync(request: dict):
    """Non-streaming generation endpoint with memory guard."""
    if _model is None or _tokenizer is None:
        return JSONResponse({"error": "No model loaded"}, status_code=400)

    # ── Memory guard (from AI-ArtWirks _ensure_comfyui_headroom) ──
    try:
        _ensure_memory_headroom("generation")
    except RuntimeError as mem_err:
        return JSONResponse({"error": str(mem_err)}, status_code=503)

    prompt = request.get("prompt", "")
    max_tokens = request.get("max_tokens", 512)
    temperature = request.get("temperature", 0.7)
    top_p = request.get("top_p", 0.9)
    repetition_penalty = request.get("repetition_penalty", 1.1)
    project_id = str(request.get("project_id") or "").strip() or "default"
    project_state, _, _ = _project_record(project_id)
    workflow = _project_workflow_settings(project_state)
    workflow_mode = _normalize_workflow_mode(request.get("workflow_mode") or workflow["workflow_mode"])
    approval_mode = _normalize_approval_mode(request.get("approval_mode") or workflow["approval_mode"])
    deep_research = bool(request.get("deep_research") or workflow["deep_research"])
    agent_mode = bool(request.get("agent_mode")) or workflow_mode != "chat" or deep_research
    max_tokens = max(int(max_tokens), _workflow_min_output_tokens(workflow_mode, deep_research=deep_research))
    generation_id = (request.get("generation_id") or "").strip() or uuid.uuid4().hex

    try:
        _clear_generation_cancel(generation_id)
        messages = request.get("messages")
        workflow_prompt = _workflow_system_prompt(
            workflow_mode,
            deep_research=deep_research,
            approval_mode=approval_mode,
        )
        if isinstance(messages, list):
            messages = _merge_system_prompt(messages, workflow_prompt)
        if agent_mode:
            messages, tool_runs, pending_workspace_batch = await _resolve_agent_tools(
                messages=list(messages) if isinstance(messages, list) else [],
                prompt=prompt,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                project_id=project_id,
                workflow_mode=workflow_mode,
                deep_research=deep_research,
                approval_mode=approval_mode,
            )
        else:
            tool_runs = []
            pending_workspace_batch = None
        if messages:
            prompt = _render_prompt_from_messages(messages, prompt)
        elif workflow_prompt:
            prompt = f"{workflow_prompt}\n\n{prompt}".strip()

        from mlx_lm import stream_generate

        generation_runtime = _build_generation_runtime(
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
        )
        response_parts: list[str] = []
        with PerfTimer(f"generate:{max_tokens}tok"):
            for chunk in stream_generate(
                _model,
                _tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                **generation_runtime,
            ):
                if _is_generation_cancelled(generation_id):
                    response = "".join(response_parts)
                    return {
                        "response": response,
                        "agent_tools": tool_runs,
                        "workspace_pending_batch": pending_workspace_batch,
                        "cancelled": True,
                    }
                response_parts.append(chunk.text if hasattr(chunk, "text") else str(chunk))
        response = "".join(response_parts)
        return {
            "response": response,
            "agent_tools": tool_runs,
            "workspace_pending_batch": pending_workspace_batch,
            "cancelled": False,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        _clear_generation_cancel(generation_id)


@app.post("/api/generate/cancel")
async def cancel_generation(request: dict):
    generation_id = (request.get("generation_id") or "").strip()
    if not generation_id:
        return JSONResponse({"error": "Missing generation_id"}, status_code=400)
    _cancel_generation(generation_id)
    return {"status": "cancelling", "generation_id": generation_id}


# ---------------------------------------------------------------------------
# Prompt Enrichment API
# ---------------------------------------------------------------------------
@app.post("/api/prompts/enrich")
async def enrich_prompt(request: dict):
    """
    Lightweight prompt enrichment — suggests context-aware system prompts.
    Ported from AI-ArtWirks PromptMixin.refine_prompt().
    """
    user_prompt = request.get("prompt", "")
    system_prompt = request.get("system_prompt", "")
    return _enrich_system_prompt(user_prompt, system_prompt)


@app.post("/api/tokens/inspect")
async def inspect_tokens(request: dict):
    prompt = request.get("prompt", "")
    system_prompt = request.get("system_prompt", "")
    messages = request.get("messages") or []
    attachments = request.get("attachments") or []
    page_clips = request.get("page_clips") or []
    context_length = request.get("context_length")
    workflow_mode = _normalize_workflow_mode(request.get("workflow_mode"))
    approval_mode = _normalize_approval_mode(request.get("approval_mode"))
    deep_research = bool(request.get("deep_research"))
    workflow_prompt = _workflow_system_prompt(
        workflow_mode,
        deep_research=deep_research,
        approval_mode=approval_mode,
    )

    grounding_parts: list[str] = []
    for item in attachments:
        excerpt = (item or {}).get("text_excerpt") or ""
        name = (item or {}).get("relative_path") or (item or {}).get("name") or "attachment"
        if excerpt:
            grounding_parts.append(f"[Attachment: {name}]\n{excerpt}")
    for clip in page_clips:
        text = (clip or {}).get("text") or (clip or {}).get("selection") or ""
        title = (clip or {}).get("title") or "Page clip"
        if text:
            grounding_parts.append(f"[Page Clip: {title}]\n{text}")

    draft_body = prompt.strip()
    if grounding_parts:
        draft_body = (
            f"{draft_body}\n\n"
            "Use the following grounded context when relevant:\n\n"
            + "\n\n".join(grounding_parts)
        ).strip()

    prompt_for_count = draft_body
    if messages:
        prompt_messages = _merge_system_prompt(list(messages), workflow_prompt)
        if prompt_messages and prompt_messages[-1].get("role") == "user":
            prompt_messages[-1] = {
                **prompt_messages[-1],
                "content": draft_body or prompt_messages[-1].get("content", ""),
            }
        try:
            prompt_for_count = _tokenizer.apply_chat_template(
                prompt_messages,
                tokenize=False,
                add_generation_prompt=True,
            ) if _tokenizer is not None else json.dumps(prompt_messages)
        except Exception:
            prompt_for_count = json.dumps(prompt_messages)
    elif system_prompt or workflow_prompt:
        prompt_for_count = f"{system_prompt}\n\n{workflow_prompt}\n\n{draft_body}".strip()

    token_estimate = _estimate_tokens(prompt_for_count, _tokenizer)
    attachment_tokens = sum(
        int((item or {}).get("token_estimate") or 0)
        for item in attachments
    )
    clip_tokens = sum(
        _estimate_tokens((clip or {}).get("text") or (clip or {}).get("selection") or "")
        for clip in page_clips
    )

    if not context_length:
        model_meta = _loaded_model_meta()
        context_length = (model_meta or {}).get("context_length") or 8192

    remaining = max(int(context_length) - token_estimate, 0)
    warning = None
    if token_estimate >= int(context_length) * 0.9:
        warning = "Context is close to full. Trim grounded files or shorten the prompt."
    elif token_estimate >= int(context_length) * 0.75:
        warning = "Context usage is getting high."

    return {
        "token_estimate": token_estimate,
        "prompt_token_estimate": _estimate_tokens(prompt, _tokenizer),
        "grounding_token_estimate": attachment_tokens + clip_tokens,
        "context_length": int(context_length),
        "remaining_tokens": remaining,
        "warning": warning,
        "grounding_sources": len(attachments) + len(page_clips),
    }


@app.post("/api/attachments/extract")
async def extract_attachments(request: Request):
    form = await request.form()
    files = form.getlist("files")
    relative_paths = form.getlist("relative_paths")
    attachments: list[dict] = []
    total_bytes = 0

    for idx, upload in enumerate(files):
        data = await upload.read()
        total_bytes += len(data)
        if total_bytes > MAX_FORM_ATTACHMENT_BYTES:
            return JSONResponse(
                {"error": "Attachment batch too large. Keep uploads under 8MB per batch."},
                status_code=413,
            )
        relative_path = (
            relative_paths[idx]
            if idx < len(relative_paths) and relative_paths[idx]
            else getattr(upload, "filename", f"attachment-{idx + 1}")
        )
        attachments.append(
            _extract_attachment_record(
                filename=getattr(upload, "filename", f"attachment-{idx + 1}"),
                content_type=getattr(upload, "content_type", "") or "",
                data=data,
                relative_path=relative_path,
            )
        )

    return {"attachments": attachments}


@app.post("/api/page-assist/capture")
async def capture_page_assist(request: dict):
    title = (request.get("title") or "Untitled Page").strip() or "Untitled Page"
    url = (request.get("url") or "").strip()
    selection = _trim_text_excerpt(request.get("selection") or "", limit=6000)
    text = _trim_text_excerpt(request.get("text") or "", limit=10000)

    clip = {
        "id": uuid.uuid4().hex,
        "title": title,
        "url": url,
        "selection": selection,
        "text": text,
        "created": _utc_now(),
        "source": request.get("source") or "extension",
    }

    app_state = _load_app_state()
    clips = [clip] + list(app_state.get("page_clips", []))
    app_state["page_clips"] = clips[:MAX_PAGE_CLIPS]
    _save_app_state(app_state)

    _push_event("page_assist_clip", {
        "clip_id": clip["id"],
        "title": clip["title"],
        "url": clip["url"],
    })

    return {"status": "captured", "clip": clip}


@app.get("/api/page-assist/clips")
async def get_page_assist_clips():
    state = _load_app_state()
    return {"clips": state.get("page_clips", [])}


# ---------------------------------------------------------------------------
# Connector APIs
# ---------------------------------------------------------------------------
@app.get("/api/connectors")
async def list_connectors():
    return {"connectors": _connector_catalog()}


@app.post("/api/connectors/{provider}/search")
async def connector_search(provider: str, request: dict):
    query = (request.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "Enter a search query."}, status_code=400)

    try:
        results = await _search_connector(provider, query)
    except Exception as e:
        status_code = 404 if "Unknown connector" in str(e) else 502
        return JSONResponse({"error": str(e)}, status_code=status_code)
    return {"provider": provider, "query": query, "results": results}


@app.post("/api/connectors/{provider}/fetch")
async def connector_fetch(provider: str, request: dict):
    item_id = (request.get("id") or "").strip()
    if not item_id:
        return JSONResponse({"error": "Missing connector item id."}, status_code=400)

    try:
        return await _fetch_connector(provider, item_id)
    except Exception as e:
        status_code = 404 if "Unknown connector" in str(e) else 502
        return JSONResponse({"error": str(e)}, status_code=status_code)


# ---------------------------------------------------------------------------
# Local Browser Tool APIs
# ---------------------------------------------------------------------------
@app.get("/api/browser/health")
async def browser_health():
    try:
        return await _browser_health()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)


@app.post("/api/browser/reset")
async def browser_reset():
    try:
        return await _browser_reset()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)


@app.post("/api/browser/navigate")
async def browser_navigate(request: dict):
    url = (request.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "Missing url."}, status_code=400)
    try:
        return await _browser_navigate(url)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/browser/snapshot")
async def browser_snapshot():
    try:
        return await _browser_snapshot()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/browser/click")
async def browser_click(request: dict):
    raw_element_id = request.get("element_id")
    selector = (request.get("selector") or "").strip()
    element_id = None
    if raw_element_id not in (None, ""):
        try:
            element_id = int(raw_element_id)
        except Exception:
            return JSONResponse({"error": "element_id must be an integer."}, status_code=400)
    if element_id is None and not selector:
        return JSONResponse({"error": "Provide selector or element_id."}, status_code=400)
    try:
        return await _browser_click(element_id=element_id, selector=selector)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/browser/type")
async def browser_type(request: dict):
    raw_element_id = request.get("element_id")
    selector = (request.get("selector") or "").strip()
    text_value = str(request.get("text") or "")
    submit = bool(request.get("submit"))
    if not text_value:
        return JSONResponse({"error": "Missing text."}, status_code=400)
    element_id = None
    if raw_element_id not in (None, ""):
        try:
            element_id = int(raw_element_id)
        except Exception:
            return JSONResponse({"error": "element_id must be an integer."}, status_code=400)
    if element_id is None and not selector:
        return JSONResponse({"error": "Provide selector or element_id."}, status_code=400)
    try:
        return await _browser_type(text=text_value, element_id=element_id, selector=selector, submit=submit)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/browser/wait")
async def browser_wait(request: dict):
    text_value = (request.get("text") or "").strip()
    seconds = request.get("seconds", 1)
    try:
        return await _browser_wait(text=text_value, seconds=float(seconds))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---------------------------------------------------------------------------
# HuggingFace Model Pull — ported from AI-ArtWirks runtime/models.py
# ---------------------------------------------------------------------------
@app.post("/api/models/pull")
async def pull_model(request: dict):
    """
    Start a background HuggingFace model download.
    Ported from AI-ArtWirks create_model_pull().
    """
    repo_id = request.get("repo_id", "").strip()
    if not repo_id or "/" not in repo_id:
        return JSONResponse(
            {"error": "Provide a valid HF repo_id like mlx-community/Qwen2-0.5B-Instruct-4bit"},
            status_code=400,
        )

    # Check if already pulling
    if repo_id in _active_pulls and _active_pulls[repo_id].get("status") == "running":
        return JSONResponse(
            {"error": f"Already pulling {repo_id}"},
            status_code=409,
        )

    pull_id = f"pull_{int(time.time())}"
    _active_pulls[repo_id] = {
        "id": pull_id,
        "repo_id": repo_id,
        "status": "queued",
        "message": "Starting download…",
    }

    # Background download thread (from AI-ArtWirks _run_model_pull)
    def _run_pull():
        _active_pulls[repo_id]["status"] = "running"
        _push_event("model_pull_started", {"repo_id": repo_id})

        try:
            from huggingface_hub import snapshot_download
            target_dir = Path(MODEL_DIRS[0]) / repo_id.replace("/", "--")
            target_dir.mkdir(parents=True, exist_ok=True)

            with PerfTimer(f"model_pull:{repo_id}"):
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=str(target_dir),
                )

            _active_pulls[repo_id]["status"] = "completed"
            _active_pulls[repo_id]["message"] = f"Downloaded to {target_dir}"
            _push_event("model_pull_completed", {
                "repo_id": repo_id,
                "local_dir": str(target_dir),
            })
        except Exception as e:
            _active_pulls[repo_id]["status"] = "failed"
            _active_pulls[repo_id]["message"] = str(e)
            _push_event("model_pull_failed", {
                "repo_id": repo_id,
                "error": str(e),
            })

    thread = threading.Thread(target=_run_pull, daemon=True, name=f"pull-{repo_id}")
    thread.start()

    return {"id": pull_id, "repo_id": repo_id, "status": "queued"}


@app.get("/api/models/pulls")
async def list_pulls():
    return {"pulls": list(_active_pulls.values())}


# ---------------------------------------------------------------------------
# Server-Sent Events — ported from AI-ArtWirks server.py
# ---------------------------------------------------------------------------
@app.get("/api/events")
async def sse_events():
    """
    Server-Sent Events stream for real-time push updates.
    Ported from AI-ArtWirks RuntimeHandler._handle_sse().
    
    Replaces frontend polling with push:
    - model_loaded / model_unloaded / model_loading
    - memory_warning (critical/warning levels)
    - generation_done
    - model_pull_started / model_pull_completed / model_pull_failed
    """
    async def event_generator():
        while True:
            # Check for events
            try:
                event = _event_queue.get_nowait()
                data = json.dumps(event)
                yield f"data: {data}\n\n"
            except queue.Empty:
                # Heartbeat every 5s (keeps connection alive)
                yield ": heartbeat\n\n"
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Web Search API (Bing/Google Custom Search placeholder)
# ---------------------------------------------------------------------------
@app.get("/api/search")
async def web_search(query: str):
    query = (query or "").strip()
    if not query:
        return {"results": [], "error": "Enter a search query."}
    try:
        results = await _web_search(query)
    except Exception as e:
        return {"results": [], "error": str(e)}
    return {
        "results": [
            {
                "name": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("description"),
            }
            for item in results
        ]
    }


# ---------------------------------------------------------------------------
# Preset Profiles
# ---------------------------------------------------------------------------
BUILTIN_PRESETS = {
    "balanced": {
        "name": "Balanced",
        "icon": "⚖️",
        "group": "General",
        "description": "General purpose — good for most tasks",
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 512,
        "repetition_penalty": 1.1,
    },
    "coding": {
        "name": "Coding",
        "icon": "🧠",
        "group": "Build",
        "description": "Low temperature for precise, deterministic code",
        "temperature": 0.2,
        "top_p": 0.85,
        "max_tokens": 2048,
        "repetition_penalty": 1.05,
    },
    "creative": {
        "name": "Creative",
        "icon": "✍️",
        "group": "Write",
        "description": "Higher temperature for imaginative writing",
        "temperature": 1.1,
        "top_p": 0.95,
        "max_tokens": 1024,
        "repetition_penalty": 1.15,
    },
    "precise": {
        "name": "Precise",
        "icon": "🎯",
        "group": "General",
        "description": "Very low temperature for factual Q&A",
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": 512,
        "repetition_penalty": 1.0,
    },
    "debug": {
        "name": "Debug",
        "icon": "🪲",
        "group": "Build",
        "description": "Tighter sampling with room for longer stack-trace reasoning",
        "temperature": 0.15,
        "top_p": 0.82,
        "max_tokens": 1536,
        "repetition_penalty": 1.02,
    },
    "long_context": {
        "name": "Long Context",
        "icon": "📚",
        "group": "Research",
        "description": "For grounded answers across larger files and page clips",
        "temperature": 0.35,
        "top_p": 0.88,
        "max_tokens": 3072,
        "repetition_penalty": 1.04,
    },
    "extract": {
        "name": "Extract",
        "icon": "🧾",
        "group": "Research",
        "description": "Structured extraction from documents and attached files",
        "temperature": 0.05,
        "top_p": 0.75,
        "max_tokens": 768,
        "repetition_penalty": 1.0,
    },
    "brainstorm": {
        "name": "Brainstorm",
        "icon": "💡",
        "group": "Write",
        "description": "Broader idea generation with higher variability",
        "temperature": 1.25,
        "top_p": 0.98,
        "max_tokens": 1408,
        "repetition_penalty": 1.08,
    },
    "low_latency": {
        "name": "Low Latency",
        "icon": "⚡",
        "group": "General",
        "description": "Short fast replies for local chat loops",
        "temperature": 0.4,
        "top_p": 0.85,
        "max_tokens": 256,
        "repetition_penalty": 1.0,
    },
    "review": {
        "name": "Review",
        "icon": "🔎",
        "group": "Build",
        "description": "Careful code and document review with moderate length",
        "temperature": 0.18,
        "top_p": 0.82,
        "max_tokens": 1792,
        "repetition_penalty": 1.05,
    },
}


@app.get("/api/presets")
async def get_presets():
    return {"presets": BUILTIN_PRESETS}


# ---------------------------------------------------------------------------
# WebSocket for streaming generation — with memory guard
# ---------------------------------------------------------------------------
@app.websocket("/ws/generate")
async def ws_generate(websocket: WebSocket):
    global _generation_stats
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if _model is None or _tokenizer is None:
                await websocket.send_json({"error": "No model loaded"})
                continue

            # ── Memory guard before generation ──
            try:
                _ensure_memory_headroom("ws_generation")
            except RuntimeError as mem_err:
                await websocket.send_json({"error": str(mem_err)})
                continue

            prompt = data.get("prompt", "")
            max_tokens = data.get("max_tokens", 512)
            temperature = data.get("temperature", 0.7)
            top_p = data.get("top_p", 0.9)
            repetition_penalty = data.get("repetition_penalty", 1.1)
            project_id = str(data.get("project_id") or "").strip() or "default"
            project_state, _, _ = _project_record(project_id)
            workflow = _project_workflow_settings(project_state)
            workflow_mode = _normalize_workflow_mode(data.get("workflow_mode") or workflow["workflow_mode"])
            approval_mode = _normalize_approval_mode(data.get("approval_mode") or workflow["approval_mode"])
            deep_research = bool(data.get("deep_research") or workflow["deep_research"])
            agent_mode = bool(data.get("agent_mode")) or workflow_mode != "chat" or deep_research
            max_tokens = max(int(max_tokens), _workflow_min_output_tokens(workflow_mode, deep_research=deep_research))
            generation_id = (data.get("generation_id") or "").strip() or uuid.uuid4().hex

            messages = data.get("messages")

            try:
                _clear_generation_cancel(generation_id)
                from mlx_lm import stream_generate
                workflow_prompt = _workflow_system_prompt(
                    workflow_mode,
                    deep_research=deep_research,
                    approval_mode=approval_mode,
                )
                if isinstance(messages, list):
                    messages = _merge_system_prompt(messages, workflow_prompt)

                if agent_mode:
                    messages, tool_runs, pending_workspace_batch = await _resolve_agent_tools(
                        messages=list(messages) if isinstance(messages, list) else [],
                        prompt=prompt,
                        temperature=temperature,
                        top_p=top_p,
                        repetition_penalty=repetition_penalty,
                        project_id=project_id,
                        workflow_mode=workflow_mode,
                        deep_research=deep_research,
                        approval_mode=approval_mode,
                        status_callback=websocket.send_json,
                    )
                    if tool_runs:
                        await websocket.send_json({
                            "type": "agent_status",
                            "message": f"Agent resolved {len(tool_runs)} tool step{'s' if len(tool_runs) != 1 else ''}. Generating final answer…",
                        })
                else:
                    tool_runs = []
                    pending_workspace_batch = None
                if messages:
                    prompt = _render_prompt_from_messages(messages, prompt)
                elif workflow_prompt:
                    prompt = f"{workflow_prompt}\n\n{prompt}".strip()

                generation_runtime = _build_generation_runtime(
                    temperature=temperature,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                )
                token_count = 0
                start_time = time.time()
                full_response = ""
                first_token_time = None
                cancelled = _is_generation_cancelled(generation_id)

                if not cancelled:
                    for chunk in stream_generate(
                        _model,
                        _tokenizer,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        **generation_runtime,
                    ):
                        if _is_generation_cancelled(generation_id):
                            cancelled = True
                            break
                        text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                        full_response += text
                        token_count += 1
                        elapsed = time.time() - start_time
                        tps = token_count / elapsed if elapsed > 0 else 0

                        if first_token_time is None:
                            first_token_time = elapsed

                        await websocket.send_json({
                            "type": "token",
                            "text": text,
                            "tokens": token_count,
                            "tps": round(tps, 1),
                            "latency_ms": round(first_token_time * 1000, 0) if first_token_time else 0,
                        })
                        # Yield control to allow WebSocket to flush
                        await asyncio.sleep(0)

                elapsed = time.time() - start_time
                final_tps = round(token_count / elapsed if elapsed > 0 else 0, 1)

                # Update global stats
                _generation_stats = {
                    "last_tps": final_tps,
                    "last_latency": round(first_token_time * 1000, 0) if first_token_time else 0,
                    "last_tokens": token_count,
                    "total_generated": _generation_stats["total_generated"] + token_count,
                }

                if cancelled:
                    await websocket.send_json({
                        "type": "cancelled",
                        "total_tokens": token_count,
                    })
                else:
                    await websocket.send_json({
                        "type": "done",
                        "total_tokens": token_count,
                        "elapsed_seconds": round(elapsed, 2),
                        "tokens_per_second": final_tps,
                        "first_token_ms": round(first_token_time * 1000, 0) if first_token_time else 0,
                        "workspace_pending_batch": pending_workspace_batch,
                    })

                    _push_event("generation_done", {
                        "tokens": token_count,
                        "tps": final_tps,
                        "model": _model_name,
                    })

            except Exception as e:
                await websocket.send_json({"type": "error", "error": str(e)})
                _push_event("generation_error", {"error": str(e)})
            finally:
                _clear_generation_cancel(generation_id)

    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Static files & SPA
# ---------------------------------------------------------------------------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "MLX Studio API is running. No frontend found."}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"\n🧠 MLX Studio v3 starting on http://localhost:{PORT}")
    print(f"   ⚡ Memory guard: warn@{MEMORY_PRESSURE_WARN}% · block@{MEMORY_PRESSURE_BLOCK}%")
    print(f"   📡 SSE events: /api/events")
    print(f"   🧪 Prompt enrichment: /api/prompts/enrich")
    print(f"   📦 Model pull: POST /api/models/pull\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
