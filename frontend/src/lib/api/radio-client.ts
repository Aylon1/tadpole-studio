import { request } from "./base";
import type {
  StationResponse,
  StationDetailResponse,
  CreateStationRequest,
  UpdateStationRequest,
  RadioStatusResponse,
  RadioSettingsResponse,
  RadioSettingsUpdate,
  SongResponse,
  SongStructure,
} from "@/types/api";

export const fetchStructures = () =>
  request<SongStructure[]>("/radio/structures");

export const createStructure = (data: Partial<SongStructure>) =>
  request<SongStructure>("/radio/structures", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateStructure = (id: string, data: Partial<SongStructure>) =>
  request<SongStructure>(`/radio/structures/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteStructure = (id: string) =>
  request<{ deleted: boolean }>(`/radio/structures/${id}`, { method: "DELETE" });

export const fetchStations = () =>
  request<StationResponse[]>("/radio/stations");

export const createStation = (data: CreateStationRequest) =>
  request<StationResponse>("/radio/stations", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const fetchStation = (id: string) =>
  request<StationDetailResponse>(`/radio/stations/${id}`);

export const updateStation = (id: string, updates: UpdateStationRequest) =>
  request<StationResponse>(`/radio/stations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });

export const deleteStation = (id: string) =>
  request<{ deleted: boolean }>(`/radio/stations/${id}`, { method: "DELETE" });

export const createStationFromSong = (songId: string, name?: string) =>
  request<StationResponse>("/radio/stations/from-song", {
    method: "POST",
    body: JSON.stringify({ song_id: songId, name }),
  });

export const generateNextTrack = (
  stationId: string,
  signal?: AbortSignal,
) =>
  request<{ success: boolean; song?: SongResponse; error?: string }>(
    `/radio/generate/${stationId}`,
    { method: "POST", signal },
  );

export const fetchRadioStatus = () =>
  request<RadioStatusResponse>("/radio/status");

export const stopRadio = () =>
  request<{ stopped: boolean }>("/radio/stop", { method: "POST" });

// VAE throttle (radio playback smoothness)
export interface VaeThrottle {
  chunk_size: number;
  sleep_ms: number;
}

export const fetchVaeThrottle = () =>
  request<VaeThrottle>("/radio/vae-throttle");

export const updateVaeThrottle = (data: VaeThrottle) =>
  request<VaeThrottle>("/radio/vae-throttle", {
    method: "PUT",
    body: JSON.stringify(data),
  });

// DiT diffusion throttle (radio playback smoothness)
export interface DitThrottle {
  sleep_ms: number;
}

export const fetchDitThrottle = () =>
  request<DitThrottle>("/radio/dit-throttle");

export const updateDitThrottle = (data: DitThrottle) =>
  request<DitThrottle>("/radio/dit-throttle", {
    method: "PUT",
    body: JSON.stringify(data),
  });

// Reset all throttle settings to defaults
export const resetThrottle = () =>
  request<VaeThrottle & DitThrottle>("/radio/throttle-reset", {
    method: "POST",
  });

// Throttle scope (all generation vs radio-only)
export interface ThrottleScope {
  radio_only: boolean;
}

export const fetchThrottleScope = () =>
  request<ThrottleScope>("/radio/throttle-scope");

export const updateThrottleScope = (data: ThrottleScope) =>
  request<ThrottleScope>("/radio/throttle-scope", {
    method: "PUT",
    body: JSON.stringify(data),
  });

// Radio LLM settings
export const fetchRadioSettings = () =>
  request<RadioSettingsResponse>("/radio/settings");

export const updateRadioSettings = (settings: RadioSettingsUpdate) =>
  request<RadioSettingsResponse>("/radio/settings", {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
