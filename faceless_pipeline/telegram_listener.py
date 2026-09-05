"""Paso 13: maquina de estados que procesa los botones/mensajes de Telegram.

Estados del draft: "pendiente" -> "guion_aprobado" -> "preview_generado" ->
"final_aprobado" | "descartado".

Corrido cada 10 minutos por .github/workflows/telegram-listener.yml (Paso 14).
Cada corrida: lee offset -> getUpdates -> procesa cada update -> guarda
offset. Si no hay updates nuevos, termina sin mandar nada (no spamear).
"""

import json
from pathlib import Path

import config
import fetch_footage
import generate_audio
import generate_metadata
import generate_script
import generate_subtitles
import generate_video
import telegram_notify

OFFSET_FILE = Path(__file__).parent / "telegram_offset.json"

CALLBACK_ACK_TEXT = {
    "usar_guion": "Generando preview...",
    "regen_video": "Regenerando video...",
    "regen_voz": "Regenerando voz...",
    "approve": "Generando version final...",
    "descartar": "Descartado.",
}


def _load_offset() -> int:
    if not OFFSET_FILE.exists():
        return 0
    try:
        return json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0)
    except (json.JSONDecodeError, OSError):
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def _draft_media_dir(channel_slug: str, draft_id: str) -> Path:
    media_dir = telegram_notify.DRAFTS_DIR / channel_slug / draft_id
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir


# --- Handlers de cada boton ---


def _handle_usar_guion(draft_id: str) -> None:
    draft = telegram_notify.find_draft(draft_id)
    channel = config.load_channel(draft["channel_slug"])
    media_dir = _draft_media_dir(draft["channel_slug"], draft_id)
    scenes = draft["scenes"]

    telegram_notify.update_draft(draft["channel_slug"], draft_id, estado="guion_aprobado")

    audio_path = media_dir / "narration.mp3"
    generate_audio.generate_audio(generate_audio.scenes_to_narration(scenes), channel.TTS_VOICE, str(audio_path))
    generate_subtitles.generate_subtitles(str(audio_path), str(audio_path.with_suffix(".ass")))

    footage_results = fetch_footage.fetch_footage_for_scenes(scenes, channel, str(media_dir / "footage"))
    video_result = generate_video.generate_video(
        channel, scenes, footage_results, str(audio_path), str(media_dir), mode="preview"
    )

    message_id = telegram_notify.send_telegram_preview(
        telegram_notify.chat_id(),
        video_result["video_path"],
        caption=f"{channel.CHANNEL_EMOJI} {draft['title']}",
        draft_id=draft_id,
        fallback_count=video_result["fallback_count"],
        total_scenes=video_result["total_scenes"],
    )

    telegram_notify.update_draft(
        draft["channel_slug"],
        draft_id,
        estado="preview_generado",
        audio_path=str(audio_path),
        footage_results=footage_results,
        used_clip_ids=[f["clip_id"] for f in footage_results],
        last_preview_message_id=message_id,
    )


def _handle_regen_video(draft_id: str) -> None:
    draft = telegram_notify.find_draft(draft_id)
    channel = config.load_channel(draft["channel_slug"])
    media_dir = _draft_media_dir(draft["channel_slug"], draft_id)
    scenes = draft["scenes"]

    notas = draft.get("notas_usuario", [])
    if notas:
        try:
            scenes = generate_script.regenerate_visual_keywords(channel, scenes, notas)
        except generate_script.ScriptGenerationError as e:
            print(
                f"[telegram_listener] aviso: fallo regenerar visual_keywords con notas "
                f"({e}); sigo con las keywords actuales."
            )

    avoid_clip_ids = set(draft.get("used_clip_ids", []))
    footage_results = fetch_footage.fetch_footage_for_scenes(
        scenes, channel, str(media_dir / "footage"), avoid_clip_ids=avoid_clip_ids
    )

    video_result = generate_video.generate_video(
        channel, scenes, footage_results, draft["audio_path"], str(media_dir), mode="preview"
    )

    used_clip_ids = list(avoid_clip_ids | {f["clip_id"] for f in footage_results})

    message_id = telegram_notify.send_telegram_preview(
        telegram_notify.chat_id(),
        video_result["video_path"],
        caption=f"{channel.CHANNEL_EMOJI} {draft['title']} (video regenerado)",
        draft_id=draft_id,
        fallback_count=video_result["fallback_count"],
        total_scenes=video_result["total_scenes"],
    )

    telegram_notify.update_draft(
        draft["channel_slug"],
        draft_id,
        estado="preview_generado",
        scenes=scenes,
        footage_results=footage_results,
        used_clip_ids=used_clip_ids,
        last_preview_message_id=message_id,
    )


