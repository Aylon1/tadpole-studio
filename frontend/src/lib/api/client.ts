import { getBaseUrl, getWsUrl, request } from "./base";
import type {
  HealthResponse,
  GenerateRequest,
  GenerateResponse,
  JobStatusResponse,
  FormatRequest,
  FormatResponse,
  SampleRequest,
  SampleResponse,
  SongResponse,
  SongListResponse,
  SettingsResponse,
  WsProgressMessage,
  ModelsResponse,
  AvailableModelsResponse,
  UploadResponse,
  GenerationHistoryEntry,
  GenerationHistoryListResponse,
  PlaylistResponse,
  PlaylistDetailResponse,
  SongVariationsResponse,
  LoraInfo,
  LoraStatusResponse,
  DatasetInfo,
  TrainingPreset,
  TrainingStartRequest,
  TrainingStatusResponse,
  TrainingUpdateMessage,
  GpuStats,
  PreprocessRequest,
  AudioFileInfo,
  DatasetConfig,
  DatasetConfigSummary,
  GenerateTitleRequest,
  GenerateTitleResponse,
  BackendsResponse,
  BackendType,
} from "@/types/api";

// Health
export const fetchHealth = () => request<HealthResponse>("/health");

// Settings
export const fetchSettings = () => request<SettingsResponse>("/settings");
export const updateSettings = (settings: Record<string, string>) =>
  request<SettingsResponse>("/settings", {
    method: "PATCH",
    body: JSON.stringify({ settings }),
  });

// Models
export const fetchModels = () => request<ModelsResponse>("/models");

export const fetchAvailableModels = () =>
  request<AvailableModelsResponse>("/models/available");

export const downloadModel = (modelName: string) =>
  request<{ status: string }>("/models/download", {
    method: "POST",
    body: JSON.stringify({ model_name: modelName }),
  });

export const fetchModelDownloadStatus = () =>
  request<Record<string, string>>("/models/download-status");

// Upload
export async function uploadAudio(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const url = `${getBaseUrl()}/api/upload`;
  const res = await fetch(url, { method: "POST", body: formData });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Upload error ${res.status}: ${body}`);
  }
  return res.json();
}

// Generation
export const submitGeneration = (params: GenerateRequest) =>
  request<GenerateResponse>("/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const fetchJobStatus = (jobId: string) =>
  request<JobStatusResponse>(`/generate/${jobId}`);

export const cancelJob = (jobId: string) =>
  request<{ message: string }>(`/generate/${jobId}/cancel`, { method: "POST" });

export const deleteGenerationResult = (filename: string) =>
  request<{ deleted: boolean }>(`/generate/result/${encodeURIComponent(filename)}`, { method: "DELETE" });

// Format & Sample
export const formatCaption = (params: FormatRequest) =>
  request<FormatResponse>("/format", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const createSample = (params: SampleRequest) =>
  request<SampleResponse>("/sample", {
    method: "POST",
    body: JSON.stringify(params),
  });

// Title generation
export const generateTitle = (params: GenerateTitleRequest) =>
  request<GenerateTitleResponse>("/generate-title", {
    method: "POST",
    body: JSON.stringify(params),
  });

// Songs
export const fetchSongs = (params?: {
  search?: string;
  sort?: string;
  order?: string;
  favorite?: boolean;
  vocal_language?: string;
  file_format?: string;
  instrumental?: boolean;
  timesignature?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}) => {
  const searchParams = new URLSearchParams();
  if (params?.search) searchParams.set("search", params.search);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.order) searchParams.set("order", params.order);
  if (params?.favorite !== undefined)
    searchParams.set("favorite", String(params.favorite));
  if (params?.vocal_language)
    searchParams.set("vocal_language", params.vocal_language);
  if (params?.file_format)
    searchParams.set("file_format", params.file_format);
  if (params?.instrumental !== undefined)
    searchParams.set("instrumental", String(params.instrumental));
  if (params?.timesignature)
    searchParams.set("timesignature", params.timesignature);
  if (params?.tag) searchParams.set("tag", params.tag);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();
  return request<SongListResponse>(`/songs${qs ? `?${qs}` : ""}`);
};

export const saveSongToLibrary = (song: {
  title: string;
  file_path: string;
  file_format?: string;
  duration_seconds?: number | null;
  caption?: string;
  lyrics?: string;
  bpm?: number | null;
  keyscale?: string;
  timesignature?: string;
  vocal_language?: string;
  instrumental?: boolean;
  generation_history_id?: string | null;
  variation_index?: number;
  parent_song_id?: string | null;
}) =>
  request<SongResponse>("/songs", {
    method: "POST",
    body: JSON.stringify(song),
  });

export const fetchSong = (id: string) =>
  request<SongResponse>(`/songs/${id}`);

export const updateSong = (
  id: string,
  updates: Partial<
    Pick<
      SongResponse,
      | "title"
      | "caption"
      | "lyrics"
      | "bpm"
      | "keyscale"
      | "timesignature"
      | "vocal_language"
      | "is_favorite"
      | "rating"
      | "tags"
      | "notes"
    >
  >,
) =>
  request<SongResponse>(`/songs/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });

