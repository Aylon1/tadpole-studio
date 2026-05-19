from pydantic import BaseModel, Field
from typing import Optional

from tadpole_studio.models.common import SongResponse


class StationResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    is_preset: bool = False
    caption_template: str = ""
    genre: str = ""
    mood: str = ""
    instrumental: bool = True
    vocal_language: str = "unknown"
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    keyscale: str = ""
    timesignature: str = ""
    duration_min: float = 30.0
    duration_max: float = 120.0
    advanced_params_json: str = "{}"
    total_plays: int = 0
    last_played_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    structure_ids: list[str] = Field(default_factory=list)


class CreateStationRequest(BaseModel):
    name: str
    description: str = ""
    caption_template: str = ""
    genre: str = ""
    mood: str = ""
    instrumental: bool = True
    vocal_language: str = "unknown"
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    keyscale: str = ""
    timesignature: str = ""
    duration_min: float = 30.0
    duration_max: float = 120.0
    advanced_params_json: str = "{}"
    structure_ids: list[str] = Field(default_factory=list)


class UpdateStationRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    caption_template: Optional[str] = None
    genre: Optional[str] = None
    mood: Optional[str] = None
    instrumental: Optional[bool] = None
    vocal_language: Optional[str] = None
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    keyscale: Optional[str] = None
    timesignature: Optional[str] = None
    duration_min: Optional[float] = None
    duration_max: Optional[float] = None
    advanced_params_json: Optional[str] = None
    structure_ids: Optional[list[str]] = None


class SongStructureResponse(BaseModel):
    id: str
    name: str
    genre: str = ""
    template: str
    is_system: bool = False
    created_at: str = ""
    updated_at: str = ""


class CreateSongStructureRequest(BaseModel):
    name: str
    genre: str = ""
    template: str
    is_system: bool = False


class UpdateSongStructureRequest(BaseModel):
    name: Optional[str] = None
    genre: Optional[str] = None
    template: Optional[str] = None
    is_system: Optional[bool] = None


class CreateStationFromSongRequest(BaseModel):
    song_id: str
    name: Optional[str] = None


class StationDetailResponse(StationResponse):
    recent_songs: list[SongResponse] = Field(default_factory=list)


class RadioStatusResponse(BaseModel):
    active_station_id: Optional[str] = None
    is_generating: bool = False
    songs_generated: int = 0


class RadioSettingsResponse(BaseModel):
    providers: list = Field(default_factory=list)
    active_provider: str = "none"
    active_model: str = ""
    system_prompt: str = ""
    default_system_prompt: str = ""


class RadioSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