def _handle_regen_voz(draft_id: str) -> None:
    draft = telegram_notify.find_draft(draft_id)
    channel = config.load_channel(draft["channel_slug"])
    media_dir = _draft_media_dir(draft["channel_slug"], draft_id)
    scenes = draft["scenes"]

    audio_path = media_dir / "narration.mp3"
    generate_audio.generate_audio(generate_audio.scenes_to_narration(scenes), channel.TTS_VOICE, str(audio_path))
    generate_subtitles.generate_subtitles(str(audio_path), str(audio_path.with_suffix(".ass")))

    footage_results = draft["footage_results"]  # reusa el footage ya descargado
    video_result = generate_video.generate_video(
        channel, scenes, footage_results, str(audio_path), str(media_dir), mode="preview"
    )

    message_id = telegram_notify.send_telegram_preview(
        telegram_notify.chat_id(),
        video_result["video_path"],
        caption=f"{channel.CHANNEL_EMOJI} {draft['title']} (voz regenerada)",
        draft_id=draft_id,
        fallback_count=video_result["fallback_count"],
        total_scenes=video_result["total_scenes"],
    )

    telegram_notify.update_draft(
        draft["channel_slug"],
        draft_id,
        estado="preview_generado",
        audio_path=str(audio_path),
        last_preview_message_id=message_id,
    )


def _handle_approve(draft_id: str) -> None:
    draft = telegram_notify.find_draft(draft_id)
    channel = config.load_channel(draft["channel_slug"])
    media_dir = _draft_media_dir(draft["channel_slug"], draft_id)

    video_result = generate_video.generate_video(
        channel, draft["scenes"], draft["footage_results"], draft["audio_path"], str(media_dir), mode="final"
    )

    metadata = generate_metadata.generate_metadata(channel, draft["scenes"], draft["title"])

    telegram_notify.send_telegram_final(telegram_notify.chat_id(), video_result["video_path"], metadata)

    telegram_notify.update_draft(draft["channel_slug"], draft_id, estado="final_aprobado", metadata=metadata)


def _handle_descartar(draft_id: str) -> None:
    draft = telegram_notify.find_draft(draft_id)
    telegram_notify.update_draft(draft["channel_slug"], draft_id, estado="descartado")


CALLBACK_HANDLERS = {
    "usar_guion": _handle_usar_guion,
    "regen_video": _handle_regen_video,
    "regen_voz": _handle_regen_voz,
    "approve": _handle_approve,
    "descartar": _handle_descartar,
}


# --- Ruteo de updates ---


def _safe_answer_callback_query(callback_id: str, text: str = "") -> None:
    """answerCallbackQuery puede fallar (ej. el callback ya expiro/es invalido) y
    eso NUNCA debe frenar el procesamiento real del boton ni tirar abajo el run()."""
    try:
        telegram_notify.answer_callback_query(callback_id, text=text)
    except Exception as e:
        print(f"[telegram_listener] aviso: no se pudo responder el callback {callback_id}: {e}")


def _process_callback_query(cq: dict) -> None:
    callback_id = cq["id"]
    data = cq.get("data", "")
    action, _, draft_id = data.partition(":")

    handler = CALLBACK_HANDLERS.get(action)
    if handler is None:
        _safe_answer_callback_query(callback_id, text="Accion desconocida.")
        return

    # Se responde el callback ANTES de procesar: asi queda respondido incluso si
    # el handler tarda, falla, o el proceso se corta a mitad de camino.
    _safe_answer_callback_query(callback_id, text=CALLBACK_ACK_TEXT.get(action, ""))

    try:
        handler(draft_id)
    except Exception as e:
        print(f"[telegram_listener] error procesando '{data}': {e}")
        try:
            telegram_notify.send_text(
                telegram_notify.chat_id(),
                f"⚠️ Error procesando '{action}' para el draft {draft_id}: {e}",
            )
        except telegram_notify.TelegramNotifyError:
            pass


def _handle_text_reply(message: dict) -> None:
    replied_id = message["reply_to_message"]["message_id"]
    draft = telegram_notify.find_draft_by_message_id(replied_id)
    if draft is None:
        return  # no es reply a un preview nuestro, se ignora

    notas = draft.get("notas_usuario", [])
    notas.append(message["text"])
    telegram_notify.update_draft(draft["channel_slug"], draft["draft_id"], notas_usuario=notas)
    telegram_notify.send_text(
        telegram_notify.chat_id(),
        f"📝 Nota guardada para \"{draft['title']}\". Se va a tener en cuenta la proxima vez que regeneres.",
    )


def _process_message(message: dict) -> None:
    if "text" not in message or "reply_to_message" not in message:
        return
    _handle_text_reply(message)


def run() -> None:
    offset = _load_offset()
    updates = telegram_notify.get_updates(offset)

    if not updates:
        return  # nada nuevo: terminar en silencio, no spamear

    for update in updates:
        try:
            if "callback_query" in update:
                _process_callback_query(update["callback_query"])
            elif "message" in update:
                _process_message(update["message"])
        except Exception as e:
            # Ultima red de seguridad: un error no previsto aca nunca debe dejar
            # el offset trabado reprocesando el mismo update para siempre.
            print(f"[telegram_listener] error inesperado procesando update {update.get('update_id')}: {e}")

        offset = update["update_id"] + 1
        _save_offset(offset)  # se guarda tras cada update, no solo al final del batch


if __name__ == "__main__":
    run()
