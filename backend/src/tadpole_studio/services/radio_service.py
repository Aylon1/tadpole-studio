"""
Radio station auto-generation service.

Inspired by:
- nalexand/ACE-Step-1.5-OPTIMIZED (MusicBox jukebox)
- PasiKoodaa/ACE-Step-RADIO (radio station mode with memory optimization)
"""

import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from tadpole_studio.db.connection import get_db
from tadpole_studio.models.radio import StationResponse, SongStructureResponse
from tadpole_studio.services.generation import generation_service
from tadpole_studio.services.gpu_lock import gpu_lock
from tadpole_studio.services.llm_provider import get_provider, get_all_providers

RADIO_DEFAULT_SYSTEM_PROMPT = """You are a music caption generator. Given station parameters, write a creative, \
detailed caption for an AI music generator. Describe instrumentation, texture, \
atmosphere, and sonic qualities. Be specific and varied — each caption should \
feel unique. Output ONLY the caption text, nothing else."""


def _row_to_station(row, structure_ids: Optional[list[str]] = None) -> StationResponse:
    return StationResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        is_preset=bool(row["is_preset"]),
        caption_template=row["caption_template"] or "",
        genre=row["genre"] or "",
        mood=row["mood"] or "",
        instrumental=bool(row["instrumental"]),
        vocal_language=row["vocal_language"] or "unknown",
        bpm_min=row["bpm_min"],
        bpm_max=row["bpm_max"],
        keyscale=row["keyscale"] or "",
        timesignature=row["timesignature"] or "",
        duration_min=row["duration_min"] or 30.0,
        duration_max=row["duration_max"] or 120.0,
        advanced_params_json=row["advanced_params_json"] or "{}",
        total_plays=row["total_plays"] or 0,
        last_played_at=row["last_played_at"],
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
        structure_ids=structure_ids or [],
    )


