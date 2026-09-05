"""Paso 11: mensajes a Telegram + persistencia de drafts en disco.

Se pega directo a la Bot API por HTTP (sin libreria de bot con polling
propio) porque el proceso real corre como cron job corto en GitHub
Actions (topic-scan cada 12h, telegram-listener cada 10 min), no como
bot persistente.

Los mensajes van en texto plano (sin parse_mode Markdown/HTML): el guion
y la metadata los escribe un LLM, y caracteres random como '_' o '*'
podrian romper el parseo de entidades de Telegram.
"""

import json
import os
from pathlib import Path

import requests

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
MAX_MESSAGE_CHARS = 4000
TELEGRAM_CAPTION_LIMIT = 1024

DRAFTS_DIR = Path(__file__).parent / "drafts"


class TelegramNotifyError(Exception):
    pass


def _bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramNotifyError("Falta la variable de entorno TELEGRAM_BOT_TOKEN.")
    return token


def chat_id() -> str:
    cid = os.environ.get("TELEGRAM_CHAT_ID")
    if not cid:
        raise TelegramNotifyError("Falta la variable de entorno TELEGRAM_CHAT_ID.")
    return cid


def _api_url(method: str) -> str:
    return f"{TELEGRAM_API_BASE.format(token=_bot_token())}/{method}"


def _split_into_blocks(text: str, max_chars: int = MAX_MESSAGE_CHARS) -> list:
    """Parte texto largo en bloques de max_chars, cortando en saltos de linea
    cuando es posible para no partir una linea al medio."""
    if len(text) <= max_chars:
        return [text]

    blocks = []
    remaining = text
    while len(remaining) > max_chars:
        cut = remaining.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        blocks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        blocks.append(remaining)
    return blocks


