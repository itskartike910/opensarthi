from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Define standard writable user config directories
LOCAL_DEV_ENV = os.path.join(os.path.dirname(__file__), ".env")
USER_CONFIG_DIR = Path.home() / ".config" / "opensarthi"
USER_CONFIG_ENV = USER_CONFIG_DIR / ".env"

# Ensure the config folder exists
USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Select env file to load: USER_CONFIG_ENV if it exists, otherwise fall back to local dev .env if present
env_file_path = str(USER_CONFIG_ENV) if USER_CONFIG_ENV.exists() else (LOCAL_DEV_ENV if os.path.exists(LOCAL_DEV_ENV) else str(USER_CONFIG_ENV))

class Settings(BaseSettings):
    app_name: str = "OpenSarthi"
    wake_words: list[str] = ["hey sarthi", "hello sarthi"]
    local_model: str = "qwen2.5-coder:3b"
    cloud_model: str = "kimi-k2.5:cloud"
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    voice_accent: str = "ie"
    voice_speed: float = 1.35
    continuous_listening: bool = False
    active_theme: str = "theme-red-black"
    
    model_config = SettingsConfigDict(env_file=env_file_path)

settings = Settings()

def save_settings_to_env(
    local_model: str, 
    cloud_model: str, 
    gemini_api_key: str | None, 
    voice_accent: str, 
    voice_speed: float, 
    continuous_listening: bool,
    active_theme: str
):
    # Always write to the writable user's home configuration directory (safe for read-only AppImage filesystems!)
    with open(USER_CONFIG_ENV, "w") as f:
        f.write(f"LOCAL_MODEL={local_model}\n")
        f.write(f"CLOUD_MODEL={cloud_model}\n")
        if gemini_api_key:
            f.write(f"GEMINI_API_KEY={gemini_api_key}\n")
        f.write(f"VOICE_ACCENT={voice_accent}\n")
        f.write(f"VOICE_SPEED={voice_speed}\n")
        f.write(f"CONTINUOUS_LISTENING={'True' if continuous_listening else 'False'}\n")
        f.write(f"ACTIVE_THEME={active_theme}\n")