class RadioService:
    """Manages radio stations and auto-generation of tracks."""

    async def list_stations(self) -> list[StationResponse]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM radio_stations ORDER BY is_preset DESC, name ASC"
        )
        rows = await cursor.fetchall()
        return [_row_to_station(row) for row in rows]

    async def get_station(self, station_id: str) -> Optional[StationResponse]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM radio_stations WHERE id = ?", (station_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_station(row)

    async def create_station(self, data: dict[str, Any]) -> StationResponse:
        db = await get_db()
        station_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            """INSERT INTO radio_stations (
                id, name, description, is_preset, caption_template,
                genre, mood, instrumental, vocal_language,
                bpm_min, bpm_max, keyscale, timesignature,
                duration_min, duration_max, advanced_params_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                station_id,
                data.get("name", "Custom Station"),
                data.get("description", ""),
                data.get("caption_template", ""),
                data.get("genre", ""),
                data.get("mood", ""),
                1 if data.get("instrumental", True) else 0,
                data.get("vocal_language", "unknown"),
                data.get("bpm_min"),
                data.get("bpm_max"),
                data.get("keyscale", ""),
                data.get("timesignature", ""),
                data.get("duration_min", 30.0),
                data.get("duration_max", 120.0),
                data.get("advanced_params_json", "{}"),
                now,
                now,
            ),
        )
        await db.commit()

        station = await self.get_station(station_id)
        assert station is not None
        return station

    async def update_station(
        self, station_id: str, updates: dict[str, Any]
    ) -> Optional[StationResponse]:
        db = await get_db()

        # Check station exists and is not a preset (presets can't be edited)
        station = await self.get_station(station_id)
        if station is None:
            return None

        if not updates:
            return station

        structure_ids = updates.pop("structure_ids", None)

        if "instrumental" in updates:
            updates["instrumental"] = 1 if updates["instrumental"] else 0

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values())
            values.append(station_id)

            await db.execute(
                f"UPDATE radio_stations SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                values,
            )

        if structure_ids is not None:
            await db.execute("DELETE FROM station_structures WHERE station_id = ?", (station_id,))
            for struct_id in structure_ids:
                await db.execute(
                    "INSERT INTO station_structures (station_id, structure_id) VALUES (?, ?)",
                    (station_id, struct_id),
                )

        await db.commit()

        return await self.get_station(station_id)

    async def delete_station(self, station_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute(
            "SELECT is_preset FROM radio_stations WHERE id = ?", (station_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False
        if bool(row["is_preset"]):
            return False

        await db.execute("DELETE FROM radio_stations WHERE id = ?", (station_id,))
        await db.commit()
        return True

    async def create_station_from_song(
        self, song_id: str, name: Optional[str] = None
    ) -> Optional[StationResponse]:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM songs WHERE id = ?", (song_id,))
        row = await cursor.fetchone()
        if row is None:
            return None

        station_name = name or f"Station from {row['title']}"
        data = {
            "name": station_name,
            "description": f"Created from: {row['title']}",
            "genre": "",
            "mood": "",
            "instrumental": bool(row["instrumental"]),
            "vocal_language": row["vocal_language"] or "unknown",
            "bpm_min": row["bpm"] - 10 if row["bpm"] else None,
            "bpm_max": row["bpm"] + 10 if row["bpm"] else None,
            "keyscale": row["keyscale"] or "",
            "timesignature": row["timesignature"] or "",
            "caption_template": row["caption"] or "",
        }

        return await self.create_station(data)

    async def _ensure_api_key_loaded(self, provider_name: str) -> None:
        """Load stored API key for a provider if it doesn't have one from env vars."""
        provider = get_provider(provider_name)
        if not provider or not provider.requires_api_key:
            return
        if hasattr(provider, "has_api_key") and getattr(provider, "has_api_key", False):
            return

        db = await get_db()
        settings_key = f"{provider_name}_api_key"
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?", (settings_key,)
        )
        row = await cursor.fetchone()
        if row and hasattr(provider, "set_api_key"):
            getattr(provider, "set_api_key")(row["value"])

    async def get_settings(self) -> dict[str, Any]:
        """Get radio LLM settings and available providers."""
        db = await get_db()
        cursor = await db.execute(
            "SELECT key, value FROM settings WHERE key IN ("
            "'radio_llm_provider', 'radio_llm_model', 'radio_system_prompt', "
            "'openai_api_key', 'anthropic_api_key', 'openai_compatible_api_base')"
        )
        rows = await cursor.fetchall()
        active_provider = "none"
        active_model = ""
        custom_system_prompt = ""
        stored_api_keys: dict[str, str] = {}
        api_bases: dict[str, str] = {}
        for r in rows:
            if r["key"] == "radio_llm_provider":
                active_provider = r["value"]
            elif r["key"] == "radio_llm_model":
                active_model = r["value"]
            elif r["key"] == "radio_system_prompt":
                custom_system_prompt = r["value"]
            elif r["key"] == "openai_api_key":
                stored_api_keys["openai"] = r["value"]
            elif r["key"] == "anthropic_api_key":
                stored_api_keys["anthropic"] = r["value"]
            elif r["key"] == "openai_compatible_api_base":
                api_bases["openai-compatible"] = r["value"]

        # Apply stored API keys to providers that don't have an env var key
        for provider_name, stored_key in stored_api_keys.items():
            provider = get_provider(provider_name)
            if provider and hasattr(provider, "set_api_key") and not getattr(provider, "has_api_key", False):
                getattr(provider, "set_api_key")(stored_key)
                
        # Apply API base
        for provider_name, stored_base in api_bases.items():
            provider = get_provider(provider_name)
            if provider and hasattr(provider, "set_api_base") and not getattr(provider, "has_api_base", False):
                getattr(provider, "set_api_base")(stored_base)

        providers_info = []
        for name, provider in get_all_providers().items():
            available = await provider.is_available()
            has_api_base = False
            if name == "openai-compatible":
                has_api_base = name in api_bases

            providers_info.append({
                "name": name,
                "available": available,
                "requires_api_key": provider.requires_api_key,
                "models": await provider.list_models_async(),
                "has_stored_api_key": name in stored_api_keys,
                "has_api_base": has_api_base,
                "api_base": api_bases.get(name, ""),
                "package_installed": getattr(provider, "package_installed", True),
                "unavailable_reason": getattr(provider, "unavailable_reason", ""),
            })

        return {
            "providers": providers_info,
            "active_provider": active_provider,
            "active_model": active_model,
            "system_prompt": custom_system_prompt,
            "default_system_prompt": RADIO_DEFAULT_SYSTEM_PROMPT,
        }

    async def update_settings(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> dict[str, Any]:
        """Update radio LLM settings."""
        db = await get_db()
        if provider is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('radio_llm_provider', ?, datetime('now'))",
                (provider,),
            )
        if model is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('radio_llm_model', ?, datetime('now'))",
                (model,),
            )
        if system_prompt is not None:
            if system_prompt.strip() == "" or system_prompt.strip() == RADIO_DEFAULT_SYSTEM_PROMPT.strip():
                await db.execute(
                    "DELETE FROM settings WHERE key = 'radio_system_prompt'"
                )
            else:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('radio_system_prompt', ?, datetime('now'))",
                    (system_prompt,),
                )
        # Store API key for cloud providers
        if api_key is not None and provider is not None:
            llm_provider = get_provider(provider)
            if llm_provider and llm_provider.requires_api_key:
                settings_key = f"{provider}_api_key"
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (settings_key, api_key),
                )
                if hasattr(llm_provider, "set_api_key"):
                    getattr(llm_provider, "set_api_key")(api_key)
                    
        # Store API base for compatible providers
        if api_base is not None and provider == "openai-compatible":
            llm_provider = get_provider(provider)
            if llm_provider:
                settings_key = "openai_compatible_api_base"
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                    (settings_key, api_base),
                )
                if hasattr(llm_provider, "set_api_base"):
                    getattr(llm_provider, "set_api_base")(api_base)
                    
        await db.commit()
        return await self.get_settings()

    async def _get_radio_llm(self) -> tuple:
        """Read the configured radio LLM provider/model and return (provider, model_name, system_prompt).

        Fallback chain: configured provider -> Ollama -> None.
        """
        db = await get_db()
        cursor = await db.execute(
            "SELECT key, value FROM settings WHERE key IN ("
            "'radio_llm_provider', 'radio_llm_model', 'radio_system_prompt')"
        )
        rows = await cursor.fetchall()
        provider_name = "none"
        model_name = ""
        custom_prompt = ""
        for r in rows:
            if r["key"] == "radio_llm_provider":
                provider_name = r["value"]
            elif r["key"] == "radio_llm_model":
                model_name = r["value"]
            elif r["key"] == "radio_system_prompt":
                custom_prompt = r["value"]

        system_prompt = custom_prompt if custom_prompt.strip() else RADIO_DEFAULT_SYSTEM_PROMPT

        if provider_name and provider_name != "none":
            provider = get_provider(provider_name)
            if provider is not None:
                await self._ensure_api_key_loaded(provider_name)
                if await provider.is_available():
                    return (provider, model_name, system_prompt)
                logger.warning(f"Radio LLM provider '{provider_name}' unavailable, trying fallbacks")

        # Fallback to Ollama (e.g. on Windows where built-in MLX is unavailable, or none selected)
        if provider_name != "ollama":
            ollama = get_provider("ollama")
            if ollama is not None and await ollama.is_available():
                ollama_models = await ollama.list_models_async()
                if ollama_models:
                    logger.info(f"Radio LLM: falling back to ollama/{ollama_models[0]}")
                    return (ollama, ollama_models[0], system_prompt)

        return (None, "", system_prompt)

    async def _generate_caption_with_llm(self, station: StationResponse) -> Optional[str]:
        """Attempt to generate a caption using the configured LLM provider.

        Returns the generated caption string, or None to fall back to template.
        """
        provider, model_name, system_prompt = await self._get_radio_llm()
        if provider is None:
            logger.info("Radio caption: no LLM provider available, using template")
            return None

        logger.info(f"Radio caption: generating via {provider.name}/{model_name or 'default'}")

        # Build user message from station parameters
        parts = []
        if station.genre:
            parts.append(f"Genre: {station.genre}")
        if station.mood:
            parts.append(f"Mood: {station.mood}")
        parts.append(f"Instrumental: {'yes' if station.instrumental else 'no'}")
        if station.vocal_language and station.vocal_language != "unknown":
            parts.append(f"Vocal language: {station.vocal_language}")
        if station.bpm_min is not None and station.bpm_max is not None:
            parts.append(f"BPM range: {station.bpm_min}-{station.bpm_max}")
        if station.keyscale:
            parts.append(f"Key/scale: {station.keyscale}")
        if station.timesignature:
            parts.append(f"Time signature: {station.timesignature}")
        if station.caption_template:
            parts.append(f"Style reference: {station.caption_template}")

        user_message = "Generate a unique music caption for these station parameters:\n" + "\n".join(parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            caption = await provider.chat(messages, model_name, temperature=0.7)
            caption = caption.strip()
            if caption:
                logger.info(f"Radio LLM caption generated ({len(caption)} chars) via {provider.name}: {caption}")
                return caption
            return None
        except Exception as e:
            logger.warning(f"Radio LLM caption generation failed ({provider.name}): {e}")
            return None

    async def _generate_title_with_llm(
        self, station: StationResponse, caption: str, recent_titles: list[str]
    ) -> Optional[str]:
        """Generate a station-themed song title using the configured radio LLM.

        Returns the generated title, or None to fall back to random titles.
        """
        provider, model_name, _prompt = await self._get_radio_llm()
        if provider is None:
            logger.info("Radio title: no LLM provider available, using random title")
            return None

        logger.info(f"Radio title: generating via {provider.name}/{model_name or 'default'}")
        avoid_str = ""
        if recent_titles:
            avoid_str = (
                "\nDo NOT reuse any of these recent titles: "
                + ", ".join(f'"{t}"' for t in recent_titles[:10])
            )

        style_hint = ""
        if station.genre:
            style_hint += f"Genre: {station.genre}. "
        if station.mood:
            style_hint += f"Mood: {station.mood}. "

        messages = [
            {
                "role": "system",
                "content": (
                    "Generate a single creative song title (1-8 words) that fits the style "
                    "of the station and song described below. The title should evoke the "
                    "genre and mood — it can be poetic, atmospheric, or thematic. "
                    "Output ONLY the title, nothing else."
                    f"{avoid_str}"
                ),
            },
            {
                "role": "user",
                "content": f"Station: {station.name}\n{style_hint}Caption: {caption}",
            },
        ]

        try:
            import re
            raw = await provider.chat(messages, model=model_name, max_tokens=50, temperature=0.7)
            # Clean: strip think tags, quotes, trailing period
            cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            for line in cleaned.splitlines():
                line = line.strip()
                if line:
                    cleaned = line
                    break
            if len(cleaned) >= 2 and cleaned[0] in ('"', "'", "\u201c") and cleaned[-1] in ('"', "'", "\u201d"):
                cleaned = cleaned[1:-1].strip()
            cleaned = cleaned.rstrip(".")
            if len(cleaned) > 80:
                cleaned = cleaned[:77] + "..."
            if cleaned and cleaned not in recent_titles:
                logger.info(f"Radio LLM title generated: '{cleaned}' via {provider.name}")
                return cleaned
        except Exception as e:
            logger.warning(f"Radio LLM title generation failed ({provider.name}): {e}")

        return None

    async def _generate_lyrics_with_llm(
        self, station: StationResponse, caption: str
    ) -> str:
        """Generate lyrics for the station if it is not instrumental."""
        if station.instrumental:
            return ""

        provider, model_name, _prompt = await self._get_radio_llm()
        if provider is None:
            return ""

        logger.info(f"Radio lyrics: generating via {provider.name}/{model_name or 'default'}")
        
        # Parse advanced parameters
        advanced_params = {}
        try:
            advanced_params = json.loads(station.advanced_params_json) if station.advanced_params_json else {}
        except Exception:
            pass

        import random

        # Theme selection
        theme_pool = advanced_params.get("theme_pool", [])
        if not theme_pool:
            random_themes = [
                "heartbreak", "youthful rebellion", "changing seasons", "a late night drive", 
                "finding oneself", "overcoming adversity", "falling in love", "nostalgia",
                "a distant memory", "a fleeting moment", "the beauty of nature", "city life",
                "a quiet morning", "an epic journey", "betrayal", "hope for the future",
                "a secret romance", "dancing in the rain", "a farewell", "a new beginning"
            ]
            theme_pool = random_themes

        station_chosen_theme = random.choice(theme_pool)

        # Style and intensity
        lyrics_style_addons = advanced_params.get("lyrics_style_addons", "Standard style")
        intensity = advanced_params.get("intensity", "Moderate")

        # Duration and key
        duration_min = station.duration_min if station.duration_min else 30.0
        duration_max = station.duration_max if station.duration_max else 120.0
        station_duration = round(random.uniform(duration_min, duration_max))
        station_keyscale = station.keyscale if station.keyscale else "Any key"

        # Structure selection
        station_chosen_structure = "[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n[Bridge]\n[Chorus]\n[Outro]"
        if station.structure_ids:
            # Fetch structures
            db = await get_db()
            placeholders = ",".join("?" for _ in station.structure_ids)
            cursor = await db.execute(f"SELECT template FROM song_structures WHERE id IN ({placeholders})", station.structure_ids)
            struct_rows = await cursor.fetchall()
            if struct_rows:
                struct_rows_list = list(struct_rows)
                chosen_row = random.choice(struct_rows_list)
                station_chosen_structure = chosen_row["template"]

        vocal_lang = station.vocal_language if station.vocal_language and station.vocal_language != "unknown" else "English"
        genre = station.genre if station.genre else "Pop"
        mood = station.mood if station.mood else "Standard"

        prompt_text = (
            f"Write a {genre} song in {vocal_lang} about '{station_chosen_theme}' using this exact structure:\n"
            f"{station_chosen_structure}\n\n"
            "STRICT REQUIREMENTS:\n"
            "1. Write ONLY the song lyrics - no translations, no explanations, no notes\n"
            f"2. Use ONLY the specified language: {vocal_lang}\n"
            "3. Follow the structure EXACTLY as shown\n"
            "4. Format each section header exactly as shown (e.g. [Verse 1])\n"
            "5. Never include any text outside the lyrics structure\n"
            f"6. Target Duration: {station_duration}s\n"
            f"7. Musical Key: {station_keyscale}\n\n"
            "STYLE GUIDELINES:\n"
            f"- {lyrics_style_addons}\n"
            f"- {intensity} feel\n"
            f"- {mood} mood\n"
            f"- Concept/Description: {station.description}\n"
            "- Use vivid imagery and emotional resonance\n"
            f"- Match the rhythm and phrasing to {genre} conventions\n\n"
            "BACKGROUND VIBE/CAPTION (For Optional Context):\n"
            f"{caption}\n\n"
        )

        messages = [
            {
                "role": "user",
                "content": prompt_text,
            },
        ]

        try:
            import re
            raw = await provider.chat(messages, model=model_name, max_tokens=800, temperature=0.8)
            logger.info(f"Radio LLM raw lyrics output:\n{raw}")
            cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            if cleaned:
                logger.info(f"Radio LLM lyrics generated via {provider.name}:\n{cleaned[:100]}...")
                return cleaned
        except Exception as e:
            logger.warning(f"Radio LLM lyrics generation failed ({provider.name}): {e}")

        return ""

    async def generate_next_track(self, station_id: str) -> dict[str, Any]:
        """Generate the next track for a radio station.

        Returns the generation result dict with song info on success,
        or an error dict on failure.
        """
        station = await self.get_station(station_id)
        if station is None:
            return {"success": False, "error": "Station not found"}

        logger.info(f"Radio: generating next track for station '{station.name}' (id={station_id})")

        if not generation_service.dit_initialized:
            return {"success": False, "error": "DiT model not loaded"}

        # Try LLM caption generation BEFORE GPU lock (it's a network call)
        llm_caption = await self._generate_caption_with_llm(station)
        
        # Resolve caption now so we can generate lyrics for it
        caption = llm_caption
        if not caption:
            caption = station.caption_template
            if caption and station.mood and station.genre:
                caption = caption.replace("{mood}", station.mood).replace("{genre}", station.genre)
            elif not caption:
                tpl_parts = []
                if station.genre:
                    tpl_parts.append(station.genre)
                if station.mood:
                    tpl_parts.append(f"{station.mood} mood")
                caption = f"A {' '.join(tpl_parts)} track" if tpl_parts else "A music track"

        llm_lyrics = await self._generate_lyrics_with_llm(station, caption)

        # Wait for GPU availability (radio can afford to wait for prior generation)
        acquired = await gpu_lock.await_acquire("radio")
        if not acquired:
            return {
                "success": False,
                "error": "GPU lock timeout. Please try again.",
            }

        history_id: str | None = None
        song_title: str | None = None
        try:
            # Randomize within station ranges for variety
            bpm = None
            if station.bpm_min is not None and station.bpm_max is not None:
                bpm = random.randint(station.bpm_min, station.bpm_max)
            elif station.bpm_min is not None:
                bpm = station.bpm_min

            duration = random.uniform(station.duration_min, station.duration_max)

            # Parse advanced params
            advanced = {}
            if station.advanced_params_json:
                try:
                    advanced = json.loads(station.advanced_params_json)
                except json.JSONDecodeError:
                    pass

            params_dict: dict[str, Any] = {
                "task_type": "text2music",
                "caption": caption,
                "lyrics": llm_lyrics,
                "instrumental": station.instrumental,
                "vocal_language": station.vocal_language,
                "duration": duration,
                "batch_size": 1,
                **advanced,
            }
            if bpm is not None:
                params_dict["bpm"] = bpm
            if station.keyscale:
                params_dict["keyscale"] = station.keyscale
            if station.timesignature:
                params_dict["timesignature"] = station.timesignature

            # Create generation history entry
            history_id = str(uuid.uuid4())
            started_at = datetime.now(timezone.utc)
            db = await get_db()
            await db.execute(
                """INSERT INTO generation_history (id, task_type, status, params_json, started_at, created_at)
                   VALUES (?, 'text2music', 'running', ?, ?, ?)""",
                (history_id, json.dumps(params_dict), started_at.isoformat(), started_at.isoformat()),
            )
            await db.commit()

            result = await generation_service.generate(params_dict)

            # Generate title BEFORE releasing GPU lock to avoid concurrent MLX
            # usage with the next track's generation (same pattern as DJ service).
            if result.get("success") and result.get("audios"):
                from tadpole_studio.services.title_generator import generate_random_title

                db = await get_db()
                recent_cursor = await db.execute(
                    """SELECT s.title FROM songs s
                       JOIN radio_station_songs rs ON s.id = rs.song_id
                       WHERE rs.station_id = ?
                       ORDER BY rs.generated_at DESC LIMIT 10""",
                    (station_id,),
                )
                recent_rows = await recent_cursor.fetchall()
                recent_titles = [r["title"] for r in recent_rows if r["title"]]

                # Try LLM-based title (station-themed) first, fall back to random
                song_title = await self._generate_title_with_llm(
                    station, caption, recent_titles,
                )
                if song_title is None:
                    song_title = await generate_random_title(
                        avoid_titles=recent_titles,
                    )
        except Exception as e:
            logger.exception(f"Radio generation failed for station {station_id}")
            if history_id is not None:
                try:
                    db = await get_db()
                    await db.execute(
                        "UPDATE generation_history SET status = 'failed', error_message = ? WHERE id = ?",
                        (str(e), history_id),
                    )
                    await db.commit()
                except Exception:
                    pass
            return {"success": False, "error": str(e)}
        finally:
            # Release GPU lock after DiT + title gen so other consumers
            # (Create tab, DJ) can acquire it. DB writes/file copies don't need GPU.
            await gpu_lock.release("radio")

        # --- Post-generation work (DB writes, file copies) runs WITHOUT the GPU lock ---
        try:
            if result.get("success"):
                audios = result.get("audios", [])
                if audios:
                    audio = audios[0]

                    completed_at = datetime.now(timezone.utc)
                    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                    audio_results = [{"path": a.get("path", ""), "key": a.get("key", ""), "sample_rate": a.get("sample_rate", 48000)} for a in audios]
                    db = await get_db()

                    # Auto-save to library
                    from tadpole_studio.routers.songs import _row_to_song
                    from tadpole_studio.models.common import SongResponse as SongResp

                    song_id = str(uuid.uuid4())
                    now = datetime.now(timezone.utc).isoformat()
                    audio_path = audio.get("path", "")
                    file_format = audio_path.rsplit(".", 1)[-1] if "." in audio_path else "flac"

                    # Title was generated under GPU lock above; fallback if needed
                    if song_title is None:
                        song_title = f"Radio Track {datetime.now(timezone.utc).strftime('%H:%M')}"

                    # Update history as completed (now includes title)
                    await db.execute(
                        """UPDATE generation_history
                           SET status = 'completed', title = ?, result_json = ?,
                               audio_count = ?, completed_at = ?, duration_ms = ?
                           WHERE id = ?""",
                        (song_title, json.dumps(audio_results), len(audios),
                         completed_at.isoformat(), duration_ms, history_id),
                    )
                    await db.commit()

                    # Copy to library
                    import shutil
                    from pathlib import Path
                    from tadpole_studio.config import settings

                    src = Path(audio_path)
                    dest_filename = f"{song_id}.{file_format}"
                    dest = settings.AUDIO_DIR / dest_filename

                    if src.exists():
                        shutil.copy2(str(src), str(dest))
                        file_size = dest.stat().st_size
                    else:
                        file_size = 0

                    db = await get_db()
                    await db.execute(
                        """INSERT INTO songs (
                            id, title, file_path, file_format, duration_seconds,
                            caption, lyrics, bpm, keyscale, timesignature,
                            vocal_language, instrumental, generation_history_id,
                            tags, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            song_id,
                            song_title,
                            dest_filename,
                            file_format,
                            duration,
                            caption,
                            llm_lyrics,
                            bpm,
                            station.keyscale,
                            station.timesignature,
                            station.vocal_language,
                            1 if station.instrumental else 0,
                            history_id,
                            "radio",
                            now,
                            now,
                        ),
                    )

                    # Link to station
                    link_id = str(uuid.uuid4())
                    await db.execute(
                        """INSERT INTO radio_station_songs (id, station_id, song_id, position, generated_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (link_id, station_id, song_id, 0, now),
                    )

                    # Update station play count
                    await db.execute(
                        """UPDATE radio_stations
                           SET total_plays = total_plays + 1, last_played_at = ?
                           WHERE id = ?""",
                        (now, station_id),
                    )
                    await db.commit()

                    song_response = SongResp(
                        id=song_id,
                        title=song_title,
                        file_path=dest_filename,
                        file_format=file_format,
                        duration_seconds=duration,
                        caption=caption,
                        bpm=bpm,
                        keyscale=station.keyscale,
                        timesignature=station.timesignature,
                        vocal_language=station.vocal_language,
                        instrumental=station.instrumental,
                        created_at=now,
                        updated_at=now,
                    )

                    return {
                        "success": True,
                        "song": song_response.model_dump(),
                    }

            error = result.get("error", "Generation failed")
            db = await get_db()
            await db.execute(
                "UPDATE generation_history SET status = 'failed', error_message = ? WHERE id = ?",
                (error, history_id),
            )
            await db.commit()
            return {"success": False, "error": error}

        except Exception as e:
            logger.exception(f"Radio post-generation failed for station {station_id}")
            return {"success": False, "error": str(e)}

    async def get_station_songs(
        self, station_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        db = await get_db()
        cursor = await db.execute(
            """SELECT s.* FROM songs s
               JOIN radio_station_songs rs ON s.id = rs.song_id
               WHERE rs.station_id = ?
               ORDER BY rs.generated_at DESC
               LIMIT ?""",
            (station_id, limit),
        )
        rows = await cursor.fetchall()
        from tadpole_studio.routers.songs import _row_to_song

        return [_row_to_song(row).model_dump() for row in rows]

    async def list_structures(self) -> list[SongStructureResponse]:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM song_structures ORDER BY name ASC")
        rows = await cursor.fetchall()
        return [SongStructureResponse(**row) for row in rows]

    async def get_structure(self, structure_id: str) -> Optional[SongStructureResponse]:
        db = await get_db()
        cursor = await db.execute("SELECT * FROM song_structures WHERE id = ?", (structure_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return SongStructureResponse(**row)

    async def create_structure(self, data: dict[str, Any]) -> SongStructureResponse:
        db = await get_db()
        structure_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        await db.execute(
            """INSERT INTO song_structures (id, name, genre, template, is_system, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                structure_id,
                data.get("name"),
                data.get("genre", ""),
                data.get("template"),
                1 if data.get("is_system") else 0,
                now,
                now,
            )
        )
        await db.commit()
        struct = await self.get_structure(structure_id)
        assert struct is not None
        return struct

    async def update_structure(self, structure_id: str, data: dict[str, Any]) -> Optional[SongStructureResponse]:
        db = await get_db()
        struct = await self.get_structure(structure_id)
        if struct is None:
            return None
            
        if not data:
            return struct
            
        if "is_system" in data:
            data["is_system"] = 1 if data["is_system"] else 0
            
        set_clause = ", ".join(f"{k} = ?" for k in data)
        values = list(data.values())
        values.append(structure_id)
        
        await db.execute(
            f"UPDATE song_structures SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values
        )
        await db.commit()
        return await self.get_structure(structure_id)

    async def delete_structure(self, structure_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute("SELECT is_system FROM song_structures WHERE id = ?", (structure_id,))
        row = await cursor.fetchone()
        if row is None:
            return False
        if bool(row["is_system"]):
            return False
            
        await db.execute("DELETE FROM song_structures WHERE id = ?", (structure_id,))
        await db.commit()
        return True


radio_service = RadioService()