def send_text(to_chat_id: str, text: str, reply_markup: dict = None) -> None:
    """Manda texto, partiendo en bloques si excede MAX_MESSAGE_CHARS.
    reply_markup (si se pasa) solo se adjunta al ultimo bloque."""
    blocks = _split_into_blocks(text)
    for i, block in enumerate(blocks):
        payload = {"chat_id": to_chat_id, "text": block}
        if reply_markup and i == len(blocks) - 1:
            payload["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post(_api_url("sendMessage"), data=payload, timeout=15)
        resp.raise_for_status()


def send_video(to_chat_id: str, video_path: str, caption: str = "", reply_markup: dict = None) -> dict:
    """Devuelve el objeto Message que responde la Bot API (trae 'message_id'),
    asi el llamador puede asociar respuestas futuras a este mensaje."""
    with open(video_path, "rb") as f:
        data = {"chat_id": to_chat_id, "caption": caption[:TELEGRAM_CAPTION_LIMIT]}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        resp = requests.post(_api_url("sendVideo"), data=data, files={"video": f}, timeout=300)
    resp.raise_for_status()
    return resp.json()["result"]


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    resp = requests.post(_api_url("answerCallbackQuery"), data=payload, timeout=15)
    resp.raise_for_status()


def get_updates(offset: int) -> list:
    """getUpdates con offset (confirma recepcion de todo lo anterior a offset).
    timeout=0: no hace long-polling, se usa desde un cron corto (Paso 14)."""
    resp = requests.get(_api_url("getUpdates"), params={"offset": offset, "timeout": 0}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("result", [])


# --- Persistencia de drafts (drafts/{channel_slug}/{draft_id}.json) ---


def _draft_path(channel_slug: str, draft_id: str) -> Path:
    return DRAFTS_DIR / channel_slug / f"{draft_id}.json"


def save_draft(draft: dict) -> Path:
    path = _draft_path(draft["channel_slug"], draft["draft_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_draft(channel_slug: str, draft_id: str) -> dict:
    path = _draft_path(channel_slug, draft_id)
    if not path.exists():
        raise TelegramNotifyError(f"No existe el draft {channel_slug}/{draft_id}.")
    return json.loads(path.read_text(encoding="utf-8"))


def update_draft(channel_slug: str, draft_id: str, **updates) -> dict:
    """Mergea `updates` sobre el draft existente y lo guarda. Usado por
    telegram_listener.py (Paso 13) para avanzar la maquina de estados."""
    draft = load_draft(channel_slug, draft_id)
    draft.update(updates)
    save_draft(draft)
    return draft


def find_draft(draft_id: str) -> dict:
    """Busca un draft por id solo (sin saber el canal), porque el callback_data de
    los botones de Telegram solo trae el draft_id (ej. 'usar_guion:{id}'). Los
    draft_id son uuid4 hex, asi que una colision entre canales es practicamente
    imposible; si igual pasara, se trata como error en vez de elegir cualquiera."""
    matches = list(DRAFTS_DIR.glob(f"*/{draft_id}.json"))
    if not matches:
        raise TelegramNotifyError(f"No existe ningun draft con id {draft_id}.")
    if len(matches) > 1:
        raise TelegramNotifyError(f"draft_id {draft_id} ambiguo entre varios canales: {matches}")
    return json.loads(matches[0].read_text(encoding="utf-8"))


def find_draft_by_message_id(message_id: int):
    """Busca el draft cuyo ultimo preview enviado tiene este message_id, para
    poder asociar una respuesta de texto (reply) con el draft correspondiente.
    Devuelve None si ningun draft matchea (no es reply a un preview nuestro)."""
    for path in DRAFTS_DIR.glob("*/*.json"):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if draft.get("last_preview_message_id") == message_id:
            return draft
    return None


# --- Mensajes del flujo ---


def send_telegram_draft(channel, draft_id: str, title: str, scenes: list) -> None:
    """Persiste el draft (estado='pendiente') y manda el guion legible a Telegram
    con un boton para elegirlo."""
    draft = {
        "draft_id": draft_id,
        "channel_slug": channel.CHANNEL_SLUG,
        "title": title,
        "scenes": scenes,
        "estado": "pendiente",
        "notas_usuario": [],
    }
    save_draft(draft)

    total_duration = sum(s["duration_estimate"] for s in scenes)
    lines = [
        f"{channel.CHANNEL_EMOJI} Nuevo guion candidato ({channel.CHANNEL_SLUG})",
        "",
        title,
        "",
        f"{len(scenes)} escenas, ~{total_duration:.0f}s",
        "",
    ]
    for i, scene in enumerate(scenes, start=1):
        lines.append(f"{i}. {scene['text']}")
    text = "\n".join(lines)

    reply_markup = {
        "inline_keyboard": [[{"text": "✅ Usar este guion", "callback_data": f"usar_guion:{draft_id}"}]]
    }
    send_text(chat_id(), text, reply_markup=reply_markup)


def send_telegram_preview(
    to_chat_id: str, video_path: str, caption: str, draft_id: str, fallback_count: int, total_scenes: int
) -> int:
    """Manda el preview (baja calidad) con botones para iterar o aprobar.
    Devuelve el message_id del mensaje enviado (telegram_listener.py lo guarda
    en el draft para poder asociar futuras respuestas de texto)."""
    warning = ""
    if fallback_count > 0:
        warning = (
            f"\n⚠️ {fallback_count}/{total_scenes} escenas usaron b-roll generico "
            f"(fallback), no el clip especifico del tema.\n"
        )

    full_caption = (
        f"{caption}\n{warning}\n"
        f"🔍 PREVIEW en baja calidad, para revisar guion y ritmo. "
        f"La version final se genera en alta calidad recien al aprobar."
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "🔄 Regenerar video", "callback_data": f"regen_video:{draft_id}"},
                {"text": "🎙️ Regenerar solo voz", "callback_data": f"regen_voz:{draft_id}"},
            ],
            [
                {"text": "✅ Aprobar - versión final", "callback_data": f"approve:{draft_id}"},
                {"text": "❌ Descartar", "callback_data": f"descartar:{draft_id}"},
            ],
        ]
    }
    result = send_video(to_chat_id, video_path, caption=full_caption, reply_markup=reply_markup)
    return result["message_id"]


def send_telegram_final(to_chat_id: str, video_path: str, metadata: dict) -> None:
    """Manda el video final y, en un mensaje aparte (el caption de Telegram tiene
    limite de 1024 caracteres), el titulo/descripcion/hashtags/caption de TikTok
    listos para copiar y pegar al subir a mano."""
    send_video(to_chat_id, video_path, caption="✅ Version final lista.")

    hashtags_str = " ".join(f"#{h.lstrip('#')}" for h in metadata["hashtags"])
    text = (
        f"📌 TÍTULO:\n{metadata['title']}\n\n"
        f"📝 DESCRIPCIÓN:\n{metadata['description']}\n\n"
        f"#️⃣ HASHTAGS:\n{hashtags_str}\n\n"
        f"🎵 TIKTOK CAPTION:\n{metadata['tiktok_caption']}\n\n"
        f"(Formato listo para copiar y pegar directo al subir a YouTube/TikTok.)"
    )
    send_text(to_chat_id, text)
