"""
LLM provider interface for the AI DJ feature.

Supports multiple backends:
- Built-in MLX (local, free, default — uses downloaded chat LLM)
- Ollama (local, free)
- OpenAI (cloud, requires TADPOLE_OPENAI_API_KEY)
- Anthropic (cloud, requires TADPOLE_ANTHROPIC_API_KEY)
"""

import asyncio
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from loguru import logger


class LLMProvider(ABC):
    """Abstract interface for LLM chat completion."""

    name: str = ""
    requires_api_key: bool = False

    @property
    def package_installed(self) -> bool:
        """Whether the required Python package is installed. Override for cloud providers."""
        return True

    @property
    def unavailable_reason(self) -> str:
        """Human-readable reason this provider can't be used, or empty string."""
        return ""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider is ready to use."""

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]], model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        """Send a chat completion request and return the assistant response."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return known model names for this provider."""

    async def list_models_async(self) -> list[str]:
        """Async variant of list_models. Override for providers that need I/O."""
        return self.list_models()


class MLXChatProvider(LLMProvider):
    """Built-in MLX chat LLM loaded from data/chat-llm/."""

    name = "built-in"
    requires_api_key = False

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._loaded_model_name: str = ""
        self._lock = threading.Lock()
        self._mlx_usable = self._check_mlx_usable()

        from tadpole_studio.config import settings
        self._chat_llm_dir = Path(settings.ACESTEP_PROJECT_ROOT) / "chat-llm"

    @staticmethod
    def _check_mlx_usable() -> bool:
        """Check if MLX is available on this platform."""
        import sys
        if sys.platform != "darwin":
            return False
        try:
            import mlx_lm  # noqa: F401
            return True
        except ImportError:
            return False

    def _installed_models(self) -> list[str]:
        """Return names of locally installed chat LLM models."""
        if not self._chat_llm_dir.exists():
            return []
        return [
            d.name
            for d in sorted(self._chat_llm_dir.iterdir())
            if d.is_dir() and (d / "config.json").exists()
        ]

    @property
    def unavailable_reason(self) -> str:
        if not self._mlx_usable:
            return "Built-in chat requires Apple Silicon (macOS). Use Ollama for a free local alternative."
        if not self._installed_models():
            return "No chat LLM models installed."
        return ""

    async def is_available(self) -> bool:
        if not self._mlx_usable:
            return False
        return len(self._installed_models()) > 0

    def _load(self, model_name: str) -> None:
        """Load (or switch) the MLX model. Blocks — call from a thread."""
        if not self._mlx_usable:
            raise RuntimeError(
                "Built-in MLX chat is only available on Apple Silicon Macs. "
                "Use Ollama, OpenAI, or Anthropic instead."
            )
        if self._model is not None and self._loaded_model_name == model_name:
            return

        model_path = str(self._chat_llm_dir / model_name)
        logger.info(f"Loading MLX chat model from {model_path}")

        from mlx_lm import load  # type: ignore[import-untyped]

        self._model, self._tokenizer = load(model_path)
        self._loaded_model_name = model_name
        logger.info(f"MLX chat model '{model_name}' loaded")

    def _generate_sync(self, messages: list[dict[str, str]], model_name: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        """Run model generation synchronously (intended for asyncio.to_thread)."""
        with self._lock:
            self._load(model_name)

            from mlx_lm import generate  # type: ignore[import-untyped]
            from mlx_lm.sample_utils import make_sampler  # type: ignore[import-untyped]

            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            sampler = make_sampler(temp=temperature)
            return generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
            )

    async def chat(self, messages: list[dict[str, str]], model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        installed = self._installed_models()
        if not installed:
            raise RuntimeError("No chat LLM models installed")

        # Use requested model if installed, otherwise first available
        target = model if model in installed else installed[0]
        logger.info(f"LLM chat [built-in/mlx] model={target} temp={temperature}")
        return await asyncio.to_thread(self._generate_sync, messages, target, max_tokens, temperature)

    def list_models(self) -> list[str]:
        if not self._mlx_usable:
            return []
        return self._installed_models()


class OllamaProvider(LLMProvider):
    name = "ollama"
    requires_api_key = False

    def __init__(self) -> None:
        self._base_url = os.getenv("TADPOLE_OLLAMA_URL", "http://localhost:11434")

    async def is_available(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def chat(self, messages: list[dict[str, str]], model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        logger.info(f"LLM chat [ollama] model={model} temp={temperature}")
        import httpx
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False, "options": {"temperature": temperature}},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    def list_models(self) -> list[str]:
        return []

    async def list_models_async(self) -> list[str]:
        """Query Ollama /api/tags for actually installed models."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return []
                data = resp.json()
                models = data.get("models", [])
                return [
                    m["name"].removesuffix(":latest")
                    for m in models
                    if "name" in m
                ]
        except Exception:
            return []


class OpenAIProvider(LLMProvider):
    name = "openai"
    requires_api_key = True

    def __init__(self) -> None:
        self._api_key = os.getenv("TADPOLE_OPENAI_API_KEY", "")

    def set_api_key(self, key: str) -> None:
        self._api_key = key

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    @property
    def package_installed(self) -> bool:
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    async def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    async def chat(self, messages: list[dict[str, str]], model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        logger.info(f"LLM chat [openai] model={model} temp={temperature}")
        import openai
        client = openai.AsyncOpenAI(api_key=self._api_key)
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            response = await client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        except openai.BadRequestError as e:
            if "temperature" in str(e):
                kwargs.pop("temperature")
                response = await client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            else:
                raise
        return response.choices[0].message.content or ""

    def list_models(self) -> list[str]:
        return ["gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1", "o3-mini", "o4-mini", "gpt-5-nano", "gpt-5-mini", "gpt-5"]


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    requires_api_key = True

    def __init__(self) -> None:
        self._api_key = os.getenv("TADPOLE_ANTHROPIC_API_KEY", "")

    def set_api_key(self, key: str) -> None:
        self._api_key = key

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    @property
    def package_installed(self) -> bool:
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    async def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    async def chat(self, messages: list[dict[str, str]], model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        logger.info(f"LLM chat [anthropic] model={model} temp={temperature}")
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        # Separate system message from conversation
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        kwargs: dict = {
            "model": model,
            "max_tokens": 2048,
            "system": system_msg,
            "messages": chat_messages,
            "temperature": temperature,
        }
        try:
            response = await client.messages.create(**kwargs)  # type: ignore[arg-type]
        except anthropic.BadRequestError as e:
            if "temperature" in str(e):
                kwargs.pop("temperature")
                response = await client.messages.create(**kwargs)  # type: ignore[arg-type]
            else:
                raise
        return response.content[0].text if response.content else ""

    def list_models(self) -> list[str]:
        return ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-6"]


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"
    requires_api_key = False

    def __init__(self) -> None:
        self._api_key = "dummy"
        self._api_base = ""

    def set_api_key(self, key: str) -> None:
        # We can reuse this method to set api_base for compatibility, or add a new one.
        # Let's just define a specific method for api_base, or read from env/db.
        pass

    def set_api_base(self, base: str) -> None:
        self._api_base = base

    @property
    def has_api_base(self) -> bool:
        return bool(self._api_base)

    @property
    def package_installed(self) -> bool:
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    async def is_available(self) -> bool:
        if not self._api_base:
            return False
        try:
            import openai  # noqa: F401
            import httpx
            # Simple ping to the models endpoint or just checking base URL reachability
            async with httpx.AsyncClient(timeout=5) as client:
                try:
                    resp = await client.get(f"{self._api_base}/models")
                    if resp.status_code in (200, 401, 403): # 401/403 means it's there but needs auth
                        return True
                    else:
                        logger.warning(f"OpenAICompatibleProvider connection test returned status {resp.status_code}")
                        return False
                except Exception as e:
                    logger.warning(f"OpenAICompatibleProvider connection failed: {e}")
                    return False
        except ImportError:
            return False

    async def chat(self, messages: list[dict[str, str]], model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        logger.info(f"LLM chat [openai-compatible] base={self._api_base} model={model} temp={temperature}")
        import openai
        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._api_base)
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            response = await client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        except openai.BadRequestError as e:
            if "temperature" in str(e):
                kwargs.pop("temperature")
                response = await client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            else:
                raise
        return response.choices[0].message.content or ""

    def list_models(self) -> list[str]:
        return []
        
    async def list_models_async(self) -> list[str]:
        """Query /v1/models to get available models."""
        if not self._api_base:
            return []
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._api_base)
            models = await client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            logger.warning(f"Failed to list models for openai-compatible provider: {e}")
            return []


# Provider registry — "built-in" first so it's the default
_providers: dict[str, LLMProvider] = {
    "built-in": MLXChatProvider(),
    "ollama": OllamaProvider(),
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "openai-compatible": OpenAICompatibleProvider(),
}


def get_provider(name: str) -> Optional[LLMProvider]:
    return _providers.get(name)


def get_all_providers() -> dict[str, LLMProvider]:
    return _providers
