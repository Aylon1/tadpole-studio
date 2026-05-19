"""
Radio station endpoints.

Inspired by:
- nalexand/ACE-Step-1.5-OPTIMIZED (MusicBox jukebox)
- PasiKoodaa/ACE-Step-RADIO (radio station mode)
"""

import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tadpole_studio.config import settings

from tadpole_studio.ace_handler import (
    get_dit_throttle,
    get_throttle_radio_only,
    get_vae_throttle,
    set_dit_throttle,
    set_radio_active,
    set_throttle_radio_only,
    set_vae_throttle,
)
from tadpole_studio.db.connection import get_db
from tadpole_studio.models.radio import (
    CreateStationFromSongRequest,
    CreateStationRequest,
    RadioSettingsResponse,
    RadioSettingsUpdate,
    RadioStatusResponse,
    StationDetailResponse,
    StationResponse,
    UpdateStationRequest,
)
from tadpole_studio.models.common import SongResponse
from tadpole_studio.services.radio_service import radio_service

router = APIRouter(prefix="/radio", tags=["radio"])


@router.get("/stations", response_model=list[StationResponse])
async def list_stations() -> list[StationResponse]:
    return await radio_service.list_stations()


@router.post("/stations", response_model=StationResponse)
async def create_station(body: CreateStationRequest) -> StationResponse:
    data = body.model_dump(exclude_unset=True)
    return await radio_service.create_station(data)


@router.get("/stations/{station_id}", response_model=StationDetailResponse)
async def get_station(station_id: str) -> StationDetailResponse:
    station = await radio_service.get_station(station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")

    recent_songs_data = await radio_service.get_station_songs(station_id, limit=20)
    recent_songs = [SongResponse(**s) for s in recent_songs_data]

    return StationDetailResponse(
        **station.model_dump(),
        recent_songs=recent_songs,
    )


@router.patch("/stations/{station_id}", response_model=StationResponse)
async def update_station(station_id: str, body: UpdateStationRequest) -> StationResponse:
    updates = body.model_dump(exclude_unset=True)
    station = await radio_service.update_station(station_id, updates)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.delete("/stations/{station_id}")
async def delete_station(station_id: str) -> dict:
    deleted = await radio_service.delete_station(station_id)
    if not deleted:
        raise HTTPException(
            status_code=400,
            detail="Station not found or is a built-in preset",
        )
    return {"deleted": True}


@router.get("/stations/{station_id}/export")
async def export_station(station_id: str):
    db = await get_db()

    cursor = await db.execute(
        "SELECT name FROM radio_stations WHERE id = ?", (station_id,)
    )
    station_row = await cursor.fetchone()
    if station_row is None:
        raise HTTPException(status_code=404, detail="Station not found")

    cursor = await db.execute(
        """
        SELECT s.title, s.file_path, s.file_format
        FROM radio_station_songs rs
        JOIN songs s ON s.id = rs.song_id
        WHERE rs.station_id = ?
        ORDER BY rs.generated_at DESC
        """,
        (station_id,),
    )
    rows = await cursor.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Station has no songs")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, row in enumerate(rows):
            audio_path = settings.AUDIO_DIR / row["file_path"]
            if not audio_path.exists():
                continue
            arcname = f"{idx + 1:02d} - {row['title']}.{row['file_format']}"
            zf.write(str(audio_path), arcname)
    buf.seek(0)

    filename = f"{station_row['name']}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/stations/from-song", response_model=StationResponse)
async def create_station_from_song(body: CreateStationFromSongRequest) -> StationResponse:
    station = await radio_service.create_station_from_song(
        body.song_id, body.name
    )
    if station is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return station


@router.post("/generate/{station_id}")
async def generate_next_track(station_id: str) -> dict:
    set_radio_active(True)
    try:
        result = await radio_service.generate_next_track(station_id)
    finally:
        set_radio_active(False)
    if not result.get("success"):
        raise HTTPException(
            status_code=503,
            detail=result.get("error", "Generation failed"),
        )
    return result


@router.get("/status", response_model=RadioStatusResponse)
async def get_status() -> RadioStatusResponse:
    return RadioStatusResponse(
        active_station_id=None,
        is_generating=False,
        songs_generated=0,
    )


@router.post("/stop")
async def stop_radio() -> dict:
    return {"stopped": True}


# -- Radio LLM settings --


@router.get("/settings", response_model=RadioSettingsResponse)
async def get_radio_settings() -> RadioSettingsResponse:
    info = await radio_service.get_settings()
    return RadioSettingsResponse(**info)


@router.patch("/settings", response_model=RadioSettingsResponse)
async def update_radio_settings(body: RadioSettingsUpdate) -> RadioSettingsResponse:
    info = await radio_service.update_settings(
        provider=body.provider,
        model=body.model,
        system_prompt=body.system_prompt,
        api_key=body.api_key,
        api_base=body.api_base,
    )
    return RadioSettingsResponse(**info)


# -- VAE throttle settings (radio playback smoothness) --


class VaeThrottleRequest(BaseModel):
    chunk_size: int = 512
    sleep_ms: int = 100


@router.get("/vae-throttle")
async def get_throttle() -> dict:
    return get_vae_throttle()


@router.put("/vae-throttle")
async def update_throttle(body: VaeThrottleRequest) -> dict:
    set_vae_throttle(body.chunk_size, body.sleep_ms)
    result = get_vae_throttle()
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vae_chunk_size', ?, datetime('now'))",
        (str(result["chunk_size"]),),
    )
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('vae_sleep_ms', ?, datetime('now'))",
        (str(result["sleep_ms"]),),
    )
    await db.commit()
    return result


# -- DiT throttle settings --


class DitThrottleRequest(BaseModel):
    sleep_ms: int = 100


@router.get("/dit-throttle")
async def get_dit() -> dict:
    return get_dit_throttle()


@router.put("/dit-throttle")
async def update_dit(body: DitThrottleRequest) -> dict:
    set_dit_throttle(body.sleep_ms)
    result = get_dit_throttle()
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('dit_sleep_ms', ?, datetime('now'))",
        (str(result["sleep_ms"]),),
    )
    await db.commit()
    return result


# -- Reset throttle to defaults --

_THROTTLE_DEFAULTS = {
    "vae_chunk_size": 128,
    "vae_sleep_ms": 200,
    "dit_sleep_ms": 200,
    "throttle_radio_only": "true",
}


@router.post("/throttle-reset")
async def reset_throttle() -> dict:
    set_vae_throttle(128, 200)
    set_dit_throttle(200)
    set_throttle_radio_only(True)
    db = await get_db()
    for key, value in _THROTTLE_DEFAULTS.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, str(value)),
        )
    await db.commit()
    return {**get_vae_throttle(), **get_dit_throttle(), "radio_only": False}


# -- Throttle scope (all vs radio-only) --


class ThrottleScopeRequest(BaseModel):
    radio_only: bool = False


@router.get("/throttle-scope")
async def get_scope() -> dict:
    return {"radio_only": get_throttle_radio_only()}


@router.put("/throttle-scope")
async def update_scope(body: ThrottleScopeRequest) -> dict:
    set_throttle_radio_only(body.radio_only)
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('throttle_radio_only', ?, datetime('now'))",
        (str(body.radio_only).lower(),),
    )
    await db.commit()
    return {"radio_only": get_throttle_radio_only()}
