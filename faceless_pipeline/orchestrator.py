"""Paso 12: orquesta el escaneo de temas -> top 3 -> guion -> Telegram.

CLI: python orchestrator.py --channel money_curiosities

Corrido 2 veces/dia por .github/workflows/topic-scan.yml (Paso 14).
Nunca falla en silencio: si no hay temas nuevos, o si fallan los 3
intentos de generar guion, avisa por Telegram en vez de terminar sin
avisar nada.
"""

import argparse
import uuid

import config
import fetch_topics
import generate_script
import rank_topics
import telegram_notify

TOP_N_TOPICS = 3


def run(channel_slug: str) -> None:
    channel = config.load_channel(channel_slug)

    print(f"[orchestrator] {channel.CHANNEL_SLUG}: buscando temas nuevos...")
    candidates = fetch_topics.fetch_candidate_topics(channel)

    if not candidates:
        print(f"[orchestrator] {channel.CHANNEL_SLUG}: no hay temas nuevos.")
        telegram_notify.send_text(
            telegram_notify.chat_id(),
            f"{channel.CHANNEL_EMOJI} {channel.CHANNEL_SLUG}: no se encontraron temas "
            f"nuevos en este escaneo (los feeds no trajeron nada que no se haya usado ya).",
        )
        return

    ranked = rank_topics.rank_topics(candidates, channel)
    top_topics = ranked[:TOP_N_TOPICS]
    print(
        f"[orchestrator] {channel.CHANNEL_SLUG}: {len(candidates)} candidatos, "
        f"generando guiones para el top {len(top_topics)}..."
    )

    used_topic_ids = []
    generated = 0

    for topic in top_topics:
        draft_id = uuid.uuid4().hex[:12]
        try:
            scenes = generate_script.generate_script(channel, topic["title"], topic["summary"])
        except generate_script.ScriptGenerationError as e:
            print(f"[orchestrator] aviso: fallo generate_script para '{topic['title']}': {e}")
            continue

        telegram_notify.send_telegram_draft(channel, draft_id, topic["title"], scenes)
        used_topic_ids.append(topic["id"])
        generated += 1

    # Solo se marcan como usados los temas que efectivamente se convirtieron en
    # guion y se mandaron: los que fallaron quedan disponibles para el proximo scan.
    fetch_topics.mark_topics_used(channel, used_topic_ids)

    if generated == 0:
        telegram_notify.send_text(
            telegram_notify.chat_id(),
            f"{channel.CHANNEL_EMOJI} {channel.CHANNEL_SLUG}: se encontraron temas nuevos "
            f"pero fallo la generacion de guion para los {len(top_topics)} candidatos "
            f"principales. Revisar logs de la corrida.",
        )
    else:
        print(f"[orchestrator] {channel.CHANNEL_SLUG}: {generated} guion(es) generado(s) y enviados a Telegram.")


def main():
    parser = argparse.ArgumentParser(description="Paso 12: escanea temas y manda guiones candidatos a Telegram")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    args = parser.parse_args()
    run(args.channel)


if __name__ == "__main__":
    main()
