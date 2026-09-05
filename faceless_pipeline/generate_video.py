"""Paso 8: armar el video (preview o final) a partir de los clips por escena,
el audio de narracion y los subtitulos.

Pipeline, igual en ambos modos (solo cambian los parametros de output):
1. Por escena: recortar el clip a su duracion y escalar/recortar al centro a 9:16.
2. Concatenar todas las escenas (ffmpeg concat demuxer).
3. Mux del audio de narracion + musica de fondo (si hay) + subtitulos
   quemados + encode final segun mode.

Convencion: los subtitulos se buscan en el mismo path que audio_path pero con
extension .ass -- palabra por palabra, estilo caption animado (asi los
genera generate_subtitles.py en el Paso 6/13).

Musica de fondo: si existen pistas en music/{channel_slug}/, se elige una al
azar y se mezcla bajito debajo de la narracion. Si la carpeta no existe o
esta vacia, el video se genera igual, sin musica (no es obligatoria).
"""

import os
import random
import shutil
import subprocess
from pathlib import Path

import config

MUSIC_DIR = Path(__file__).parent / "music"
MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg"}
MUSIC_VOLUME = 0.10  # bajito: 10% del volumen original de la pista
MUSIC_FADE_IN_SECONDS = 2

_MODE_SETTINGS = {
    "preview": {
        "width": config.PREVIEW_WIDTH,
        "height": config.PREVIEW_HEIGHT,
        "preset": "ultrafast",
        "crf": "30",
        "maxrate": "1000k",
        "bufsize": "2000k",
    },
    "final": {
        "width": config.VIDEO_WIDTH,
        "height": config.VIDEO_HEIGHT,
        "preset": "medium",
        "crf": "19",
        "maxrate": None,
        "bufsize": None,
    },
}


class VideoGenerationError(Exception):
    pass


def _ffmpeg_binary() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    # Fallback: instalacion via winget (ver README, seccion instalacion) no
    # siempre queda en el PATH de la sesion actual sin reiniciar la terminal.
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.exists():
        for candidate in winget_packages.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"):
            return str(candidate)
    raise VideoGenerationError(
        "No se encontro ffmpeg en PATH. Instalalo y asegurate de que el "
        "comando 'ffmpeg' funcione en una terminal nueva (ver README)."
    )


def _run_ffmpeg(args: list) -> None:
    cmd = [_ffmpeg_binary(), "-y", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoGenerationError(f"ffmpeg fallo.\ncomando: {' '.join(cmd)}\nstderr: {result.stderr}")


def _normalize_scene_clip(clip_path: str, duration: float, width: int, height: int, output_path: Path) -> None:
    """Recorta el clip a `duration` segundos y lo escala/recorta al centro a width x height."""
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    _run_ffmpeg(
        [
            "-i", clip_path,
            "-t", f"{duration}",
            "-vf", vf,
            "-r", "30",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-an",
            str(output_path),
        ]
    )


def _concat_clips(clip_paths: list, list_file: Path, output_path: Path) -> None:
    list_content = "\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in clip_paths)
    list_file.write_text(list_content, encoding="utf-8")
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output_path)])


def _escape_subtitles_path(path) -> str:
    """El filtro subtitles= de ffmpeg interpreta ':' como separador de opciones,
    asi que hay que escapar los dos puntos de la letra de unidad en Windows."""
    return Path(path).resolve().as_posix().replace(":", "\\:")


def _pick_music_track(channel):
    """Elige una pista al azar de music/{channel_slug}/. Devuelve None si la
    carpeta no existe o no tiene ningun archivo de audio (la musica es opcional)."""
    channel_music_dir = MUSIC_DIR / channel.CHANNEL_SLUG
    if not channel_music_dir.exists():
        return None
    tracks = [p for p in channel_music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTENSIONS]
    if not tracks:
        return None
    return random.choice(tracks)


