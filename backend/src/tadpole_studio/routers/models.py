import asyncio
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from loguru import logger
from pydantic import BaseModel

_SAFE_MODEL_NAME = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

# Chat LLM models that can be downloaded for the AI DJ feature
_CHAT_LLM_REGISTRY: dict[str, str] = {
    "Qwen2.5-1.5B-Instruct-4bit": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "Qwen3-0.6B-4bit": "mlx-community/Qwen3-0.6B-4bit",
}

_CHAT_LLM_SIZES: dict[str, int] = {
    "Qwen2.5-1.5B-Instruct-4bit": 869,
    "Qwen3-0.6B-4bit": 335,
}

_CHAT_LLM_DESCRIPTIONS: dict[str, str] = {
    "Qwen2.5-1.5B-Instruct-4bit": "Recommended. Strong instruction following and JSON output. 869 MB.",
    "Qwen3-0.6B-4bit": "Ultra-lightweight alternative. 335 MB.",
}

from tadpole_studio.config import settings
from tadpole_studio.models.common import (
    AvailableModel,
    AvailableModelsResponse,
    DownloadModelRequest,
)
from tadpole_studio.models.training import SwitchModelRequest, GpuStatsResponse
from tadpole_studio.services.generation import generation_service
from tadpole_studio.backends.base import BackendType

router = APIRouter(tags=["models"])


class ModelInfo(BaseModel):
    name: str
    model_type: str
    is_active: bool = False


class ModelsResponse(BaseModel):
    dit_models: list[ModelInfo]
    lm_models: list[ModelInfo]
    chat_llm_models: list[ModelInfo] = []
    heartmula_models: list[ModelInfo] = []


