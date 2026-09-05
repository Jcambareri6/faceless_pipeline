"""Paso 15: herramienta manual OPCIONAL para correr el pipeline completo desde
la terminal, para un tema puntual, sin pasar por Telegram.

El flujo normal de produccion es 100% Telegram: orchestrator.py (Paso 12) +
telegram_listener.py (Paso 13), corridos por GitHub Actions (Paso 14). Esto
es solo para debug o para probar rapido un tema especifico en tu maquina.
"""

import argparse
import uuid
from pathlib import Path

import config
import fetch_footage
import generate_audio
import generate_metadata
import generate_script
import generate_subtitles
import generate_video

OUTPUT_DIR = Path(__file__).parent / "manual_runs"


def run(channel_slug: str, title: str, summary: str) -> None:
    channel = config.load_channel(channel_slug)
    run_id = uuid.uuid4().hex[:8]
    media_dir = OUTPUT_DIR / run_id
    media_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {channel.CHANNEL_EMOJI} {channel.CHANNEL_SLUG} | run {run_id} ===\n")

    print("Generando guion...")
    scenes = generate_script.generate_script(channel, title, summary)
    total_duration = sum(s["duration_estimate"] for s in scenes)
    print(f"{len(scenes)} escenas, ~{total_duration:.0f}s:\n")
    for i, s in enumerate(scenes, start=1):
        print(f"  {i}. {s['text']}")
    print()

    print("Generando audio...")
    audio_path = media_dir / "narration.mp3"
    generate_audio.generate_audio(generate_audio.scenes_to_narration(scenes), channel.TTS_VOICE, str(audio_path))

    print("Generando subtitulos...")
    generate_subtitles.generate_subtitles(str(audio_path), str(audio_path.with_suffix(".ass")))

    print("Buscando footage...")
    footage_results = fetch_footage.fetch_footage_for_scenes(scenes, channel, str(media_dir / "footage"))

    print("Armando preview...")
    preview = generate_video.generate_video(
        channel, scenes, footage_results, str(audio_path), str(media_dir), mode="preview"
    )
    print(f"\nPreview listo: {preview['video_path']}")
    if preview["fallback_count"] > 0:
        print(f"({preview['fallback_count']}/{preview['total_scenes']} escenas usaron b-roll de fallback)")

    answer = input("\nAprobar y generar version final? [y/N]: ").strip().lower()
    if answer != "y":
        print(f"Descartado. Los archivos intermedios quedan en {media_dir}")
        return

    print("\nGenerando version final...")
    final = generate_video.generate_video(
        channel, scenes, footage_results, str(audio_path), str(media_dir), mode="final"
    )

    print("Generando metadata...")
    metadata = generate_metadata.generate_metadata(channel, scenes, title)

    print(f"\nFinal listo: {final['video_path']}\n")
    print(f"TÍTULO:\n{metadata['title']}\n")
    print(f"DESCRIPCIÓN:\n{metadata['description']}\n")
    print(f"HASHTAGS:\n{' '.join('#' + h.lstrip('#') for h in metadata['hashtags'])}\n")
    print(f"TIKTOK CAPTION:\n{metadata['tiktok_caption']}\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Corre el pipeline completo a mano para un tema puntual, sin Telegram. "
            "El flujo normal de produccion es 100%% Telegram (ver orchestrator.py / "
            "telegram_listener.py); esto es solo para debug."
        )
    )
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--title", required=True, help="Titulo/tema a convertir en guion")
    parser.add_argument("--summary", default="", help="Resumen opcional del tema")
    args = parser.parse_args()

    run(args.channel, args.title, args.summary)


if __name__ == "__main__":
    main()