def _mux_final(
    video_path: Path, audio_path: str, subtitles_path: Path, music_path, output_path: Path, mode: str
) -> None:
    settings = _MODE_SETTINGS[mode]
    subtitles_filter = f"subtitles='{_escape_subtitles_path(subtitles_path)}'"

    args = ["-i", str(video_path), "-i", audio_path]

    if music_path:
        # -stream_loop -1: la pista se loopea indefinidamente, amix con
        # duration=first la recorta a la duracion de la narracion (primer
        # input de audio). Fade-in de arranque, sin fade-out para no tener
        # que ffprobear la duracion exacta de antemano: al 10% de volumen el
        # corte al final del video no se nota.
        args += ["-stream_loop", "-1", "-i", str(music_path)]
        filter_complex = (
            f"[0:v]{subtitles_filter}[vout];"
            f"[2:a]volume={MUSIC_VOLUME},afade=t=in:st=0:d={MUSIC_FADE_IN_SECONDS}[music];"
            f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        args += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"]
    else:
        filter_complex = f"[0:v]{subtitles_filter}[vout]"
        args += ["-filter_complex", filter_complex, "-map", "[vout]", "-map", "1:a:0"]

    args += ["-c:v", "libx264", "-preset", settings["preset"], "-crf", settings["crf"]]
    if settings["maxrate"]:
        args += ["-maxrate", settings["maxrate"], "-bufsize", settings["bufsize"]]
    args += ["-c:a", "aac", "-b:a", "128k", "-shortest", str(output_path)]
    _run_ffmpeg(args)


def generate_video(channel, scenes: list, footage_results: list, audio_path: str, output_dir: str, mode: str) -> dict:
    """Genera el video en modo 'preview' o 'final'.

    Devuelve {"video_path", "fallback_count", "total_scenes"}.
    """
    if mode not in _MODE_SETTINGS:
        raise ValueError(f"mode invalido: {mode!r} (esperado 'preview' o 'final')")
    if len(scenes) != len(footage_results):
        raise VideoGenerationError("scenes y footage_results deben tener la misma longitud.")

    subtitles_path = Path(audio_path).with_suffix(".ass")
    if not subtitles_path.exists():
        raise VideoGenerationError(
            f"No se encontraron subtitulos en {subtitles_path}; correr "
            f"generate_subtitles.py sobre {audio_path} antes de generate_video()."
        )

    output_dir = Path(output_dir)
    tmp_dir = output_dir / f"_tmp_{mode}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    settings = _MODE_SETTINGS[mode]
    scene_clip_paths = []
    for i, (scene, footage) in enumerate(zip(scenes, footage_results)):
        clip_out = tmp_dir / f"scene_{i:02d}.mp4"
        _normalize_scene_clip(
            footage["clip_path"],
            scene["duration_estimate"],
            settings["width"],
            settings["height"],
            clip_out,
        )
        scene_clip_paths.append(clip_out)

    concat_output = tmp_dir / "concatenated.mp4"
    _concat_clips(scene_clip_paths, tmp_dir / "concat_list.txt", concat_output)

    music_path = _pick_music_track(channel)
    print(f"[generate_video] musica de fondo: {music_path.name if music_path else 'ninguna'}")

    output_path = output_dir / f"{mode}.mp4"
    _mux_final(concat_output, audio_path, subtitles_path, music_path, output_path, mode)

    fallback_count = sum(1 for f in footage_results if f["match_quality"] == "fallback")

    return {
        "video_path": str(output_path),
        "fallback_count": fallback_count,
        "total_scenes": len(scenes),
    }


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))

    parser = argparse.ArgumentParser(description="Prueba standalone de generate_video.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--audio", required=True, help="mp3 ya generado (debe existir un .ass con el mismo nombre)")
    parser.add_argument("--clips", required=True, nargs="+", help="paths a clips de video existentes, uno por escena")
    parser.add_argument("--mode", choices=["preview", "final"], default="preview")
    parser.add_argument("--output-dir", default="test_video_out")
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    fake_scenes = [
        {"text": f"scene {i}", "visual_keywords": ["a", "b", "c"], "duration_estimate": 3.0}
        for i in range(len(args.clips))
    ]
    fake_footage = [
        {"clip_path": p, "matched_keyword": "test", "match_quality": "specific", "clip_id": i}
        for i, p in enumerate(args.clips)
    ]
    result = generate_video(ch, fake_scenes, fake_footage, args.audio, args.output_dir, args.mode)
    print(result)