def _scan_checkpoints(active_chat_llm: str = "") -> ModelsResponse:
    checkpoints_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "checkpoints"
    chat_llm_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "chat-llm"
    heartmula_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "heartmula"
    dit_models: list[ModelInfo] = []
    lm_models: list[ModelInfo] = []
    chat_llm_models: list[ModelInfo] = []
    heartmula_models: list[ModelInfo] = []

    if checkpoints_dir.exists():
        active_dit = generation_service.active_dit_model
        active_lm = generation_service.active_lm_model

        for entry in sorted(checkpoints_dir.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith("acestep-v15-") or name.startswith("acestep-v1-"):
                dit_models.append(ModelInfo(
                    name=name,
                    model_type="dit",
                    is_active=(name == active_dit),
                ))
            elif name.startswith("acestep-5Hz-lm-"):
                lm_models.append(ModelInfo(
                    name=name,
                    model_type="lm",
                    is_active=(name == active_lm),
                ))

    # Scan chat LLM models
    if chat_llm_dir.exists():
        for entry in sorted(chat_llm_dir.iterdir()):
            if entry.is_dir() and (entry / "config.json").exists():
                chat_llm_models.append(ModelInfo(
                    name=entry.name,
                    model_type="chat_llm",
                    is_active=(entry.name == active_chat_llm),
                ))

    # Scan HeartMuLa models
    if heartmula_dir.exists():
        for name in _HEARTMULA_REGISTRY:
            model_dir = heartmula_dir / name
            if model_dir.exists() and (model_dir / "config.json").exists():
                heartmula_models.append(ModelInfo(
                    name=name,
                    model_type="heartmula",
                    is_active=False,
                ))

    return ModelsResponse(
        dit_models=dit_models,
        lm_models=lm_models,
        chat_llm_models=chat_llm_models,
        heartmula_models=heartmula_models,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    from tadpole_studio.db.connection import get_db

    active_chat_llm = "Qwen2.5-1.5B-Instruct-4bit"
    try:
        db = await get_db()
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'dj_model'")
        row = await cursor.fetchone()
        if row:
            active_chat_llm = row["value"]
    except Exception:
        pass

    return _scan_checkpoints(active_chat_llm=active_chat_llm)


# Approximate download sizes in MB for each submodel (from HuggingFace repo)
_MODEL_SIZES: dict[str, int] = {
    "acestep-5Hz-lm-0.6B": 1_373,
    "acestep-5Hz-lm-4B": 8_426,
    "acestep-v15-sft": 4_792,
    "acestep-v15-base": 4_792,
    "acestep-v15-turbo-shift3": 4_792,
    "acestep-v15-turbo-shift1": 4_792,
    "acestep-v15-turbo-continuous": 4_792,
}

# Model descriptions for available models list
_MODEL_DESCRIPTIONS: dict[str, str] = {
    "acestep-5Hz-lm-0.6B": "Based on Qwen3-0.6B. Lightweight (6-8 GB VRAM).",
    "acestep-5Hz-lm-4B": "Based on Qwen3-4B. Best quality (24 GB+ VRAM).",
    "acestep-v15-sft": "SFT-tuned DiT. 50 steps, CFG-guided.",
    "acestep-v15-base": "Base DiT model. 50 steps, CFG-guided.",
    "acestep-v15-turbo-shift3": "Turbo DiT variant with shift=3.",
    "acestep-v15-turbo-shift1": "Turbo DiT variant with shift=1.",
    "acestep-v15-turbo-continuous": "Turbo DiT with continuous noise schedule.",
}


def _scan_dir_bytes(path: Path) -> int:
    """Sum all file sizes recursively in a directory."""
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _hf_cache_blob_dir(repo_id: str) -> Path:
    """Return the HuggingFace cache blobs directory for a repo."""
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    # repo_id like "ACE-Step/model-name" → "models--ACE-Step--model-name"
    folder_name = "models--" + repo_id.replace("/", "--")
    return cache_root / folder_name / "blobs"


def _download_progress_fs(repo_id: str, model_dir: Path, expected_mb: int) -> float:
    """Compute download progress by scanning filesystem bytes.

    Checks both the HF cache (for .incomplete partial downloads) and the
    model target directory (for completed files).
    """
    if expected_mb <= 0:
        return 0.0
    expected_bytes = expected_mb * 1_000_000
    # Scan HF cache blobs (includes .incomplete partial files)
    total = _scan_dir_bytes(_hf_cache_blob_dir(repo_id))
    # Also scan model target dir (completed files copied/linked there)
    if model_dir.exists():
        total += _scan_dir_bytes(model_dir)
    return min(total / expected_bytes, 0.99)


@router.get("/models/available", response_model=AvailableModelsResponse)
async def list_available_models() -> AvailableModelsResponse:
    """List all models from SUBMODEL_REGISTRY and chat LLM registry with install status."""
    from acestep.model_downloader import SUBMODEL_REGISTRY

    checkpoints_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "checkpoints"
    chat_llm_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "chat-llm"
    result: list[AvailableModel] = []

    for name, repo_id in SUBMODEL_REGISTRY.items():
        model_type = "lm" if "lm" in name.lower() else "dit"
        installed = (checkpoints_dir / name).exists()
        downloading = generation_service.model_download_status.get(name) == "downloading"
        progress = 0.0
        if downloading:
            progress = _download_progress_fs(
                repo_id, checkpoints_dir / name, _MODEL_SIZES.get(name, 0),
            )
        result.append(AvailableModel(
            name=name,
            model_type=model_type,
            repo_id=repo_id,
            installed=installed,
            description=_MODEL_DESCRIPTIONS.get(name, ""),
            downloading=downloading,
            download_progress=progress,
            size_mb=_MODEL_SIZES.get(name, 0),
        ))

    # Append HeartMuLa models
    heartmula_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "heartmula"
    for name, repo_id in _HEARTMULA_REGISTRY.items():
        installed = (heartmula_dir / name).exists()
        downloading = generation_service.model_download_status.get(name) == "downloading"
        progress = 0.0
        if downloading:
            progress = _download_progress_fs(
                repo_id, heartmula_dir / name, _HEARTMULA_SIZES.get(name, 0),
            )
        result.append(AvailableModel(
            name=name,
            model_type="heartmula",
            repo_id=repo_id,
            installed=installed,
            description=_HEARTMULA_DESCRIPTIONS.get(name, ""),
            downloading=downloading,
            download_progress=progress,
            size_mb=_HEARTMULA_SIZES.get(name, 0),
        ))

    # Append chat LLM models
    for name, repo_id in _CHAT_LLM_REGISTRY.items():
        installed = (chat_llm_dir / name).exists() and (chat_llm_dir / name / "config.json").exists()
        downloading = generation_service.model_download_status.get(name) == "downloading"
        progress = 0.0
        if downloading:
            progress = _download_progress_fs(
                repo_id, chat_llm_dir / name, _CHAT_LLM_SIZES.get(name, 0),
            )
        result.append(AvailableModel(
            name=name,
            model_type="chat_llm",
            repo_id=repo_id,
            installed=installed,
            description=_CHAT_LLM_DESCRIPTIONS.get(name, ""),
            downloading=downloading,
            download_progress=progress,
            size_mb=_CHAT_LLM_SIZES.get(name, 0),
        ))

    return AvailableModelsResponse(models=result)


@router.post("/models/download")
async def download_model(request: DownloadModelRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Trigger download of a model from SUBMODEL_REGISTRY or chat LLM registry."""
    from acestep.model_downloader import SUBMODEL_REGISTRY

    model_name = request.model_name
    if not _SAFE_MODEL_NAME.match(model_name):
        raise HTTPException(status_code=400, detail="Invalid model name")

    is_chat_llm = model_name in _CHAT_LLM_REGISTRY
    if is_chat_llm and sys.platform != "darwin":
        raise HTTPException(
            status_code=400,
            detail="Built-in chat models require macOS (Apple Silicon). Use Ollama instead.",
        )
    is_heartmula = model_name in _HEARTMULA_REGISTRY
    if not is_chat_llm and not is_heartmula and model_name not in SUBMODEL_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

    current = generation_service.model_download_status.get(model_name)
    if current == "downloading":
        return {"status": "already_downloading"}

    generation_service.model_download_status[model_name] = "downloading"

    if is_heartmula:
        def _do_download() -> None:
            try:
                from huggingface_hub import snapshot_download
                repo_id = _HEARTMULA_REGISTRY[model_name]
                local_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "heartmula" / model_name
                snapshot_download(repo_id=repo_id, local_dir=str(local_dir))
                generation_service.model_download_status[model_name] = "done"
                logger.info(f"HeartMuLa model download complete: {model_name}")
            except Exception as e:
                generation_service.model_download_status[model_name] = f"error:{e}"
                logger.exception(f"HeartMuLa model download failed: {model_name}")
    elif is_chat_llm:
        def _do_download() -> None:
            try:
                from huggingface_hub import snapshot_download
                repo_id = _CHAT_LLM_REGISTRY[model_name]
                local_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "chat-llm" / model_name
                snapshot_download(repo_id=repo_id, local_dir=str(local_dir))
                generation_service.model_download_status[model_name] = "done"
                logger.info(f"Chat LLM download complete: {model_name}")
            except Exception as e:
                generation_service.model_download_status[model_name] = f"error:{e}"
                logger.exception(f"Chat LLM download failed: {model_name}")
    else:
        def _do_download() -> None:
            try:
                from acestep.model_downloader import download_submodel
                checkpoint_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "checkpoints"
                success, msg = download_submodel(model_name, checkpoint_dir)
                generation_service.model_download_status[model_name] = "done" if success else f"error:{msg}"
                logger.info(f"Model download {model_name}: {msg}")
            except Exception as e:
                generation_service.model_download_status[model_name] = f"error:{e}"
                logger.exception(f"Model download failed: {model_name}")

    async def _run_download() -> None:
        await asyncio.to_thread(_do_download)

    background_tasks.add_task(_run_download)
    return {"status": "started"}


@router.get("/models/download-status")
async def get_download_status() -> dict[str, str]:
    """Return current download status for all models being downloaded."""
    return generation_service.model_download_status


@router.post("/models/switch-dit")
async def switch_dit_model(request: SwitchModelRequest) -> dict[str, str]:
    from tadpole_studio.db.connection import get_db

    status, ok = await generation_service.initialize_dit(
        config_path=request.model_name,
        device=generation_service.device or settings.DEFAULT_DEVICE,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=status)

    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("dit_model", request.model_name),
    )
    await db.commit()

    return {"message": f"DiT model switched to {request.model_name}"}


@router.post("/models/switch-lm")
async def switch_lm_model(request: SwitchModelRequest) -> dict[str, str]:
    from tadpole_studio.db.connection import get_db

    backend = request.backend or settings.DEFAULT_LM_BACKEND
    status, ok = await generation_service.initialize_lm(
        lm_model_path=request.model_name,
        backend=backend,
        device=generation_service.device or settings.DEFAULT_DEVICE,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=status)

    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("lm_model", request.model_name),
    )
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("lm_backend", backend),
    )
    await db.commit()

    return {"message": f"LM model switched to {request.model_name}"}


class SwitchBackendRequest(BaseModel):
    backend: str


async def _build_init_kwargs(bt: BackendType, db) -> dict:
    """Build initialization kwargs for a backend from saved settings."""
    cursor = await db.execute("SELECT key, value FROM settings")
    rows = await cursor.fetchall()
    saved = {row["key"]: row["value"] for row in rows}

    if bt == BackendType.ACE_STEP:
        lm_backend = saved.get("lm_backend", settings.DEFAULT_LM_BACKEND)
        if lm_backend == "mlx" and sys.platform != "darwin":
            lm_backend = "nano-vllm"
        return {
            "config_path": saved.get("dit_model", settings.DEFAULT_DIT_MODEL),
            "device": saved.get("device", settings.DEFAULT_DEVICE),
            "lm_model_path": saved.get("lm_model", settings.DEFAULT_LM_MODEL),
            "lm_backend": lm_backend,
        }
    elif bt == BackendType.HEARTMULA:
        heartmula_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "heartmula"
        has_models = (
            (heartmula_dir / "HeartMuLa-oss-3B" / "config.json").exists()
            and (heartmula_dir / "HeartCodec-oss" / "config.json").exists()
        )
        if not has_models:
            return {}
        model_path = str(heartmula_dir)
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            ("heartmula_model_path", model_path),
        )
        await db.commit()
        return {
            "model_path": model_path,
            "version": saved.get("heartmula_version", "3B"),
            "lazy_load": saved.get("heartmula_lazy_load", "false") == "true",
            "device": saved.get("device", settings.HEARTMULA_DEVICE) or "auto",
        }
    return {}


@router.post("/models/switch-backend")
async def switch_backend(request: SwitchBackendRequest) -> dict[str, str]:
    from tadpole_studio.db.connection import get_db

    try:
        bt = BackendType(request.backend)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown backend: {request.backend}")

    backend = generation_service.get_backend(bt)
    if backend is None:
        raise HTTPException(status_code=400, detail=f"Backend '{request.backend}' not registered")

    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        ("active_backend", request.backend),
    )
    await db.commit()

    # If already the active backend and ready, nothing to do
    if generation_service.active_backend_type == bt and backend.is_ready:
        return {"message": f"{request.backend} already active"}

    init_kwargs = await _build_init_kwargs(bt, db)

    if not init_kwargs:
        generation_service.set_active_backend(bt)
        return {"message": f"Switched to {request.backend} (models not downloaded yet)"}

    # Always go through the full switch flow so the old backend is
    # unloaded (frees memory) and the new one is properly initialized.
    async def _do_switch():
        status, ok = await generation_service.switch_backend(bt, init_kwargs)
        if ok:
            logger.info(f"Backend switch complete: {status}")
        else:
            logger.warning(f"Backend switch failed: {status}")

    asyncio.create_task(_do_switch())
    return {"message": f"Switching to {request.backend}..."}


# HeartMuLa model registry
# Folder names must match what heartlib expects:
#   {pretrained_path}/HeartMuLa-oss-{version}  and  {pretrained_path}/HeartCodec-oss
_HEARTMULA_REGISTRY: dict[str, str] = {
    "HeartMuLa-oss-3B": "HeartMuLa/HeartMuLa-oss-3B",
    "HeartCodec-oss": "HeartMuLa/HeartCodec-oss-20260123",
}

_HEARTMULA_SIZES: dict[str, int] = {
    "HeartMuLa-oss-3B": 15_800,
    "HeartCodec-oss": 6_640,
}

_HEARTMULA_DESCRIPTIONS: dict[str, str] = {
    "HeartMuLa-oss-3B": "3B parameter music generation model with superior lyrics controllability. ~15.8 GB.",
    "HeartCodec-oss": "Audio codec for HeartMuLa. Required for generation. ~6.6 GB.",
}


@router.get("/models/gpu-stats", response_model=GpuStatsResponse)
async def get_gpu_stats() -> GpuStatsResponse:
    device = generation_service.device or "unknown"

    try:
        import torch

        if torch.cuda.is_available():
            vram_used = torch.cuda.memory_reserved() / (1024 * 1024)
            vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
            return GpuStatsResponse(
                device=device,
                vram_used_mb=round(vram_used, 1),
                vram_total_mb=round(vram_total, 1),
                vram_percent=round(vram_used / vram_total * 100, 1) if vram_total > 0 else None,
            )
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            allocated = 0.0
            if hasattr(torch.mps, "current_allocated_memory"):
                allocated = torch.mps.current_allocated_memory() / (1024 * 1024)
            elif hasattr(torch.mps, "driver_allocated_size"):
                allocated = torch.mps.driver_allocated_size() / (1024 * 1024)
            return GpuStatsResponse(
                device=device,
                vram_used_mb=round(allocated, 1),
            )
    except Exception as e:
        logger.warning(f"Failed to read GPU stats: {e}")

    return GpuStatsResponse(device=device)
