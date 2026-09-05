"""Configuracion global del pipeline. No contiene secretos: esos van por variables de entorno."""

import importlib

from dotenv import load_dotenv

# Carga .env si existe (uso local / manual con app.py). En GitHub Actions no
# hay .env: las variables ya vienen seteadas como Secrets, y esto es un no-op.
load_dotenv()

# --- Claude ---
CLAUDE_MODEL = "claude-sonnet-4-6"

# --- Narracion / guion ---
WORDS_PER_MINUTE = 165
SCRIPT_TARGET_SECONDS = 65
SCRIPT_TARGET_WORDS = round(WORDS_PER_MINUTE * SCRIPT_TARGET_SECONDS / 60)

# --- Video ---
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

PREVIEW_WIDTH = 540
PREVIEW_HEIGHT = 960

# --- Canales disponibles ---
AVAILABLE_CHANNELS = [
    "money_curiosities",
    "history_geopolitics",
]


def load_channel(slug: str):
    """Importa y devuelve el modulo channels/<slug>.py."""
    if slug not in AVAILABLE_CHANNELS:
        raise ValueError(
            f"Canal desconocido: {slug!r}. Canales disponibles: {AVAILABLE_CHANNELS}"
        )
    return importlib.import_module(f"channels.{slug}")
