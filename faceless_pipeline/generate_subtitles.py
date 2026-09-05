"""Paso 6: generar subtitulos a partir del audio, con Whisper local.

El formato se elige por la extension de output_path:
- ".ass": subtitulos PALABRA POR PALABRA (word_timestamps de Whisper), una
  sola palabra en pantalla a la vez, estilo caption animado tipo
  TikTok/Shorts. Es lo que usa el pipeline de video real (generate_video.py).
- cualquier otra extension (".srt" por default): subtitulos por segmento,
  como antes. Lo sigue usando competitor_research.py para extraer el texto
  plano del gancho transcripto de la competencia -- ahi no importa el
  estilo visual, solo el texto.
"""

from pathlib import Path

import whisper

MODEL_NAME = "base"

# Estilo de los subtitulos .ass: una palabra grande, centrada, cerca del
# tercio inferior. DejaVu Sans esta preinstalada en la mayoria de las
# imagenes de Ubuntu (GitHub Actions) y tiene variante bold; en Windows
# libass cae a un fallback razonable si no la encuentra.
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,DejaVu Sans,90,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,60,60,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_model_cache = {}


def _get_model():
    """Cachea el modelo cargado en memoria: cargarlo tarda varios segundos."""
    if MODEL_NAME not in _model_cache:
        _model_cache[MODEL_NAME] = whisper.load_model(MODEL_NAME)
    return _model_cache[MODEL_NAME]


def _format_srt_timestamp(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    hours, ms_total = divmod(ms_total, 3_600_000)
    minutes, ms_total = divmod(ms_total, 60_000)
    secs, millis = divmod(ms_total, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_ass_timestamp(seconds: float) -> str:
    """Formato de tiempo de .ass: H:MM:SS.cc (centisegundos)."""
    cs_total = round(seconds * 100)
    hours, cs_total = divmod(cs_total, 360_000)
    minutes, cs_total = divmod(cs_total, 6_000)
    secs, cs = divmod(cs_total, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _segments_to_srt(segments) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _format_srt_timestamp(seg["start"])
        end = _format_srt_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _words_to_ass(segments) -> str:
    lines = []
    for seg in segments:
        for w in seg.get("words", []):
            word = w["word"].strip().upper()
            if not word:
                continue
            start = _format_ass_timestamp(w["start"])
            end = _format_ass_timestamp(w["end"])
            lines.append(f"Dialogue: 0,{start},{end},Word,,0,0,0,,{word}")
    return ASS_HEADER + "\n".join(lines) + "\n"


def generate_subtitles(audio_path: str, output_path: str, language: str = "en") -> str:
    """Transcribe audio_path con Whisper (modelo 'base') y escribe subtitulos
    en output_path, en el formato indicado por su extension (ver docstring
    del modulo).

    language: idioma del audio (default "en", los dos canales de produccion
    son en ingles).

    Devuelve output_path.
    """
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"No existe el audio: {audio_path}")

    is_ass = Path(output_path).suffix.lower() == ".ass"

    model = _get_model()
    result = model.transcribe(audio_path, language=language, verbose=False, word_timestamps=is_ass)

    content = _words_to_ass(result["segments"]) if is_ass else _segments_to_srt(result["segments"])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))

    parser = argparse.ArgumentParser(description="Prueba standalone de generate_subtitles.py")
    parser.add_argument("--audio", required=True, help="Path a un archivo de audio existente")
    parser.add_argument("--output", default=None)
    parser.add_argument("--language", default="en")
    parser.add_argument("--format", choices=["ass", "srt"], default="ass")
    args = parser.parse_args()

    output = args.output or str(Path(args.audio).with_suffix(f".{args.format}"))
    path = generate_subtitles(args.audio, output, language=args.language)
    print(f"Subtitulos generados en: {path}\n")
    print(Path(path).read_text(encoding="utf-8"))
