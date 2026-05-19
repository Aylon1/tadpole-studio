SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS songs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_format TEXT NOT NULL DEFAULT 'flac',
    duration_seconds REAL,
    sample_rate INTEGER DEFAULT 48000,
    file_size_bytes INTEGER,
    caption TEXT DEFAULT '',
    lyrics TEXT DEFAULT '',
    bpm INTEGER,
    keyscale TEXT DEFAULT '',
    timesignature TEXT DEFAULT '',
    vocal_language TEXT DEFAULT 'unknown',
    instrumental INTEGER DEFAULT 0,
    is_favorite INTEGER DEFAULT 0,
    rating INTEGER DEFAULT 0,
    tags TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    parent_song_id TEXT,
    generation_history_id TEXT,
    variation_index INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_song_id) REFERENCES songs(id) ON DELETE SET NULL,
    FOREIGN KEY (generation_history_id) REFERENCES generation_history(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS generation_history (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL DEFAULT 'text2music',
    status TEXT NOT NULL DEFAULT 'pending',
    title TEXT,
    params_json TEXT DEFAULT '{}',
    result_json TEXT DEFAULT '{}',
    audio_count INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    icon TEXT DEFAULT 'ListMusic',
    cover_song_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cover_song_id) REFERENCES songs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS playlist_songs (
    id TEXT PRIMARY KEY,
    playlist_id TEXT NOT NULL,
    song_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(playlist_id, song_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS radio_stations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_preset INTEGER DEFAULT 0,
    caption_template TEXT DEFAULT '',
    genre TEXT DEFAULT '',
    mood TEXT DEFAULT '',
    instrumental INTEGER DEFAULT 1,
    vocal_language TEXT DEFAULT 'unknown',
    bpm_min INTEGER,
    bpm_max INTEGER,
    keyscale TEXT DEFAULT '',
    timesignature TEXT DEFAULT '',
    duration_min REAL DEFAULT 30.0,
    duration_max REAL DEFAULT 120.0,
    advanced_params_json TEXT DEFAULT '{}',
    total_plays INTEGER DEFAULT 0,
    last_played_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS radio_station_songs (
    id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL REFERENCES radio_stations(id) ON DELETE CASCADE,
    song_id TEXT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dj_conversations (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT 'New Conversation',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dj_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES dj_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    generation_params_json TEXT,
    generation_job_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS custom_themes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    css TEXT NOT NULL,
    color_scheme TEXT NOT NULL DEFAULT 'dark',
    preview_bg TEXT NOT NULL DEFAULT '#1a1a2e',
    preview_sidebar TEXT NOT NULL DEFAULT '#151527',
    preview_primary TEXT NOT NULL DEFAULT '#8b5cf6',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS song_structures (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    genre TEXT DEFAULT '',
    template TEXT NOT NULL,
    is_system INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS station_structures (
    station_id TEXT NOT NULL REFERENCES radio_stations(id) ON DELETE CASCADE,
    structure_id TEXT NOT NULL REFERENCES song_structures(id) ON DELETE CASCADE,
    PRIMARY KEY (station_id, structure_id)
);

CREATE INDEX IF NOT EXISTS idx_songs_created_at ON songs(created_at);
CREATE INDEX IF NOT EXISTS idx_songs_is_favorite ON songs(is_favorite);
CREATE INDEX IF NOT EXISTS idx_songs_rating ON songs(rating);
CREATE INDEX IF NOT EXISTS idx_songs_parent_song_id ON songs(parent_song_id);
CREATE INDEX IF NOT EXISTS idx_generation_history_created_at ON generation_history(created_at);
CREATE INDEX IF NOT EXISTS idx_generation_history_status ON generation_history(status);
CREATE INDEX IF NOT EXISTS idx_playlist_songs_playlist_id ON playlist_songs(playlist_id);
CREATE INDEX IF NOT EXISTS idx_playlist_songs_position ON playlist_songs(playlist_id, position);
CREATE INDEX IF NOT EXISTS idx_songs_generation_history_id ON songs(generation_history_id);
CREATE INDEX IF NOT EXISTS idx_songs_updated_at ON songs(updated_at);
CREATE INDEX IF NOT EXISTS idx_songs_title ON songs(title);
CREATE INDEX IF NOT EXISTS idx_songs_duration_seconds ON songs(duration_seconds);
CREATE INDEX IF NOT EXISTS idx_songs_bpm ON songs(bpm);
CREATE INDEX IF NOT EXISTS idx_generation_history_task_type ON generation_history(task_type);
CREATE INDEX IF NOT EXISTS idx_radio_stations_is_preset ON radio_stations(is_preset);
CREATE INDEX IF NOT EXISTS idx_radio_station_songs_station_id ON radio_station_songs(station_id);
CREATE INDEX IF NOT EXISTS idx_dj_conversations_updated_at ON dj_conversations(updated_at);
CREATE INDEX IF NOT EXISTS idx_dj_messages_conversation_id ON dj_messages(conversation_id);
"""

import sys

DEFAULT_SETTINGS = {
    "dit_model": "acestep-v15-turbo",
    "lm_model": "acestep-5Hz-lm-1.7B",
    "lm_backend": "mlx" if sys.platform == "darwin" else "nano-vllm",
    "device": "auto",
    "audio_format": "flac",
    "batch_size": "2",
    "inference_steps": "8",
    "guidance_scale": "7.0",
    "thinking": "true",
    "dj_provider": "built-in",
    "dj_model": "Qwen2.5-1.5B-Instruct-4bit",
    "vae_chunk_size": "128",
    "vae_sleep_ms": "200",
    "dit_sleep_ms": "200",
    "throttle_radio_only": "true",
    "active_backend": "ace-step",
    "heartmula_model_path": "",
    "heartmula_version": "3B",
    "heartmula_lazy_load": "false",
    "heartmula_temperature": "1.0",
    "heartmula_topk": "50",
    "heartmula_cfg_scale": "1.5",
}

RADIO_PRESETS = [
    {
        "name": "Lo-Fi Chill",
        "description": "Relaxing lo-fi beats for studying or unwinding",
        "genre": "lo-fi hip-hop",
        "mood": "chill, relaxed, mellow",
        "instrumental": True,
        "bpm_min": 70,
        "bpm_max": 90,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} track with warm textures and gentle rhythms",
    },
    {
        "name": "Jazz Club",
        "description": "Smooth jazz vibes from a late-night club",
        "genre": "jazz",
        "mood": "smooth, sophisticated, warm",
        "instrumental": True,
        "bpm_min": 90,
        "bpm_max": 140,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} piece with expressive melodies and rich harmonies",
    },
    {
        "name": "EDM Energy",
        "description": "High-energy electronic dance music",
        "genre": "EDM",
        "mood": "energetic, uplifting, powerful",
        "instrumental": True,
        "bpm_min": 125,
        "bpm_max": 140,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} track with driving beats and soaring synths",
    },
    {
        "name": "Classical Piano",
        "description": "Beautiful solo piano compositions",
        "genre": "classical piano",
        "mood": "elegant, emotional, beautiful",
        "instrumental": True,
        "bpm_min": 60,
        "bpm_max": 120,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} piece with expressive dynamics and flowing melodies",
    },
    {
        "name": "Ambient",
        "description": "Atmospheric ambient soundscapes",
        "genre": "ambient",
        "mood": "atmospheric, dreamy, ethereal",
        "instrumental": True,
        "bpm_min": 60,
        "bpm_max": 80,
        "duration_min": 90.0,
        "duration_max": 120.0,
        "caption_template": "An {mood} {genre} soundscape with lush textures and subtle movement",
    },
    {
        "name": "Hip-Hop",
        "description": "Hard-hitting hip-hop beats and flows",
        "genre": "hip-hop",
        "mood": "confident, bold, rhythmic",
        "instrumental": True,
        "bpm_min": 80,
        "bpm_max": 100,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} track with punchy drums and deep bass",
    },
    {
        "name": "Pop",
        "description": "Catchy pop music with hooks",
        "genre": "pop",
        "mood": "catchy, upbeat, bright",
        "instrumental": True,
        "bpm_min": 100,
        "bpm_max": 130,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} song with memorable melodies and modern production",
    },
    {
        "name": "R&B",
        "description": "Soulful R&B grooves",
        "genre": "R&B",
        "mood": "soulful, smooth, groovy",
        "instrumental": True,
        "bpm_min": 65,
        "bpm_max": 100,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} track with lush chords and silky grooves",
    },
    {
        "name": "Rock",
        "description": "Guitar-driven rock energy",
        "genre": "rock",
        "mood": "powerful, raw, energetic",
        "instrumental": True,
        "bpm_min": 110,
        "bpm_max": 150,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "A {mood} {genre} track with distorted guitars and driving drums",
    },
    {
        "name": "Metal",
        "description": "Heavy metal intensity",
        "genre": "metal",
        "mood": "aggressive, intense, heavy",
        "instrumental": True,
        "bpm_min": 120,
        "bpm_max": 180,
        "duration_min": 60.0,
        "duration_max": 120.0,
        "caption_template": "An {mood} {genre} track with crushing riffs and thunderous percussion",
    },
    {
        "name": "Medievalcore",
        "description": "Bardcore and tavernwave — medieval instruments meet modern songwriting",
        "genre": "medievalcore, bardcore, tavernwave",
        "mood": "chill",
        "instrumental": False,
        "bpm_min": 60,
        "bpm_max": 130,
        "duration_min": 60.0,
        "duration_max": 180.0,
        "caption_template": "Music as if played in medieval times, using instruments like lutes, harps, flutes",
    },
]
