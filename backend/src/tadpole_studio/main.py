import asyncio
import os
import sys
import uuid as _uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from tadpole_studio.config import settings
from tadpole_studio.db.connection import init_db, close_db
from tadpole_studio.services.generation import generation_service
from tadpole_studio.routers.health import router as health_router
from tadpole_studio.routers.generation import router as generation_router, format_router, ws_router
from tadpole_studio.routers.songs import router as songs_router
from tadpole_studio.routers.models import router as models_router
from tadpole_studio.routers.uploads import router as uploads_router
from tadpole_studio.routers.history import router as history_router
from tadpole_studio.routers.playlists import router as playlists_router
from tadpole_studio.routers.lora import router as lora_router
from tadpole_studio.routers.training import router as training_router, ws_router as training_ws_router
from tadpole_studio.routers.radio import router as radio_router
from tadpole_studio.routers.dj import router as dj_router
from tadpole_studio.routers.themes import router as themes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Tadpole Studio starting up...")
    settings.ensure_dirs()
    await init_db()
    logger.info("Database initialized")

    # Mark any stale running/pending history entries as failed (e.g. from a crash or restart)
    from tadpole_studio.db.connection import get_db
    db = await get_db()
    await db.execute(
        "UPDATE generation_history SET status = 'failed', error_message = 'Server restarted' "
        "WHERE status IN ('running', 'pending')"
    )
    await db.commit()

    # Load saved settings for model init
    cursor = await db.execute("SELECT key, value FROM settings")
    rows = await cursor.fetchall()
    saved = {row["key"]: row["value"] for row in rows}

    # Seed radio presets
    from tadpole_studio.db.schema import RADIO_PRESETS
    for preset in RADIO_PRESETS:
        cursor = await db.execute(
            "SELECT id FROM radio_stations WHERE name = ? AND is_preset = 1",
            (preset["name"],),
        )
        if await cursor.fetchone() is None:
            preset_id = str(_uuid.uuid4())
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """INSERT INTO radio_stations (
                    id, name, description, is_preset, caption_template,
                    genre, mood, instrumental, vocal_language, bpm_min, bpm_max,
                    duration_min, duration_max, advanced_params_json, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    preset_id,
                    preset["name"],
                    preset["description"],
                    preset.get("caption_template", ""),
                    preset.get("genre", ""),
                    preset.get("mood", ""),
                    1 if preset.get("instrumental", True) else 0,
                    preset.get("vocal_language", "unknown"),
                    preset.get("bpm_min"),
                    preset.get("bpm_max"),
                    preset.get("duration_min", 30.0),
                    preset.get("duration_max", 120.0),
                    preset.get("advanced_params_json", "{}"),
                    now_str,
                    now_str,
                ),
            )
    await db.commit()
    logger.info("Radio presets seeded")

    # Restore stored API keys for cloud LLM providers
    from tadpole_studio.services.llm_provider import get_provider
    for key_name in ("openai_api_key", "anthropic_api_key"):
        if key_name in saved:
            provider_name = key_name.replace("_api_key", "")
            provider = get_provider(provider_name)
            if provider and hasattr(provider, "set_api_key"):
                provider.set_api_key(saved[key_name])
                logger.info(f"Restored {provider_name} API key from database")

    # Restore GPU throttle settings from DB
    from tadpole_studio.ace_handler import set_vae_throttle, set_dit_throttle, set_throttle_radio_only
    set_vae_throttle(
        int(saved.get("vae_chunk_size", "256")),
        int(saved.get("vae_sleep_ms", "100")),
    )
    set_dit_throttle(int(saved.get("dit_sleep_ms", "100")))
    set_throttle_radio_only(saved.get("throttle_radio_only", "false") == "true")
    logger.info("GPU throttle settings restored from database")

    # Register backends
    from tadpole_studio.backends.ace_step_backend import AceStepBackend
    from tadpole_studio.backends.heartmula_backend import HeartMuLaBackend
    from tadpole_studio.backends.base import BackendType

    ace_backend = AceStepBackend()
    heartmula_backend = HeartMuLaBackend()
    generation_service.register_backend(ace_backend)
    generation_service.register_backend(heartmula_backend)
    logger.info("Music generation backends registered: ace-step, heartmula")

    # Restore active backend from saved settings
    active_backend_str = saved.get("active_backend", "ace-step")
    try:
        generation_service.set_active_backend(BackendType(active_backend_str))
    except ValueError:
        generation_service.set_active_backend(BackendType.ACE_STEP)
    logger.info(f"Active backend: {generation_service.active_backend_type.value}")

    # Initialize ONLY the active backend (one backend at a time to avoid GPU conflicts)
    async def _init_active():
        active_type = generation_service.active_backend_type
        if active_type == BackendType.ACE_STEP:
            dit_model = saved.get("dit_model", settings.DEFAULT_DIT_MODEL)
            lm_model = saved.get("lm_model", settings.DEFAULT_LM_MODEL)
            lm_backend = saved.get("lm_backend", settings.DEFAULT_LM_BACKEND)
            if lm_backend == "mlx" and sys.platform != "darwin":
                lm_backend = "nano-vllm"
                logger.info("Overriding saved lm_backend 'mlx' -> 'nano-vllm' (mlx requires macOS)")

            # Clamp LM model to GPU tier's supported list, downloading if needed
            if sys.platform != "darwin":
                from acestep.gpu_config import get_gpu_config, is_lm_model_size_allowed
                gpu_config = get_gpu_config()
                if gpu_config.available_lm_models and not is_lm_model_size_allowed(lm_model, gpu_config.available_lm_models):
                    recommended = gpu_config.recommended_lm_model
                    logger.warning(
                        f"LM model '{lm_model}' too large for {gpu_config.tier} "
                        f"({gpu_config.gpu_memory_gb:.1f} GB), switching to '{recommended}'"
                    )
                    lm_model = recommended
                    # Download the recommended model if it's not on disk
                    from acestep.model_downloader import ensure_lm_model
                    from pathlib import Path as _Path
                    dl_ok, dl_msg = await asyncio.to_thread(
                        ensure_lm_model,
                        model_name=lm_model,
                        checkpoints_dir=_Path(settings.ACESTEP_PROJECT_ROOT) / "checkpoints",
                    )
                    if dl_ok:
                        logger.info(f"LM model ready: {dl_msg}")
                    else:
                        logger.warning(f"LM model download failed: {dl_msg}")

            device = saved.get("device", settings.DEFAULT_DEVICE)

            logger.info(f"Initializing DiT model: {dit_model}")
            status, ok = await ace_backend.initialize_dit(
                config_path=dit_model,
                device=device,
            )
            if ok:
                logger.info("DiT model loaded successfully")

                # Restore previously loaded LoRAs
                lora_state_json = saved.get("lora_state", "[]")
                try:
                    import json as _json
                    lora_state = _json.loads(lora_state_json)
                    if lora_state:
                        from tadpole_studio.services.lora_service import lora_service
                        logger.info(f"Restoring {len(lora_state)} LoRA adapter(s)")
                        lora_service.restore_loras(lora_state)
                except Exception as e:
                    logger.warning(f"Failed to restore LoRA state: {e}")

                logger.info(f"Initializing LM model: {lm_model}")
                status, ok = await ace_backend.initialize_lm(
                    lm_model_path=lm_model,
                    backend=lm_backend,
                    device=device,
                )
                if ok:
                    logger.info("LM model loaded successfully")
                else:
                    logger.warning(f"LM model failed to load: {status}")
            else:
                logger.warning(f"DiT model failed to load: {status}")

        elif active_type == BackendType.HEARTMULA:
            heartmula_model_path = saved.get("heartmula_model_path", settings.HEARTMULA_MODEL_PATH)
            if heartmula_model_path:
                logger.info(f"Initializing HeartMuLa: {saved.get('heartmula_version', '3B')}")
                status, ok = await heartmula_backend.initialize(
                    model_path=heartmula_model_path,
                    version=saved.get("heartmula_version", "3B"),
                    lazy_load=saved.get("heartmula_lazy_load", "false") == "true",
                    device=saved.get("device", settings.HEARTMULA_DEVICE) or "auto",
                )
                if ok:
                    logger.info("HeartMuLa loaded successfully")
                else:
                    logger.warning(f"HeartMuLa failed to load: {status}")
            else:
                logger.info("HeartMuLa model path not configured, skipping initialization")

    asyncio.create_task(_init_active())

    # Auto-download a chat LLM if none are installed (for title generation + DJ)
    async def _auto_download_chat_llm():
        chat_llm_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "chat-llm"
        has_model = (
            chat_llm_dir.exists()
            and any(
                (d / "config.json").exists()
                for d in chat_llm_dir.iterdir()
                if d.is_dir()
            )
        )
        if has_model:
            logger.info("Chat LLM already installed, skipping auto-download")
            return

        model_name = "Qwen2.5-1.5B-Instruct-4bit"
        repo_id = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
        logger.info(f"No chat LLM found — auto-downloading {model_name}")
        generation_service.model_download_status[model_name] = "downloading"

        try:
            from huggingface_hub import snapshot_download
            local_dir = chat_llm_dir / model_name
            await asyncio.to_thread(
                snapshot_download, repo_id=repo_id, local_dir=str(local_dir)
            )
            generation_service.model_download_status[model_name] = "done"
            logger.info(f"Chat LLM auto-download complete: {model_name}")
        except Exception as e:
            generation_service.model_download_status[model_name] = f"error:{e}"
            logger.warning(f"Chat LLM auto-download failed: {e}")

    if sys.platform == "darwin":
        asyncio.create_task(_auto_download_chat_llm())
    else:
        logger.info("Skipping chat LLM auto-download (built-in requires macOS)")

    async def _cleanup_loop():
        while True:
            await asyncio.sleep(600)
            generation_service.cleanup_old_jobs()

    cleanup_task = asyncio.create_task(_cleanup_loop())

    yield

    cleanup_task.cancel()
    logger.info("Tadpole Studio shutting down...")
    await close_db()


app = FastAPI(
    title="Tadpole Studio",
    version="0.1.0",
    description="Premium Local Music Generation API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Mount routers under /api
app.include_router(health_router, prefix="/api")
app.include_router(generation_router, prefix="/api")
app.include_router(format_router, prefix="/api")
app.include_router(ws_router, prefix="/api")
app.include_router(songs_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(playlists_router, prefix="/api")
app.include_router(lora_router, prefix="/api")
app.include_router(training_router, prefix="/api")
app.include_router(training_ws_router, prefix="/api")
app.include_router(radio_router, prefix="/api")
app.include_router(dj_router, prefix="/api")
app.include_router(themes_router, prefix="/api")

# Serve audio files
audio_dir = settings.AUDIO_DIR
if audio_dir.exists():
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

# Serve uploads directory
uploads_dir = settings.UPLOADS_DIR
if uploads_dir.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


def run():
    import uvicorn
    uvicorn.run(
        "tadpole_studio.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )


if __name__ == "__main__":
    run()