export const deleteSong = (id: string) =>
  request<{ deleted: boolean }>(`/songs/${id}`, { method: "DELETE" });

export const bulkDeleteSongs = (songIds: string[]) =>
  request<{ deleted: number }>("/songs/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ song_ids: songIds }),
  });

export const bulkUpdateSongs = (
  songIds: string[],
  updates: Partial<
    Pick<
      SongResponse,
      | "title"
      | "caption"
      | "lyrics"
      | "bpm"
      | "keyscale"
      | "timesignature"
      | "vocal_language"
      | "is_favorite"
      | "rating"
      | "tags"
      | "notes"
    >
  >,
) =>
  request<{ updated: number }>("/songs/bulk", {
    method: "PATCH",
    body: JSON.stringify({ song_ids: songIds, updates }),
  });

export function getSongAudioUrl(songId: string): string {
  return `${getBaseUrl()}/api/songs/${songId}/audio`;
}

export function getSongDownloadUrl(songId: string): string {
  return `${getBaseUrl()}/api/songs/${songId}/audio?download=true`;
}

export function getPlaylistExportUrl(playlistId: string): string {
  return `${getBaseUrl()}/api/playlists/${playlistId}/export`;
}

export function getStationExportUrl(stationId: string): string {
  return `${getBaseUrl()}/api/radio/stations/${stationId}/export`;
}

// History
export const fetchHistory = (params?: {
  search?: string;
  status?: string;
  task_type?: string;
  sort?: string;
  order?: string;
  limit?: number;
  offset?: number;
}) => {
  const searchParams = new URLSearchParams();
  if (params?.search) searchParams.set("search", params.search);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.task_type) searchParams.set("task_type", params.task_type);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.order) searchParams.set("order", params.order);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();
  return request<GenerationHistoryListResponse>(`/history${qs ? `?${qs}` : ""}`);
};

export const fetchHistoryEntry = (id: string) =>
  request<GenerationHistoryEntry>(`/history/${id}`);

export const updateHistoryEntry = (id: string, updates: { title?: string }) =>
  request<GenerationHistoryEntry>(`/history/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });

export const deleteHistoryEntry = (id: string) =>
  request<{ deleted: boolean }>(`/history/${id}`, { method: "DELETE" });

// WebSocket
export function createGenerationWebSocket(
  onMessage: (msg: WsProgressMessage) => void,
  onError?: (err: Event) => void,
): WebSocket {
  const wsUrl = getWsUrl();
  const ws = new WebSocket(`${wsUrl}/api/ws/generate`);
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data) as WsProgressMessage;
    onMessage(msg);
  };
  if (onError) ws.onerror = onError;
  return ws;
}

// Playlists
export const fetchPlaylists = (params?: {
  search?: string;
  sort?: string;
  order?: string;
}) => {
  const searchParams = new URLSearchParams();
  if (params?.search) searchParams.set("search", params.search);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.order) searchParams.set("order", params.order);
  const qs = searchParams.toString();
  return request<PlaylistResponse[]>(`/playlists${qs ? `?${qs}` : ""}`);
};

export const createPlaylist = (data: { name: string; description?: string; icon?: string }) =>
  request<PlaylistResponse>("/playlists", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const fetchPlaylist = (id: string) =>
  request<PlaylistDetailResponse>(`/playlists/${id}`);

export const updatePlaylist = (
  id: string,
  updates: { name?: string; description?: string; cover_song_id?: string | null; icon?: string },
) =>
  request<PlaylistResponse>(`/playlists/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });

export const deletePlaylist = (id: string) =>
  request<{ deleted: boolean }>(`/playlists/${id}`, { method: "DELETE" });

export const addSongsToPlaylist = (playlistId: string, songIds: string[]) =>
  request<PlaylistDetailResponse>(`/playlists/${playlistId}/songs`, {
    method: "POST",
    body: JSON.stringify({ song_ids: songIds }),
  });

export const removeSongFromPlaylist = (playlistId: string, songId: string) =>
  request<PlaylistDetailResponse>(`/playlists/${playlistId}/songs/${songId}`, {
    method: "DELETE",
  });

export const reorderPlaylistSongs = (playlistId: string, songIds: string[]) =>
  request<PlaylistDetailResponse>(`/playlists/${playlistId}/songs`, {
    method: "PATCH",
    body: JSON.stringify({ song_ids: songIds }),
  });

// Song helpers
export const getSongSourcePath = (songId: string) =>
  request<{ file_path: string }>(`/songs/${songId}/source-path`);

export const fetchSongVariations = (songId: string) =>
  request<SongVariationsResponse>(`/songs/${songId}/variations`);

// LoRA
export const fetchLoras = () => request<LoraInfo[]>("/lora");

export const fetchLoraStatus = () =>
  request<LoraStatusResponse>("/lora/status");

