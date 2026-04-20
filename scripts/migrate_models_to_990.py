#!/usr/bin/env python3
from pathlib import Path
import shutil

DEST_ROOT = Path('/Volumes/Wirks990/ai/models')
LORA_DIR = DEST_ROOT / 'loras'

FILES = [
    '/Users/bluewirks.max/Documents/Ai-ArtWirks/wikeeyang--Flux2-Klein-9B-True-V2/Flux2-Klein-9B-True-v2-bf16.safetensors',
    '/Users/bluewirks.max/Downloads/unstableEvolution_GGUFQ8012GB.gguf',
    '/Volumes/BlueWirksSSD/Archive/Models/Local-AI-Models/llama-3.2-11B-vision_Q8_0.gguf',
    '/Volumes/BlueWirksSSD/Archive/Models/2026-04-ai-second-pass/Joeavaib/DeepSeek-Coder-V2-LiteGGUF_IQ4_XS/deepseek-v2-lite-IQ4_XS.gguf',
    '/Users/bluewirks.max/Documents/Ai-ArtWirks/wikeeyang--Flux2-Klein-9B-True-V2/Flux2-Klein-9B-True-v2-fp8mixed.safetensors',
    '/Volumes/BlueWirksSSD/Archive/Models/Local-AI-Models/llama-3.2-11B-vision_f16_projector.gguf',
    '/Users/bluewirks.max/Documents/ComfyUI/custom_nodes/comfyui-kjnodes/intrinsic_loras/intrinsic_lora_sd15_shading.safetensors',
    '/Users/bluewirks.max/Documents/ComfyUI/custom_nodes/comfyui-kjnodes/intrinsic_loras/intrinsic_lora_sd15_normal.safetensors',
    '/Users/bluewirks.max/Documents/ComfyUI/custom_nodes/comfyui-kjnodes/intrinsic_loras/intrinsic_lora_sd15_depth.safetensors',
    '/Users/bluewirks.max/Documents/ComfyUI/custom_nodes/comfyui-kjnodes/intrinsic_loras/intrinsic_lora_sd15_albedo.safetensors',
]


def main() -> None:
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    LORA_DIR.mkdir(parents=True, exist_ok=True)

    moved = []
    skipped = []

    for raw in FILES:
        src = Path(raw)
        if not src.exists() or not src.is_file():
            skipped.append((str(src), 'missing'))
            continue

        name_lower = src.name.lower()
        is_lora = ('lora' in name_lower) or ('lycoris' in name_lower)

        if src.suffix.lower() == '.gguf':
            dest = DEST_ROOT / src.name
        elif is_lora:
            dest = LORA_DIR / src.name
        else:
            parent = src.parent.name or 'imported-model'
            dest_dir = DEST_ROOT / parent
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name

        if dest.exists():
            if dest.stat().st_size == src.stat().st_size:
                src.unlink()
                moved.append((str(src), str(dest), 'dedup-delete-source'))
                continue

            stem = dest.stem
            suffix = dest.suffix
            index = 2
            while True:
                candidate = dest.with_name(f'{stem}__{index}{suffix}')
                if not candidate.exists():
                    dest = candidate
                    break
                index += 1

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        moved.append((str(src), str(dest), 'moved'))

    print(f'MOVED_COUNT={len(moved)}')
    print(f'SKIPPED_COUNT={len(skipped)}')
    for src, dest, kind in moved:
        print(f'{kind}\t{src}\t=>\t{dest}')
    for src, reason in skipped:
        print(f'skipped\t{src}\t{reason}')


if __name__ == '__main__':
    main()
