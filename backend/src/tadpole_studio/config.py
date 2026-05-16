import os
import sys
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables."""

    HOST: str = os.getenv("TADPOLE_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("TADPOLE_PORT", "8000"))

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "tadpole-studio.db"
    AUDIO_DIR: Path = DATA_DIR / "audio"
    UPLOADS_DIR: Path = DATA_DIR / "uploads"
    LORA_DIR: Path = DATA_DIR / "loras"
    DATASETS_DIR: Path = DATA_DIR / "datasets"
    DATASET_CONFIGS_DIR: Path = DATA_DIR / "dataset-configs"
    TRAINING_OUTPUT_DIR: Path = DATA_DIR / "training_output"

    # ACE-Step project root (co-located with DB, audio, LoRAs)
    ACESTEP_PROJECT_ROOT: str = os.getenv(
        "ACESTEP_PROJECT_ROOT",
        str(Path(__file__).resolve().parent.parent.parent / "data"),
    )

    # Model defaults
    DEFAULT_DIT_MODEL: str = os.getenv("TADPOLE_DIT_MODEL", "acestep-v15-turbo")
    DEFAULT_LM_MODEL: str = os.getenv("TADPOLE_LM_MODEL", "acestep-5Hz-lm-1.7B")
    DEFAULT_LM_BACKEND: str = os.getenv(
        "TADPOLE_LM_BACKEND",
        "mlx" if sys.platform == "darwin" else "nano-vllm",
    )
    DEFAULT_DEVICE: str = os.getenv("TADPOLE_DEVICE", "auto")

    # Generation defaults
    DEFAULT_AUDIO_FORMAT: str = os.getenv("TADPOLE_AUDIO_FORMAT", "flac")
    DEFAULT_BATCH_SIZE: int = int(os.getenv("TADPOLE_BATCH_SIZE", "2"))

    # HeartMuLa defaults
    HEARTMULA_MODEL_PATH: str = os.getenv("HEARTMULA_MODEL_PATH", "")
    HEARTMULA_VERSION: str = os.getenv("HEARTMULA_VERSION", "3B")
    HEARTMULA_LAZY_LOAD: bool = os.getenv("HEARTMULA_LAZY_LOAD", "false").lower() == "true"
    HEARTMULA_DEVICE: str = os.getenv("HEARTMULA_DEVICE", "auto")

    # CORS — override with comma-separated TADPOLE_CORS_ORIGINS env var
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "TADPOLE_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8700,http://127.0.0.1:8700,http://0.0.0.0:8700",
        ).split(",")
        if origin.strip()
    ]

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        cls.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        cls.LORA_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATASET_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.TRAINING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "checkpoints").mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "chat-llm").mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / ".cache" / "acestep").mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "heartmula").mkdir(parents=True, exist_ok=True)


settings = Settings()
