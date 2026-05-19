"""
AI DJ chat service — translates natural language into music generation.

Inspired by:
- clockworksquirrel/ace-step-apple-silicon (conversational AI DJ interface)
"""

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from tadpole_studio.db.connection import get_db
from tadpole_studio.services.llm_provider import get_provider, get_all_providers

DEFAULT_SYSTEM_PROMPT = """You are an AI DJ assistant for Tadpole Studio, a music generation app powered by ACE-Step.

Your job is to help users create music through natural conversation. When a user describes music they want to hear, you should:

1. Respond conversationally and enthusiastically about their music request
2. Include a JSON code block with generation parameters when you want to generate music

The JSON block should use this format:
```json
{
  "caption": "A description of the music to generate",
  "lyrics": "",
  "instrumental": true,
  "bpm": 120,
  "keyscale": "",
  "timesignature": "4/4",
  "duration": 60,
  "vocal_language": "unknown"
}
```

Parameter guidelines:
- caption: Descriptive text about the music style, mood, instruments (be detailed and vivid)
- lyrics: Song lyrics with standard structure. For vocal tracks, write at least 2 verses and a chorus (12+ lines). Use [verse], [chorus], [bridge] tags. Example:
  "[verse]\\nFirst verse lines here\\n[chorus]\\nChorus lines here\\n[verse]\\nSecond verse lines here\\n[chorus]\\nChorus lines here"
- instrumental: true for no vocals, false for vocal tracks
- bpm: Beats per minute (60-200 typical range)
- keyscale: Musical key (e.g., "C major", "A minor", leave empty if unsure)
- timesignature: Time signature (e.g., "4/4", "3/4", "6/8")
- duration: Length in seconds (60-120 recommended, use 90+ for songs with lyrics)
- vocal_language: Language for vocals ("english", "unknown" for instrumental)

You can also handle these commands:
- "skip" or "next" → respond with: [ACTION:SKIP]
- "replay" or "play again" → respond with: [ACTION:REPLAY]
- "save" or "save to library" → respond with: [ACTION:SAVE]
- "create a radio station like this" → respond with: [ACTION:CREATE_STATION]

Be creative, knowledgeable about music genres, and enthusiastic. Keep responses concise but engaging."""


def _extract_json_block(text: str) -> Optional[dict[str, Any]]:
    """Extract the first JSON code block from LLM response text."""
    pattern = r"```json\s*\n?(.*?)\n?\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON block from DJ response")
    return None


def _extract_action(text: str) -> Optional[str]:
    """Extract an action command from the response."""
    pattern = r"\[ACTION:(\w+)\]"
    match = re.search(pattern, text)
    if match:
        return match.group(1).lower()
    return None


