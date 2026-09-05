"""Paso 5: generar el audio de narracion con edge-tts (gratis, sin API key)."""

import asyncio
from pathlib import Path

import edge_tts


async def _generate_audio_async(text: str, voice: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(output_path)


def scenes_to_narration(scenes: list) -> str:
    """Concatena el 'text' de cada escena en orden -> narracion continua a sintetizar."""
    return " ".join(s["text"].strip() for s in scenes)


def generate_audio(text: str, voice: str, output_path: str) -> str:
    """Genera un archivo de audio (mp3) con la narracion completa.

    text: texto a narrar (tipicamente el resultado de scenes_to_narration()).
    voice: identificador de voz edge-tts (channel.TTS_VOICE).
    output_path: donde guardar el audio.
    """
    if not text or not text.strip():
        raise ValueError("El texto para generar audio esta vacio.")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_generate_audio_async(text.strip(), voice, output_path))
    return output_path


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import config

    parser = argparse.ArgumentParser(description="Prueba standalone de generate_audio.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument(
        "--text",
        default="This is a quick test of the text to speech voice for this channel.",
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    output = args.output or f"test_audio_{ch.CHANNEL_SLUG}.mp3"
    path = generate_audio(args.text, ch.TTS_VOICE, output)
    size_kb = Path(path).stat().st_size / 1024
    print(f"Audio generado en: {path} ({size_kb:.1f} KB, voz={ch.TTS_VOICE})")
