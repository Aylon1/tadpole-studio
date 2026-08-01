# Tadpole Radio Stations System — Comprehensive Analysis

> Generated: 2026-08-01
> Scope: Complete analysis of radio station architecture, custom station configuration, LLM interactions, prompt templates, DJ comparison, and full request/response flows.

---

## Table of Contents

1. [Backend Radio Models](#1-backend-radio-models)
2. [Backend Radio Service](#2-backend-radio-service)
3. [Backend Radio Router](#3-backend-radio-router)
4. [LLM Provider System](#4-llm-provider-system)
5. [Prompt Templates](#5-prompt-templates)
6. [DJ System — Comparison with Radio](#6-dj-system--comparison-with-radio)
7. [Frontend Architecture](#7-frontend-architecture)
8. [Audio Engine](#8-audio-engine)
9. [Frontend Hooks](#9-frontend-hooks)
10. [Complete Request/Response Flow](#10-complete-requestresponse-flow--custom-station-playback)
11. [WebSocket Usage](#11-websocket-usage)
12. [Database Schema](#12-database-schema-inferred-from-sql)
13. [Patch File](#13-patch-file)
14. [Key Architectural Observations](#14-key-architectural-observations)

---

## 1. Backend Radio Models

**File:** [`backend/src/tadpole_studio/models/radio.py`](backend/src/tadpole_studio/models/radio.py)

### Key Data Structures

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `StationResponse` | Full station representation | `id`, `name`, `caption_template`, `genre`, `mood`, `instrumental`, `vocal_language`, `bpm_min/max`, `keyscale`, `timesignature`, `duration_min/max`, `advanced_params_json`, `structure_ids[]` |
| `CreateStationRequest` | Create station payload | Same fields minus `is_preset`, `total_plays`, timestamps |
| `UpdateStationRequest` | Partial update payload | All fields `Optional` |
| `SongStructureResponse` | Lyrics structure template | `id`, `name`, `genre`, `template` (text like `[Verse 1]\n[Chorus]\n...`), `is_system` |
| `StationDetailResponse` | Station + recent songs | Extends StationResponse with `recent_songs[]` |
| `RadioSettingsResponse` | LLM settings state | `providers[]`, `active_provider`, `active_model`, `system_prompt`, `default_system_prompt` |
| `RadioSettingsUpdate` | Settings patch | `provider`, `model`, `system_prompt`, `api_key`, `api_base` (all optional) |
| `RadioStatusResponse` | Runtime status | `active_station_id`, `is_generating`, `songs_generated` |
| `CreateStationFromSongRequest` | Create from existing song | `song_id`, `name?` |

### Custom Station Configuration

A station is defined by:
- **Musical parameters**: `genre`, `mood`, `bpm_min/max`, `keyscale`, `timesignature`, `instrumental`, `vocal_language`
- **`caption_template`**: Fallback caption when no LLM available. Supports `{mood}` and `{genre}` template variables.
- **`advanced_params_json`**: JSON string containing lyrics generation config:
  - `theme_pool[]`: List of themes the LLM randomly picks from (e.g., "heartbreak", "nostalgia", "city life")
  - `lyrics_style_addons`: Style directive for lyrics (default: "Standard style")
  - `intensity`: Emotional intensity (default: "Moderate")
- **`structure_ids[]`**: References to song structure templates for lyrics formatting
- **Duration range**: `duration_min` (default 30s), `duration_max` (default 120s)

---

## 2. Backend Radio Service

**File:** [`backend/src/tadpole_studio/services/radio_service.py`](backend/src/tadpole_studio/services/radio_service.py)

### Core Business Logic — `RadioService`

The service handles:
- **Station CRUD**: `list_stations()`, `get_station()`, `create_station()`, `update_station()`, `delete_station()`
- **Station from song**: `create_station_from_song()` — extracts params from an existing song (BPM ±10, keyscale, caption as template)
- **Structure CRUD**: Full CRUD for song structure templates
- **LLM Settings**: `get_settings()`, `update_settings()` — provider/model/prompt/API key management
- **Track Generation**: `generate_next_track()` — the main generation pipeline

### Generation Pipeline — `generate_next_track(station_id)`

```
1. Get station from DB
2. Check DiT model initialized
3. Generate caption via LLM (or fallback to template)
4. Generate lyrics via LLM (if non-instrumental)
5. Acquire GPU lock (await_acquire — blocks until available)
6. Randomize BPM/duration within station ranges
7. Build generation params dict
8. Create generation_history DB record
9. Call generation_service.generate(params)
10. Generate title (LLM or random) — runs UNDER GPU lock
11. Release GPU lock
12. Post-generation: save song to DB, copy audio file, link to station
13. Return { success: true, song: SongResponse }
```

### Three LLM Generation Methods

#### a. `_generate_caption_with_llm(station)`
- Builds user message from station params: genre, mood, instrumental, vocal_language, BPM range, keyscale, timesignature, caption_template as style reference
- Sends to LLM with system prompt
- Returns caption string or `None` (falls back to template)
- **Temperature: 0.7**

#### b. `_generate_title_with_llm(station, caption, recent_titles)`
- Generates station-themed title (1-8 words)
- Avoids recent titles from same station (last 10)
- Cleans response: strips think tags, quotes, trailing periods, truncates at 80 chars
- Falls back to `generate_random_title()` if LLM unavailable or returns duplicate
- **Temperature: 0.7, max_tokens: 50**

#### c. `_generate_lyrics_with_llm(station, caption)`
- Only runs for non-instrumental stations
- Parses `advanced_params_json` for theme pool, style addons, intensity
- Selects random theme from `theme_pool` (or built-in pool of 20 themes)
- Selects random structure from station's `structure_ids` (or default: Verse-Chorus-Verse-Chorus-Bridge-Chorus-Outro)
- Builds detailed prompt with genre, language, target duration, keyscale, mood
- **Temperature: 0.8, max_tokens: 800**
- Returns cleaned lyrics or empty string

### LLM Selection — `_get_radio_llm()`

```
Configured provider (from settings table)
  → Try it (is_available?)
    → If unavailable → Fall back to Ollama
      → If unavailable → Return (None, "", system_prompt)
```

API keys loaded from DB settings for cloud providers if not set from env vars.

---

## 3. Backend Radio Router

**File:** [`backend/src/tadpole_studio/routers/radio.py`](backend/src/tadpole_studio/routers/radio.py)

### API Endpoints

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| GET | `/radio/stations` | `list_stations()` | List all stations |
| POST | `/radio/stations` | `create_station()` | Create custom station |
| GET | `/radio/stations/{id}` | `get_station()` | Station detail + recent 20 songs |
| PATCH | `/radio/stations/{id}` | `update_station()` | Update station |
| DELETE | `/radio/stations/{id}` | `delete_station()` | Delete (non-preset only) |
| POST | `/radio/stations/from-song` | `create_station_from_song()` | Create station from existing song |
| GET | `/radio/stations/{id}/export` | `export_station()` | Download station songs as ZIP |
| POST | `/radio/generate/{id}` | `generate_next_track()` | Generate next track (blocking) |
| GET | `/radio/structures` | `list_structures()` | List lyrics structures |
| POST | `/radio/structures` | `create_structure()` | Create structure |
| PUT | `/radio/structures/{id}` | `update_structure()` | Update structure |
| DELETE | `/radio/structures/{id}` | `delete_structure()` | Delete structure (non-system only) |
| GET | `/radio/settings` | `get_radio_settings()` | LLM settings + provider info |
| PATCH | `/radio/settings` | `update_radio_settings()` | Update LLM settings |
| GET | `/radio/vae-throttle` | `get_throttle()` | Get VAE decode throttle |
| PUT | `/radio/vae-throttle` | `update_throttle()` | Set VAE throttle (chunk_size, sleep_ms) |
| GET | `/radio/dit-throttle` | `get_dit()` | Get DiT diffusion throttle |
| PUT | `/radio/dit-throttle` | `update_dit()` | Set DiT throttle (sleep_ms) |
| POST | `/radio/throttle-reset` | `reset_throttle()` | Reset all throttle to defaults |
| GET | `/radio/throttle-scope` | `get_scope()` | Get throttle scope |
| PUT | `/radio/throttle-scope` | `update_scope()` | Set radio_only scope |
| GET | `/radio/status` | `get_status()` | Radio status (static — always zeros) |
| POST | `/radio/stop` | `stop_radio()` | Stop radio (stub) |

### Throttle Defaults
- `vae_chunk_size = 128` frames
- `vae_sleep_ms = 200` ms
- `dit_sleep_ms = 200` ms
- `throttle_radio_only = true`

### Radio Activation
`generate_next_track()` wraps generation with `set_radio_active(True/False)` to signal the ACE handler that radio mode is active, enabling throttle behavior during VAE/DiT processing.

---

## 4. LLM Provider System

**File:** [`backend/src/tadpole_studio/services/llm_provider.py`](backend/src/tadpole_studio/services/llm_provider.py)

### Provider Registry

| Provider | Slug | API Key Required | Availability Check | Notes |
|----------|------|-----------------|-------------------|-------|
| `MLXChatProvider` | `built-in` | No | macOS + MLX package + models in `data/chat-llm/` | Apple Silicon only. Loads models from local dirs. Thread-safe with lock. |
| `OllamaProvider` | `ollama` | No | HTTP GET to `{base_url}/api/tags` | Configurable via `TADPOLE_OLLAMA_URL` (default `localhost:11434`). Async model listing. |
| `OpenAIProvider` | `openai` | Yes (`TADPOLE_OPENAI_API_KEY`) | Package installed + key present | Models: gpt-4.1-nano, gpt-4.1-mini, gpt-4.1, o3-mini, o4-mini, gpt-5-nano, gpt-5-mini, gpt-5 |
| `AnthropicProvider` | `anthropic` | Yes (`TADPOLE_ANTHROPIC_API_KEY`) | Package installed + key present | Models: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6. Extracts system message separately. |
| `OpenAICompatibleProvider` | `openai-compatible` | No (uses dummy key) | Needs `api_base` URL + package installed | For custom OpenAI-compatible APIs. Dynamically lists models from `/v1/models`. |

### Abstract Interface — `LLMProvider`

```python
class LLMProvider(ABC):
    name: str = ""
    requires_api_key: bool = False
    package_installed: bool  # Override for cloud providers
    unavailable_reason: str  # Human-readable reason

    async def is_available() -> bool
    async def chat(messages, model, max_tokens=1024, temperature=0.0) -> str
    def list_models() -> list[str]
    async def list_models_async() -> list[str]
```

### Shared Behavior
- All providers log chat calls with provider, model, and temperature
- OpenAI and Anthropic providers have fallback for models that reject temperature param
- Anthropic provider separates system message from chat messages (Anthropic API pattern)
- API keys can be set at runtime via `set_api_key()` and persisted in DB settings

---

## 5. Prompt Templates

### Radio Caption System Prompt (default)
```
You are a music caption generator. Given station parameters, write a creative, 
detailed caption for an AI music generator. Describe instrumentation, texture, 
atmosphere, and sonic qualities. Be specific and varied — each caption should 
feel unique. Output ONLY the caption text, nothing else.
```

**User message format:**
```
Generate a unique music caption for these station parameters:
Genre: {genre}
Mood: {mood}
Instrumental: yes/no
Vocal language: {language}
BPM range: {min}-{max}
Key/scale: {keyscale}
Time signature: {timesignature}
Style reference: {caption_template}
```

### Radio Title System Prompt
```
Generate a single creative song title (1-8 words) that fits the style 
of the station and song described below. The title should evoke the 
genre and mood — it can be poetic, atmospheric, or thematic. 
Output ONLY the title, nothing else.
Do NOT reuse any of these recent titles: "title1", "title2", ...
```

**User message format:**
```
Station: {station_name}
Genre: {genre}. Mood: {mood}. 
Caption: {caption}
```

### Radio Lyrics Prompt (user message only — no system prompt)
```
Write a {genre} song in {language} about '{theme}' using this exact structure:
{structure_template}

STRICT REQUIREMENTS:
1. Write ONLY the song lyrics - no translations, no explanations, no notes
2. Use ONLY the specified language: {language}
3. Follow the structure EXACTLY as shown
4. Format each section header exactly as shown (e.g. [Verse 1])
5. Never include any text outside the lyrics structure
6. Target Duration: {duration}s
7. Musical Key: {keyscale}

STYLE GUIDELINES:
- {lyrics_style_addons}
- {intensity} feel
- {mood} mood
- Concept/Description: {station.description}
- Use vivid imagery and emotional resonance
- Match the rhythm and phrasing to {genre} conventions

BACKGROUND VIBE/CAPTION (For Optional Context):
{caption}
```

**Default structure template:** `[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n[Bridge]\n[Chorus]\n[Outro]`

**Built-in theme pool (20 themes):**
heartbreak, youthful rebellion, changing seasons, a late night drive, finding oneself, overcoming adversity, falling in love, nostalgia, a distant memory, a fleeting moment, the beauty of nature, city life, a quiet morning, an epic journey, betrayal, hope for the future, a secret romance, dancing in the rain, a farewell, a new beginning

### LLM Parameters

| Generation | Temperature | Max Tokens | Notes |
|------------|-------------|------------|-------|
| Caption | 0.7 | default (1024) | System + user prompt |
| Title | 0.7 | 50 | System + user, avoids recent titles |
| Lyrics | 0.8 | 800 | User message only |

### Response Cleaning
- All methods strip `<think>...</think>` think tags via regex
- Title additionally strips surrounding quotes, trailing periods, truncates at 80 chars
- Lyrics: only think tag stripping

---

## 6. DJ System — Comparison with Radio

### Overview

The DJ system ([`backend/src/tadpole_studio/services/dj_service.py`](backend/src/tadpole_studio/services/dj_service.py)) is a **conversational** music generation interface, while radio is **station-based auto-generation**.

### Comparison Table

| Aspect | Radio | DJ |
|--------|-------|-----|
| **Interaction** | User selects station, tracks auto-generate continuously | User chats naturally, DJ generates on request |
| **LLM Input** | Station params → caption → lyrics → title | Full conversation + system prompt → JSON params |
| **Caption Source** | LLM or template from station params | Extracted from JSON code block in LLM response |
| **Generation Trigger** | Continuous (buffer-based, `BUFFER_THRESHOLD=2`) | Per-message (when LLM includes JSON block) |
| **Persistence** | Station config + linked songs in DB | Conversation + messages in DB |
| **Title Gen** | Station-themed LLM or random titles | Caption-based LLM title (`generate_song_title`) |
| **Lyrics Gen** | Dedicated LLM call with structure templates | Passed directly from DJ JSON params |
| **GPU Lock** | `await_acquire()` — blocks until available | `acquire()` — returns False if busy (non-blocking) |
| **Async Pattern** | Synchronous (frontend waits for result) | Fire-and-forget (`asyncio.create_task()`) |
| **WebSocket** | Not used | Yes — `generation_ws_manager` broadcasts progress/completed/failed |
| **Auto-save** | Optional playlist save per station | No auto-save |
| **Actions** | None | `[ACTION:SKIP]`, `[ACTION:REPLAY]`, `[ACTION:SAVE]`, `[ACTION:CREATE_STATION]` |
| **Settings keys** | `radio_llm_provider`, `radio_llm_model`, `radio_system_prompt` | `dj_provider`, `dj_model`, `dj_system_prompt` |

### DJ System Prompt

Instructs the LLM to:
1. Respond conversationally and enthusiastically about music requests
2. Include a JSON code block with generation parameters:
   - `caption`: Descriptive text about music style/mood/instruments
   - `lyrics`: Song lyrics with `[verse]`, `[chorus]`, `[bridge]` tags (12+ lines for vocal)
   - `instrumental`: boolean
   - `bpm`: 60-200
   - `keyscale`: e.g., "C major", "A minor"
   - `timesignature`: e.g., "4/4", "3/4", "6/8"
   - `duration`: seconds (60-120 recommended, 90+ for songs with lyrics)
   - `vocal_language`: e.g., "english", "unknown"
3. Support action commands: `[ACTION:SKIP]`, `[ACTION:REPLAY]`, `[ACTION:SAVE]`, `[ACTION:CREATE_STATION]`

### DJ Fallback Chain

More elaborate than radio (5-level fallback):
1. Try configured provider
2. If unavailable → Try built-in (macOS MLX)
3. If that fails → Try Ollama
4. If still fails → Return error with platform-specific guidance
5. On chat error → Retry with fallback providers, auto-switch settings on success

### Shared Infrastructure

Both radio and DJ use:
- Same `LLMProvider` registry ([`llm_provider.py`](backend/src/tadpole_studio/services/llm_provider.py))
- Same SQLite `settings` table (different key prefixes)
- Same set of 5 providers
- Same API key management (stored per provider in settings)
- Same think tag stripping pattern

---

## 7. Frontend Architecture

### State Management — `frontend/src/stores/radio-store.ts`

Zustand store with:
- `stations: StationResponse[]` — All loaded stations
- `activeStationId: string | null` — Currently playing station
- `isGenerating: boolean` — Whether a generation is in progress
- `songsGenerated: number` — Counter for tracks generated this session

Actions:
- `setStations(stations)` — Replace station list
- `startStation(id)` — Set active station, reset song counter
- `stopStation()` — Clear active station, stop generating, reset counter
- `setIsGenerating(v)` — Toggle generation state
- `incrementSongsGenerated()` — Increment counter

### Main Component — `frontend/src/components/radio/radio-client.tsx`

- Uses React Query: `fetchStations` with `["stations"]` key
- `deleteStation` mutation with auto-refetch and toast notifications
- Local state for dialogs: create, edit, settings, structures
- Composes sub-components: `StationGrid`, `StationNowPlaying`, `CreateStationDialog`, `EditStationDialog`, `RadioSettingsDialog`, `StructuresSettingsDialog`
- Animated transitions with Framer Motion for now-playing panel

### Radio Settings Dialog — `frontend/src/components/radio/radio-settings-dialog.tsx`

Four settings sections:
1. **Caption LLM**: Provider selector (includes "None"), model selector, system prompt textarea with reset button, availability indicators, API key warnings
2. **GPU Throttle**: DiT sleep slider (0-500ms), VAE chunk size slider (128-2048), VAE sleep slider (0-500ms), radio-only scope toggle, reset button
3. **Auto-save**: Toggle from `useSettingsStore` — auto-save each generated track to a playlist matching station name
4. **Ambiance**: Toggle from `useAmbientStore` — vinyl crackle / radio static / brown noise effects with volume slider (0-50%)

### API Client — `frontend/src/lib/api/radio-client.ts`

Thin wrapper functions around base `request()`:
- Station CRUD: `fetchStations`, `createStation`, `fetchStation`, `updateStation`, `deleteStation`
- Station from song: `createStationFromSong(songId, name?)`
- Generation: `generateNextTrack(stationId, signal?)` — supports `AbortSignal` for cancellation
- Status: `fetchRadioStatus`, `stopRadio`
- Throttle: `fetchVaeThrottle`, `updateVaeThrottle`, `fetchDitThrottle`, `updateDitThrottle`, `resetThrottle`, `fetchThrottleScope`, `updateThrottleScope`
- LLM settings: `fetchRadioSettings`, `updateRadioSettings`
- Structures: `fetchStructures`, `createStructure`, `updateStructure`, `deleteStructure`

---

## 8. Audio Engine

**File:** [`frontend/src/lib/audio/radio-engine.ts`](frontend/src/lib/audio/radio-engine.ts)

### Architecture

`RadioAudioEngine` is a singleton that uses **AudioWorklet** for isolated audio playback:

```
┌─────────────────────────────────────────────┐
│              Main Thread                     │
│                                             │
│  RadioAudioEngine                           │
│    ├── _buffers: Map<songId, AudioBuffer>  │
│    ├── _ctx: AudioContext                  │
│    ├── _gain: GainNode                     │
│    └── _worklet: AudioWorkletNode ──postMessage + transfer──▶ Worklet Thread
│                                               │
│                                               │  process() reads Float32Array
│                                               └─────────────────────────────▶ Audio Output
└─────────────────────────────────────────────┘
```

### Key Design Principles
- **Zero-copy transfer**: PCM data transferred via `postMessage` with `Transferable` ArrayBuffers (line 142). The worklet gets exclusive ownership — no shared memory with main thread.
- **Worklet isolation**: The worklet thread's `process()` reads from locally-owned `Float32Array`s — the most isolated path from memory to audio output possible in a browser. Prevents audio hiccups when MLX saturates unified memory during VAE decode.
- **Fallback**: Falls back to `AudioBufferSourceNode` if AudioWorklet not supported
- **Warmup**: `warmup()` must be called within user gesture to unlock `AudioContext`

### API

| Method | Description |
|--------|-------------|
| `warmup()` | Create + resume AudioContext (must be in user gesture) |
| `cacheBuffer(songId, buffer)` | Store decoded AudioBuffer |
| `hasBuffer(songId)` | Check if pre-decoded |
| `clearBuffers()` | Clear all cached buffers |
| `play(songId)` | Play from cache (returns false if not cached) |
| `pause()` | Save offset, pause playback |
| `resume()` | Resume from saved offset |
| `seek(time)` | Seek to time in seconds |
| `setVolume(v)` | Set volume (0-1) |
| `stop()` | Stop playback, clear current song |

### Properties & Events

| Property/Event | Type | Description |
|----------------|------|-------------|
| `currentTime` | `number` | Current playback position |
| `duration` | `number` | Duration of current song |
| `playing` | `boolean` | Whether currently playing |
| `currentSongId` | `string \| null` | Currently playing song ID |
| `audioContext` | `AudioContext \| null` | The underlying AudioContext |
| `onended` | `() => void` | Called when current song ends |
| `ontimeupdate` | `(time: number) => void` | Called every 400ms with current time |

---

## 9. Frontend Hooks

### `useRadio()` — Station Start/Stop

**File:** [`frontend/src/hooks/use-radio.ts`](frontend/src/hooks/use-radio.ts)

Manages station lifecycle using a **session counter pattern**:

```typescript
let _sessionCounter = 0;  // Monotonically increasing
let _activeSession = 0;   // Current active session
```

Each `startStation()` increments the counter. All async continuations check `session !== _activeSession` and bail out if the session changed (preventing stale operations after stop/restart).

#### `startStation(stationId)` Flow:
1. `abortRadioRequests()` — Cancel in-flight API requests
2. `forceReleaseGenLock()` — Release frontend generation lock
3. `radioEngine.stop()` + `clearBuffers()` — Stop audio
4. `radioEngine.warmup()` — Unlock AudioContext (must be in user gesture)
5. `_sessionCounter++` — Start new session
6. `createRadioAbortController()` — New abort signal for this session
7. `startStation()` in store — Set active station
8. Set GPU holder to "radio", acquire gen lock
9. **Generate song 1**: `await generateNextTrack(stationId, signal)`
10. Session check → `decodeAndCacheAudio(song1.id)`
11. Session check → `radioEngine.play(song1.id)` + `play(song1)` + `setQueue([song1])`
12. **Generate song 2** (pre-buffer): `await generateNextTrack(stationId, signal)`
13. Session check → `addToQueue(song2)` + `prefetchAudio(song2.id)`
14. On catch: Silently swallow `AbortError`
15. On finally (if still active session): Invalidate queries, release lock, clear GPU holder

#### `stopStation()` Flow:
1. `_sessionCounter++` — Invalidate current session
2. `abortRadioRequests()` — Cancel all in-flight fetch requests
3. `forceReleaseGenLock()` — Release gen lock
4. `radioEngine.stop()` + `clearBuffers()` — Stop audio
5. `stopStationBase()` in store — Clear state
6. Clear GPU holder

### `useRadioPlayback()` — Continuous Playback

**File:** [`frontend/src/hooks/use-radio-playback.ts`](frontend/src/hooks/use-radio-playback.ts)

Persistent hook that runs in AppShell (survives tab navigation). Handles:

#### Auto-generation (lines 189-200)
- Monitors `queue.length - currentIdx - 1` (remaining songs in queue)
- When `remaining < BUFFER_THRESHOLD (2)`, triggers `generateTrack()`
- Prevents multiple concurrent generations via `isGenLocked()` check

#### `generateTrack()` (lines 65-145)
1. Check active station and acquire gen lock
2. Get abort signal for this session
3. Set GPU holder, set `isGenerating = true`
4. `await generateNextTrack(stationId, signal)`
5. On success: Decode audio, queue song, increment counter
6. Auto-save to playlist if `radioAutoSave` enabled
7. On error (non-abort): Exponential backoff retry (`RETRY_DELAY_MS=8000`, doubles up to `MAX_RETRY_DELAY_MS=60000`)
8. On finally: Release lock, clear GPU holder

#### Song-ended handling (lines 162-186)
- Wires `radioEngine.onended` callback
- If `repeat === "one"`: Replay current song
- Otherwise: Call `playNext()` from player store, then play next if it has a cached buffer

#### Time updates (lines 148-159)
- Wires `radioEngine.ontimeupdate` → `playerStore.setCurrentTime(time)`

#### Ambient noise (lines 212-245)
- Two effects: one for station start/stop, one for store subscription
- Attaches `ambientNoise` to `radioEngine.audioContext`
- Reacts to `useAmbientStore` changes (effect type, volume, enabled)
- Stops ambient noise when station is stopped

### `radio-helpers.ts` — Shared Utilities

**File:** [`frontend/src/lib/audio/radio-helpers.ts`](frontend/src/lib/audio/radio-helpers.ts)

```typescript
// Constants
export const BUFFER_THRESHOLD = 2;     // Songs to keep in queue
export const RETRY_DELAY_MS = 8000;    // Initial retry delay
export const MAX_RETRY_DELAY_MS = 60000; // Max retry delay (60s)

// Generation lock
let _genLock = false;
acquireGenLock() → boolean      // Returns false if already locked
releaseGenLock()                // Releases lock
forceReleaseGenLock()           // Force release (used on stop)
isGenLocked() → boolean         // Check lock state

// Abort controller
let _abortController: AbortController | null = null;
createRadioAbortController() → AbortController  // Creates new, aborts old
abortRadioRequests()                          // Aborts current
getRadioSignal() → AbortSignal | undefined    // Get current signal

// Audio decoding
decodeAndCacheAudio(songId) → Promise<void>   // Fetch + decode + cache in engine
prefetchAudio(songId) → Promise<void>          // Silent decodeAndCacheAudio
```

---

## 10. Complete Request/Response Flow — Custom Station Playback

### Creating a Custom Station

```
UI (CreateStationDialog)
  → POST /radio/stations { name, genre, mood, caption_template, bpm_min, bpm_max, ... }
    → radio_service.create_station(data)
      → INSERT INTO radio_stations
      → INSERT INTO station_structures (if structure_ids provided)
      → SELECT newly created station
    → Returns StationResponse
  → invalidateQueries(["stations"])
```

### Playing a Custom Station (Full Flow)

```
User clicks station card
  ↓
useRadio.startStation(stationId)
  ↓
  ├─ abortRadioRequests() + forceReleaseGenLock()
  ├─ radioEngine.stop() + clearBuffers() + warmup()
  ├─ _sessionCounter++
  ├─ createRadioAbortController()
  ├─ startStation(stationId) in store
  └─ acquireGenLock() + setGPUHolder("radio")
  ↓
┌─ GENERATE SONG 1 (blocking) ──────────────────────┐
│ POST /radio/generate/{stationId}                    │
│   → set_radio_active(True)                          │
│   → generate_next_track():                          │
│     ├─ get_station()                                │
│     ├─ _generate_caption_with_llm() → caption       │
│     ├─ _generate_lyrics_with_llm() → lyrics         │
│     ├─ gpu_lock.await_acquire("radio")              │
│     ├─ Randomize BPM, duration                      │
│     ├─ generation_service.generate(params) → audio  │
│     ├─ _generate_title_with_llm() → title           │
│     ├─ gpu_lock.release("radio")                    │
│     └─ Save song to DB, copy audio file             │
│   → set_radio_active(False)                          │
│   → Returns { success: true, song: SongResponse }   │
└─────────────────────────────────────────────────────┘
  ↓
decodeAndCacheAudio(song1.id)     // Fetch FLAC, decode to AudioBuffer
radioEngine.play(song1.id)        // Play via AudioWorklet
play(song1) + setQueue([song1])   // Update player store
  ↓
┌─ GENERATE SONG 2 (pre-buffer, blocking) ───────────┐
│ Same pipeline as song 1                              │
└─────────────────────────────────────────────────────┘
  ↓
addToQueue(song2) + prefetchAudio(song2.id)
  ↓
releaseGenLock() + invalidateQueries()

┌────────────────────────────────────────────────────┐
│ useRadioPlayback (continuous, in AppShell)          │
│                                                     │
│ Effect: remaining < BUFFER_THRESHOLD? → generate   │
│ Effect: radioEngine.onended → play next / repeat   │
│ Effect: radioEngine.ontimeupdate → setCurrentTime  │
│ Effect: ambient noise start/stop + config          │
└────────────────────────────────────────────────────┘
```

---

## 11. WebSocket Usage

The radio system **does not use WebSocket** for its core operations. All communication is HTTP request/response.

- The WebSocket system (`generation_ws_manager`) is used by the **DJ service** for real-time generation progress updates (`progress`, `completed`, `failed`, `title` events)
- Radio uses synchronous blocking requests (`await generateNextTrack()`) since the frontend hook is already waiting for the result
- The `get_status()` endpoint (GET `/radio/status`) currently returns static data (`active_station_id: null`, `is_generating: false`, `songs_generated: 0`) — real-time status tracking was planned but not implemented for radio
- The `stop_radio()` endpoint (POST `/radio/stop`) is a stub returning `{"stopped": true}` — actual stopping is handled by the frontend hook's session invalidation pattern

---

## 12. Database Schema (Inferred from SQL)

### `radio_stations`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `name` | TEXT | Station name |
| `description` | TEXT | Station description (used in lyrics prompt) |
| `is_preset` | INTEGER (0/1) | Built-in vs custom |
| `caption_template` | TEXT | Fallback caption with `{mood}`, `{genre}` vars |
| `genre` | TEXT | Music genre |
| `mood` | TEXT | Mood/atmosphere |
| `instrumental` | INTEGER (0/1) | Has vocals or not |
| `vocal_language` | TEXT | Language for lyrics ("unknown" = instrumental) |
| `bpm_min` | INTEGER | Minimum BPM |
| `bpm_max` | INTEGER | Maximum BPM |
| `keyscale` | TEXT | Musical key/scale |
| `timesignature` | TEXT | Time signature (e.g., "4/4") |
| `duration_min` | FLOAT | Min duration in seconds |
| `duration_max` | FLOAT | Max duration in seconds |
| `advanced_params_json` | TEXT | JSON: theme_pool, lyrics_style_addons, intensity |
| `total_plays` | INTEGER | Generation count |
| `last_played_at` | TEXT (ISO) | Last generation timestamp |
| `created_at` | TEXT (ISO) | Creation timestamp |
| `updated_at` | TEXT (ISO) | Last update timestamp |

### `station_structures`
| Column | Type | Description |
|--------|------|-------------|
| `station_id` | TEXT (FK) | → radio_stations.id |
| `structure_id` | TEXT (FK) | → song_structures.id |

### `song_structures`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `name` | TEXT | Structure name |
| `genre` | TEXT | Associated genre |
| `template` | TEXT | Lyrics template with section headers |
| `is_system` | INTEGER (0/1) | System preset (undeletable) |
| `created_at` | TEXT (ISO) | Creation timestamp |
| `updated_at` | TEXT (ISO) | Last update timestamp |

### `radio_station_songs`
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key |
| `station_id` | TEXT (FK) | → radio_stations.id |
| `song_id` | TEXT (FK) | → songs.id |
| `position` | INTEGER | Position in station history |
| `generated_at` | TEXT (ISO) | Generation timestamp |

### `settings` (key-value store)
| Key | Value | Description |
|-----|-------|-------------|
| `radio_llm_provider` | string | Active LLM provider slug |
| `radio_llm_model` | string | Active model name |
| `radio_system_prompt` | string | Custom system prompt (empty = default) |
| `{provider}_api_key` | string | Stored API key per provider |
| `openai_compatible_api_base` | string | Custom API base URL |
| `vae_chunk_size` | string | VAE decode chunk size |
| `vae_sleep_ms` | string | VAE decode pause |
| `dit_sleep_ms` | string | DiT diffusion pause |
| `throttle_radio_only` | string | "true"/"false" |
| `dj_provider` | string | DJ LLM provider |
| `dj_model` | string | DJ model name |
| `dj_system_prompt` | string | DJ custom prompt |

### Related tables (used by radio)
- **`songs`**: Stores generated audio metadata (title, file_path, caption, lyrics, bpm, etc.)
- **`generation_history`**: Tracks generation jobs (status, params, results, timing)

---

## 13. Patch File

**File:** [`backend/src/patch_radio_service.py`](backend/src/patch_radio_service.py)

This is a **one-time migration script** (not part of the running application) that patches `radio_service.py` to add song structure support. Already applied to the current codebase.

### Changes Made:
1. Adds `SongStructureResponse` to imports
2. Modifies `list_stations()` to fetch structure associations from `station_structures` table for all stations at once
3. Modifies `get_station()` to load structure IDs per station
4. Modifies `create_station()` to insert structure links on creation
5. Modifies `update_station()` to handle `structure_ids` updates (delete old, insert new)

### Concerns:
- Uses string replacement — fragile and non-reentrant
- The `update_station` patch was noted as incomplete in the script itself (line 118 comment: "We need a regex or careful replacement here")
- Should be replaced with a proper DB migration if run again

---

## 14. Key Architectural Observations

### Strengths

1. **LLM-agnostic design**: Provider abstraction allows seamless swapping between local (MLX, Ollama) and cloud (OpenAI, Anthropic, custom) providers
2. **Graceful degradation**: Template-based fallback when LLM unavailable ensures the system always produces output
3. **GPU lock management**: `await_acquire()` for radio, `acquire()` for DJ — prevents concurrent MLX usage causing segfaults
4. **AudioWorklet isolation**: Browser-side audio playback isolated from main thread prevents stuttering during GPU-intensive generation
5. **Session management**: Monotonic session counter prevents race conditions when stopping/restarting stations
6. **Pre-buffering**: Generates 2 tracks ahead for seamless playback with `BUFFER_THRESHOLD = 2`
7. **GPU lock optimization**: Title generation runs under GPU lock (prevents MLX conflicts), but DB writes/file copies run without it
8. **Caption gen before GPU lock**: LLM caption/lyrics generation happens BEFORE acquiring GPU lock (network call shouldn't block GPU)
9. **Ambient effects**: Vinyl crackle, radio static, brown noise enhance the radio experience
10. **Throttle system**: Tunable VAE/DiT throttle with radio-only scope prevents audio stuttering on unified memory systems

### Areas for Improvement

1. **No WebSocket for radio**: Status endpoint returns static data; no real-time progress during generation. Users see no feedback during the potentially long generation process.
2. **`advanced_params_json` is opaque**: The JSON structure (`theme_pool`, `lyrics_style_addons`, `intensity`) is not documented in API types. Frontend components need to know the schema from source code.
3. **No preset stations visible**: The code references `is_preset` and orders by `is_preset DESC`, but no preset station definitions or seed data are included in the analyzed files.
4. **`RadioStatusResponse` not tracked**: Always returns zeros/nulls. The backend doesn't track which station is actively generating or the generation count.
5. **`stop_radio()` is a stub**: Returns `{"stopped": true}` without actually stopping anything. Real stopping is frontend-driven via session invalidation.
6. **Patch file not idempotent**: `patch_radio_service.py` uses string replacement which is fragile and non-reentrant.
7. **Title generation under GPU lock**: While necessary for preventing MLX conflicts, it adds latency to the GPU lock hold time. Could be moved to post-lock if MLX usage is properly managed.
8. **No max retry count**: Generation failures retry with exponential backoff (8s → 60s max) but no maximum retry count — could loop indefinitely.
9. **Lyrics generation has no system prompt**: Unlike caption/title generation, lyrics uses only a user message — no system-level guardrails for output format.
10. **`useRadioPlayback` auto-save silently fails**: The `autoSaveRadioTrack` function catches all errors silently. If playlist creation fails, the user has no indication.
11. **No queue limit**: The playback hook continuously adds songs to the queue. On a fast LLM + slow generation setup, the queue could grow very large with songs the user may never hear.
12. **Frontend gen lock is module-level**: The `_genLock` in `radio-helpers.ts` is a module-level variable — if the module is re-imported or the page reloads, the lock state is lost but in-flight requests may still exist.