class DJService:
    """Manages AI DJ conversations and music generation from chat."""

    async def _ensure_api_key_loaded(self, provider_name: str) -> None:
        """Load stored API key for a provider if it doesn't have one from env vars."""
        provider = get_provider(provider_name)
        if not provider:
            return
            
        db = await get_db()
        
        if provider_name == "openai-compatible":
            if hasattr(provider, "set_api_base") and not getattr(provider, "has_api_base", False):
                cursor = await db.execute("SELECT value FROM settings WHERE key = 'openai_compatible_api_base'")
                row = await cursor.fetchone()
                if row:
                    getattr(provider, "set_api_base")(row["value"])
            return

        if not provider.requires_api_key:
            return
            
        if hasattr(provider, "has_api_key") and getattr(provider, "has_api_key", False):
            return

        settings_key = f"{provider_name}_api_key"
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?", (settings_key,)
        )
        row = await cursor.fetchone()
        if row and hasattr(provider, "set_api_key"):
            getattr(provider, "set_api_key")(row["value"])

    async def list_conversations(self) -> list[dict[str, Any]]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM dj_conversations ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"] or "",
                "updated_at": row["updated_at"] or "",
            }
            for row in rows
        ]

    async def create_conversation(self, title: str = "New Conversation") -> dict[str, Any]:
        db = await get_db()
        conv_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO dj_conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now),
        )
        await db.commit()

        return {
            "id": conv_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }

    async def get_conversation(self, conv_id: str) -> Optional[dict[str, Any]]:
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM dj_conversations WHERE id = ?", (conv_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        msg_cursor = await db.execute(
            "SELECT * FROM dj_messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conv_id,),
        )
        msg_rows = await msg_cursor.fetchall()

        messages = [
            {
                "id": m["id"],
                "conversation_id": m["conversation_id"],
                "role": m["role"],
                "content": m["content"],
                "generation_params_json": m["generation_params_json"],
                "generation_job_id": m["generation_job_id"],
                "created_at": m["created_at"] or "",
            }
            for m in msg_rows
        ]

        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"] or "",
            "updated_at": row["updated_at"] or "",
            "messages": messages,
        }

    async def delete_conversation(self, conv_id: str) -> bool:
        db = await get_db()
        cursor = await db.execute(
            "SELECT id FROM dj_conversations WHERE id = ?", (conv_id,)
        )
        if await cursor.fetchone() is None:
            return False

        await db.execute("DELETE FROM dj_conversations WHERE id = ?", (conv_id,))
        await db.commit()
        return True

    async def send_message(
        self, conv_id: str, user_content: str
    ) -> dict[str, Any]:
        """Process a user message through the LLM and optionally trigger generation."""
        db = await get_db()

        # Verify conversation exists
        cursor = await db.execute(
            "SELECT id FROM dj_conversations WHERE id = ?", (conv_id,)
        )
        if await cursor.fetchone() is None:
            return {"error": "Conversation not found"}

        # Save user message
        user_msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO dj_messages (id, conversation_id, role, content, created_at)
               VALUES (?, ?, 'user', ?, ?)""",
            (user_msg_id, conv_id, user_content, now),
        )

        # Load conversation history
        msg_cursor = await db.execute(
            """SELECT role, content FROM dj_messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (conv_id,),
        )
        msg_rows = await msg_cursor.fetchall()

        # Read custom system prompt from settings
        prompt_cursor = await db.execute(
            "SELECT value FROM settings WHERE key = 'dj_system_prompt'"
        )
        prompt_row = await prompt_cursor.fetchone()
        system_prompt = prompt_row["value"] if prompt_row else DEFAULT_SYSTEM_PROMPT

        # Build messages for LLM
        llm_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        for m in msg_rows:
            llm_messages.append({"role": m["role"], "content": m["content"]})

        # Get active provider
        provider_name = "built-in"
        model_name = "Qwen2.5-1.5B-Instruct-4bit"

        settings_cursor = await db.execute(
            "SELECT key, value FROM settings WHERE key IN ('dj_provider', 'dj_model')"
        )
        settings_rows = await settings_cursor.fetchall()
        for s in settings_rows:
            if s["key"] == "dj_provider":
                provider_name = s["value"]
            elif s["key"] == "dj_model":
                model_name = s["value"]

        provider = get_provider(provider_name)
        if provider is None:
            return {"error": f"LLM provider '{provider_name}' not found"}

        # Load stored API key if the provider needs one and doesn't have it yet
        await self._ensure_api_key_loaded(provider_name)

        fallback_notice: str | None = None

        available = await provider.is_available()
        if not available:
            fell_back = False

            # Try built-in (works on macOS with MLX)
            if provider_name != "built-in":
                builtin = get_provider("built-in")
                if builtin and await builtin.is_available():
                    fallback_notice = f"Provider '{provider_name}' was unavailable — responded using built-in model instead."
                    logger.info(f"Provider '{provider_name}' unavailable, falling back to built-in")
                    provider = builtin
                    provider_name = "built-in"
                    model_name = "Qwen2.5-1.5B-Instruct-4bit"
                    fell_back = True

            # Try Ollama (works on Windows/Linux if installed)
            if not fell_back and provider_name != "ollama":
                ollama = get_provider("ollama")
                if ollama and await ollama.is_available():
                    ollama_models = await ollama.list_models_async()
                    if ollama_models:
                        fallback_notice = f"Provider '{provider_name}' was unavailable — responded using Ollama instead."
                        logger.info(f"Provider '{provider_name}' unavailable, falling back to Ollama")
                        provider = ollama
                        provider_name = "ollama"
                        model_name = ollama_models[0]
                        fell_back = True

            if not fell_back:
                if sys.platform != "darwin":
                    return {
                        "error": (
                            "The AI DJ requires a language model. On Windows/Linux, either "
                            "install Ollama (https://ollama.com) and pull a model (e.g. "
                            "'ollama pull qwen2.5:1.5b'), or configure an API key (OpenAI / "
                            "Anthropic) in DJ Settings."
                        ),
                    }
                return {
                    "error": f"LLM provider '{provider_name}' is not available. Check your configuration.",
                }

        # Call LLM (with fallback to built-in on failure)
        try:
            response_text = await provider.chat(llm_messages, model_name)
        except Exception as e:
            # If a non-built-in provider fails, try falling back to built-in then Ollama
            fell_back_on_error = False

            if provider_name != "built-in":
                builtin = get_provider("built-in")
                if builtin and await builtin.is_available():
                    logger.warning(f"Provider '{provider_name}' failed ({e}), falling back to built-in")
                    try:
                        response_text = await builtin.chat(llm_messages, "Qwen2.5-1.5B-Instruct-4bit")
                        fell_back_on_error = True
                        fallback_notice = f"Provider '{provider_name}' failed ({e}) — responded using built-in model instead."
                        await self.update_settings(provider="built-in", model="Qwen2.5-1.5B-Instruct-4bit")
                    except Exception as e2:
                        logger.warning(f"Built-in fallback also failed: {e2}")

            if not fell_back_on_error and provider_name != "ollama":
                ollama = get_provider("ollama")
                if ollama and await ollama.is_available():
                    ollama_models = await ollama.list_models_async()
                    if ollama_models:
                        logger.warning(f"Provider '{provider_name}' failed ({e}), falling back to Ollama")
                        try:
                            response_text = await ollama.chat(llm_messages, ollama_models[0])
                            fell_back_on_error = True
                            fallback_notice = f"Provider '{provider_name}' failed ({e}) — responded using Ollama instead."
                            await self.update_settings(provider="ollama", model=ollama_models[0])
                        except Exception as e3:
                            logger.warning(f"Ollama fallback also failed: {e3}")

            if not fell_back_on_error:
                logger.exception("DJ LLM call failed")
                return {"error": f"LLM error: {e}"}

        # Strip <think>...</think> blocks from models like Qwen3
        response_text = re.sub(
            r"<think>.*?</think>", "", response_text, flags=re.DOTALL
        ).strip()

        # Parse response for generation params or actions
        gen_params = _extract_json_block(response_text)
        action = _extract_action(response_text)

        # Clean action tags and JSON code blocks from the display text
        display_text = re.sub(r"\[ACTION:\w+\]", "", response_text)
        display_text = re.sub(r"```json\s*\n?.*?\n?\s*```", "", display_text, flags=re.DOTALL)
        display_text = display_text.strip()

        # Save assistant message
        assistant_msg_id = str(uuid.uuid4())
        assistant_now = datetime.now(timezone.utc).isoformat()
        gen_params_json = json.dumps(gen_params) if gen_params else None
        generation_job_id = None

        # Generate conversation title BEFORE firing generation task to avoid
        # concurrent MLX usage (chat model + ACE-Step LM) which causes a segfault
        title_cursor = await db.execute(
            "SELECT title FROM dj_conversations WHERE id = ?", (conv_id,)
        )
        title_row = await title_cursor.fetchone()
        auto_title = None
        if title_row and title_row["title"] == "New Conversation":
            from tadpole_studio.services.title_generator import generate_conversation_title
            auto_title = await generate_conversation_title(user_content)

        # Trigger generation if params were provided
        if gen_params:
            try:
                from tadpole_studio.services.generation import generation_service

                if generation_service.dit_initialized:
                    job_id = generation_service.create_job()
                    generation_job_id = job_id

                    # Fire and forget generation
                    import asyncio
                    asyncio.create_task(
                        self._run_dj_generation(job_id, gen_params, provider_name, model_name)
                    )
            except Exception as e:
                logger.warning(f"Failed to start DJ generation: {e}")

        await db.execute(
            """INSERT INTO dj_messages
               (id, conversation_id, role, content, generation_params_json, generation_job_id, created_at)
               VALUES (?, ?, 'assistant', ?, ?, ?, ?)""",
            (assistant_msg_id, conv_id, display_text, gen_params_json, generation_job_id, assistant_now),
        )

        # Apply the pre-generated title or just update timestamp
        if auto_title is not None:
            await db.execute(
                "UPDATE dj_conversations SET title = ?, updated_at = ? WHERE id = ?",
                (auto_title, assistant_now, conv_id),
            )
        else:
            await db.execute(
                "UPDATE dj_conversations SET updated_at = ? WHERE id = ?",
                (assistant_now, conv_id),
            )
        await db.commit()

        return {
            "message": {
                "id": assistant_msg_id,
                "conversation_id": conv_id,
                "role": "assistant",
                "content": display_text,
                "generation_params_json": gen_params_json,
                "generation_job_id": generation_job_id,
                "created_at": assistant_now,
            },
            "action": action,
            "generation_job_id": generation_job_id,
            "fallback_notice": fallback_notice,
        }

    async def _run_dj_generation(
        self, job_id: str, params: dict[str, Any],
        dj_provider: str = "", dj_model: str = "",
    ) -> None:
        """Run generation triggered by DJ chat."""
        from tadpole_studio.services.generation import generation_service
        from tadpole_studio.services.gpu_lock import gpu_lock
        from tadpole_studio.services.lora_service import lora_service
        from tadpole_studio.ws.manager import generation_ws_manager

        acquired = await gpu_lock.acquire("dj")
        if not acquired:
            generation_service.update_job(
                job_id,
                status="failed",
                error=f"GPU is busy ({gpu_lock.holder})",
            )
            await generation_ws_manager.broadcast({
                "type": "failed",
                "job_id": job_id,
                "error": f"GPU is busy ({gpu_lock.holder}). Please wait.",
            })
            return

        started_at = datetime.now(timezone.utc)
        history_id = job_id  # Same ID so DJ messages can link to history

        try:
            generation_service.update_job(job_id, status="running", stage="preparing")

            # Ensure required fields
            params.setdefault("task_type", "text2music")
            params.setdefault("batch_size", 1)

            # Inject model metadata (matches generation.py pattern)
            lora_snapshot = lora_service.get_lora_snapshot()
            if lora_snapshot:
                params["lora"] = lora_snapshot
            if generation_service.active_dit_model:
                params["dit_model"] = generation_service.active_dit_model
            if generation_service.active_lm_model:
                params["lm_model"] = generation_service.active_lm_model
            params["backend"] = "ace-step"
            if dj_provider:
                params["dj_provider"] = dj_provider
            if dj_model:
                params["dj_model"] = dj_model

            # Insert generation history record
            db = await get_db()
            await db.execute(
                """INSERT INTO generation_history (id, task_type, status, params_json, started_at, created_at, backend)
                   VALUES (?, ?, 'running', ?, ?, ?, 'ace-step')""",
                (history_id, params.get("task_type", "text2music"),
                 json.dumps(params), started_at.isoformat(), started_at.isoformat()),
            )
            await db.commit()

            result = await generation_service.generate(params)

            if result.get("success"):
                audios = result.get("audios", [])
                results = [
                    {
                        "path": a.get("path", ""),
                        "key": a.get("key", ""),
                        "sample_rate": a.get("sample_rate", 48000),
                        "params": {
                            k: v
                            for k, v in (a.get("params") or {}).items()
                            if k != "tensor" and not k.startswith("_")
                        },
                    }
                    for a in audios
                ]
                generation_service.update_job(
                    job_id, status="completed", progress=1.0, results=results
                )
                await generation_ws_manager.broadcast({
                    "type": "completed",
                    "job_id": job_id,
                    "results": results,
                })

                # Update history as completed
                completed_at = datetime.now(timezone.utc)
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                db = await get_db()
                await db.execute(
                    """UPDATE generation_history
                       SET status = 'completed', result_json = ?, audio_count = ?,
                           completed_at = ?, duration_ms = ?
                       WHERE id = ?""",
                    (json.dumps(results), len(results),
                     completed_at.isoformat(), duration_ms, history_id),
                )
                await db.commit()

                # Auto-generate a title for the history entry
                try:
                    from tadpole_studio.services.title_generator import generate_song_title
                    caption = params.get("caption", "")
                    if caption:
                        title = await generate_song_title(caption, "", "", "DJ Generation")
                        db = await get_db()
                        await db.execute(
                            "UPDATE generation_history SET title = ? WHERE id = ?",
                            (title, history_id),
                        )
                        await db.commit()
                        await generation_ws_manager.broadcast({
                            "type": "title",
                            "job_id": job_id,
                            "history_id": history_id,
                            "title": title,
                        })
                except Exception as e:
                    logger.debug(f"DJ title generation failed: {e}")
            else:
                error = result.get("error", "Generation failed")
                generation_service.update_job(job_id, status="failed", error=error)
                await generation_ws_manager.broadcast({
                    "type": "failed",
                    "job_id": job_id,
                    "error": error,
                })

                db = await get_db()
                await db.execute(
                    """UPDATE generation_history SET status = 'failed', error_message = ? WHERE id = ?""",
                    (error, history_id),
                )
                await db.commit()
        except Exception as e:
            logger.exception(f"DJ generation {job_id} failed")
            generation_service.update_job(job_id, status="failed", error=str(e))
            await generation_ws_manager.broadcast({
                "type": "failed",
                "job_id": job_id,
                "error": str(e),
            })

            try:
                db = await get_db()
                await db.execute(
                    """UPDATE generation_history SET status = 'failed', error_message = ? WHERE id = ?""",
                    (str(e), history_id),
                )
                await db.commit()
            except Exception:
                pass
        finally:
            await gpu_lock.release("dj")

    async def get_providers_info(self) -> dict[str, Any]:
        """Get info about available LLM providers."""
        db = await get_db()
        cursor = await db.execute(
            "SELECT key, value FROM settings WHERE key IN ('dj_provider', 'dj_model', 'dj_system_prompt', 'openai_api_key', 'anthropic_api_key', 'openai_compatible_api_base')"
        )
        rows = await cursor.fetchall()
        active_provider = "built-in"
        active_model = "Qwen2.5-1.5B-Instruct-4bit"
        custom_system_prompt = ""
        stored_api_keys: dict[str, str] = {}
        api_bases: dict[str, str] = {}
        for r in rows:
            if r["key"] == "dj_provider":
                active_provider = r["value"]
            elif r["key"] == "dj_model":
                active_model = r["value"]
            elif r["key"] == "dj_system_prompt":
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
            "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
        }

    async def update_settings(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> dict[str, Any]:
        db = await get_db()
        if provider is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('dj_provider', ?, datetime('now'))",
                (provider,),
            )
        if model is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('dj_model', ?, datetime('now'))",
                (model,),
            )
        if system_prompt is not None:
            if system_prompt.strip() == "" or system_prompt.strip() == DEFAULT_SYSTEM_PROMPT.strip():
                await db.execute(
                    "DELETE FROM settings WHERE key = 'dj_system_prompt'"
                )
            else:
                await db.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('dj_system_prompt', ?, datetime('now'))",
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
        return await self.get_providers_info()

    async def rename_conversation(self, conv_id: str, title: str) -> bool:
        db = await get_db()
        cursor = await db.execute(
            "SELECT id FROM dj_conversations WHERE id = ?", (conv_id,)
        )
        if await cursor.fetchone() is None:
            return False
        await db.execute(
            "UPDATE dj_conversations SET title = ? WHERE id = ?",
            (title, conv_id),
        )
        await db.commit()
        return True


dj_service = DJService()