export const addToLibrary = (path: string, adapterName?: string) =>
  request<{ message: string }>("/lora/add", {
    method: "POST",
    body: JSON.stringify({ path, adapter_name: adapterName }),
  });

export const forgetAdapter = (name: string) =>
  request<{ message: string }>(
    `/lora/known/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );

export const loadLora = (path: string, adapterName?: string) =>
  request<{ message: string }>("/lora/load", {
    method: "POST",
    body: JSON.stringify({ path, adapter_name: adapterName }),
  });

export const unloadLora = (name: string) =>
  request<{ message: string }>(
    `/lora/${encodeURIComponent(name)}/unload`,
    { method: "POST" },
  );

export const unloadAllLoras = () =>
  request<{ message: string }>("/lora/unload-all", { method: "POST" });

export const setLoraScale = (name: string, scale: number) =>
  request<{ message: string }>(
    `/lora/${encodeURIComponent(name)}/scale`,
    {
      method: "PATCH",
      body: JSON.stringify({ adapter_name: name, scale }),
    },
  );

export const toggleLora = (enabled: boolean) =>
  request<{ message: string }>("/lora/toggle", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });

export const activateLora = (name: string) =>
  request<{ message: string }>(
    `/lora/${encodeURIComponent(name)}/activate`,
    { method: "POST" },
  );

// Training
export const fetchDatasets = () =>
  request<DatasetInfo[]>("/training/datasets");

export const deleteDataset = (name: string) =>
  request<{ status: string }>(`/training/datasets/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });

export const startPreprocess = (params: PreprocessRequest) =>
  request<{ status: string }>("/training/preprocess", {
    method: "POST",
    body: JSON.stringify(params),
  });

// Dataset configs
export const scanAudioDir = (audioDir: string) =>
  request<AudioFileInfo[]>("/training/scan-audio", {
    method: "POST",
    body: JSON.stringify({ audio_dir: audioDir }),
  });

export const saveDatasetConfig = (config: DatasetConfig) =>
  request<{ status: string; path: string }>("/training/dataset-configs", {
    method: "POST",
    body: JSON.stringify({ config }),
  });

export const fetchDatasetConfigs = () =>
  request<DatasetConfigSummary[]>("/training/dataset-configs");

export const loadDatasetConfig = (name: string) =>
  request<DatasetConfig>(`/training/dataset-configs/${encodeURIComponent(name)}`);

export const loadDatasetEmbeddedConfig = (name: string) =>
  request<DatasetConfig>(`/training/datasets/${encodeURIComponent(name)}/config`);

export const deleteDatasetConfig = (name: string) =>
  request<{ status: string }>(
    `/training/dataset-configs/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );

export const fetchPresets = () =>
  request<TrainingPreset[]>("/training/presets");

export const startTraining = (params: TrainingStartRequest) =>
  request<{ status: string }>("/training/start", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const stopTraining = () =>
  request<{ status: string }>("/training/stop", { method: "POST" });

export const fetchTrainingStatus = () =>
  request<TrainingStatusResponse>("/training/status");

// Models (enhanced)
export const switchDitModel = (modelName: string) =>
  request<{ message: string }>("/models/switch-dit", {
    method: "POST",
    body: JSON.stringify({ model_name: modelName }),
  });

export const switchLmModel = (modelName: string, backend?: string) =>
  request<{ message: string }>("/models/switch-lm", {
    method: "POST",
    body: JSON.stringify({ model_name: modelName, backend }),
  });

export const fetchGpuStats = () => request<GpuStats>("/models/gpu-stats");

// Backends
export const fetchBackends = () => request<BackendsResponse>("/backends");

export const switchBackend = (backend: BackendType) =>
  request<{ message: string }>("/models/switch-backend", {
    method: "POST",
    body: JSON.stringify({ backend }),
  });

// Custom Themes
export interface CustomThemeData {
  name: string;
  css: string;
  color_scheme: string;
  preview_bg: string;
  preview_sidebar: string;
  preview_primary: string;
}

export interface CustomThemeResponse {
  id: string;
  name: string;
  css: string;
  color_scheme: string;
  preview_bg: string;
  preview_sidebar: string;
  preview_primary: string;
  created_at: string;
}

export const fetchCustomThemes = () =>
  request<CustomThemeResponse[]>("/themes");

export const createCustomTheme = (data: CustomThemeData) =>
  request<CustomThemeResponse>("/themes", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const deleteCustomTheme = (id: string) =>
  request<{ deleted: boolean }>(`/themes/${id}`, { method: "DELETE" });

// Training WebSocket
export function createTrainingWebSocket(
  onMessage: (msg: TrainingUpdateMessage) => void,
  onError?: (err: Event) => void,
): WebSocket {
  const wsUrl = getWsUrl();
  const ws = new WebSocket(`${wsUrl}/api/ws/training`);
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data) as TrainingUpdateMessage;
    onMessage(msg);
  };
  if (onError) ws.onerror = onError;
  return ws;
}
