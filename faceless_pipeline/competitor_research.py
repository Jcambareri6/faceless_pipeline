"""Paso 9: investigar competencia real en YouTube (shorts recientes del mismo nicho).

La YouTube Data API v3 no tiene un filtro nativo para "es un Short": se
aproxima en dos pasos -> search.list con videoDuration="short" (<4 min,
el filtro mas angosto que ofrece la API) y despues se afina con
videos.list, descartando todo lo que supere MAX_SHORT_DURATION_SECONDS
(el limite real de Shorts, extendido por YouTube a 3 minutos). No es
perfecto (puede colar algun video corto que no sea tecnicamente un
Short, o perderse alguno mal categorizado), pero es la mejor
aproximacion posible con esta API.
"""

import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import rank_topics  # reuso STOPWORDS para tokenizar titulos

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

LOOKBACK_DAYS = 30
MAX_SHORT_DURATION_SECONDS = 183
INSIGHTS_MAX_AGE_DAYS = 7
CACHE_DIR = Path(__file__).parent

QUESTION_WORDS = ("why", "how", "what", "when", "where", "who", "did", "is", "are", "was", "were", "could", "would", "will")


class CompetitorResearchError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise CompetitorResearchError("Falta la variable de entorno YOUTUBE_API_KEY.")
    return key


def _iso8601_duration_to_seconds(duration: str) -> int:
    """Convierte formato ISO8601 de YouTube ('PT1M30S') a segundos."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return 0
    h, m, s = (int(x) if x else 0 for x in match.groups())
    return h * 3600 + m * 60 + s


def search_competitor_videos(channel, max_results: int = 25) -> list:
    """Busca shorts recientes (ultimos 30 dias) relacionados al nicho del canal
    y trae sus estadisticas de vistas/likes.

    Devuelve lista de dicts (ordenada por view_count descendente):
    {video_id, title, description, view_count, like_count, duration_seconds, published_at}
    """
    api_key = _api_key()
    published_after = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # NICHE_DESCRIPTION es un parrafo largo (pensado para prompts de Claude), y
    # YouTube Search matchea mal con oraciones largas: se usa una query corta
    # dedicada (fallback a NICHE_DESCRIPTION si el canal no la define).
    search_query = getattr(channel, "COMPETITOR_SEARCH_QUERY", channel.NICHE_DESCRIPTION)

    search_params = {
        "part": "snippet",
        "q": search_query,
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": min(max_results, 50),
        "key": api_key,
    }
    resp = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]

    if not video_ids:
        return []

    videos_params = {
        "part": "statistics,snippet,contentDetails",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    resp = requests.get(YOUTUBE_VIDEOS_URL, params=videos_params, timeout=15)
    resp.raise_for_status()
    video_items = resp.json().get("items", [])

    results = []
    for item in video_items:
        duration_seconds = _iso8601_duration_to_seconds(item.get("contentDetails", {}).get("duration", ""))
        if duration_seconds > MAX_SHORT_DURATION_SECONDS:
            continue
        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        results.append(
            {
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "duration_seconds": duration_seconds,
                "published_at": snippet.get("publishedAt", ""),
            }
        )

    results.sort(key=lambda v: v["view_count"], reverse=True)
    return results


def _extract_hashtags(description: str) -> list:
    return re.findall(r"#(\w+)", description or "")


def _tokenize_title(title: str) -> list:
    words = re.findall(r"[a-zA-Z']+", title.lower())
    return [w for w in words if w not in rank_topics.STOPWORDS and len(w) > 2]


def _extract_description_hook(description: str) -> str:
    """La primera linea/oracion no vacia de la descripcion suele reflejar el
    gancho del video. Heuristica simple, no perfecta pero no requiere ningun
    llamado extra: ya tenemos la descripcion de videos.list."""
    if not description:
        return ""
    first_line = next((line.strip() for line in description.splitlines() if line.strip()), "")
    if not first_line:
        return ""
    match = re.match(r"^(.{1,140}?[.!?])(\s|$)", first_line)
    return match.group(1) if match else first_line[:140]


def _analyze_hook_patterns(hooks: list, source: str) -> dict:
    """Extrae patrones ESTRUCTURALES agregados (longitud promedio, % preguntas,
    etc.) de una lista de hooks. Nunca devuelve el texto de los hooks en si:
    solo estadisticas, para poder usarse como inspiracion sin copiar a nadie."""
    hooks = [h for h in hooks if h and h.strip()]
    if not hooks:
        return {}

    n = len(hooks)
    word_counts = [len(h.split()) for h in hooks]
    is_question = sum(1 for h in hooks if h.strip().endswith("?"))
    starts_with_number = sum(1 for h in hooks if re.match(r"^\d", h.strip()))
    starts_with_question_word = sum(
        1 for h in hooks if h.strip().lower().split()[0].strip("?,.!¿") in QUESTION_WORDS
    )

    return {
        "avg_hook_length_words": round(sum(word_counts) / n, 1),
        "pct_hooks_are_questions": round(100 * is_question / n),
        "pct_hooks_start_with_number": round(100 * starts_with_number / n),
        "pct_hooks_start_with_question_word": round(100 * starts_with_question_word / n),
        "sample_size": n,
        "source": source,
    }


def _srt_to_plain_text(srt_content: str) -> str:
    lines = []
    for line in srt_content.splitlines():
        line = line.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        lines.append(line)
    return " ".join(lines)


def fetch_real_hook_transcripts(videos: list, max_videos: int = 5, hook_seconds: int = 8) -> list:
    """Nivel 3 (opcional, mas pesado): baja SOLO los primeros `hook_seconds`
    segundos de audio de los `max_videos` videos con mas vistas (yt-dlp) y
    transcribe ese gancho hablado con Whisper, para tener el patron real de
    como abren sus videos (no solo la descripcion).

    El audio se descarga a un directorio temporal y se borra al terminar:
    nunca se guarda ni se reproduce el contenido de nadie, solo se usa para
    derivar las mismas estadisticas agregadas de _analyze_hook_patterns.
    Requiere yt-dlp y ffmpeg. Si alguno de los dos falta o una descarga
    puntual falla, esa entrada se saltea (nunca frena todo el analisis).
    """
    import yt_dlp

    import generate_subtitles

    top_videos = sorted(videos, key=lambda v: v["view_count"], reverse=True)[:max_videos]
    hooks = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for v in top_videos:
            video_url = f"https://www.youtube.com/watch?v={v['video_id']}"
            out_template = str(Path(tmp_dir) / f"{v['video_id']}.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": out_template,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
                "download_ranges": yt_dlp.utils.download_range_func(None, [(0, hook_seconds)]),
                "force_keyframes_at_cuts": True,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
            except Exception as e:
                print(f"[competitor_research] aviso: no se pudo bajar audio de {v['video_id']}: {e}")
                continue

            audio_path = Path(tmp_dir) / f"{v['video_id']}.mp3"
            if not audio_path.exists():
                continue

            try:
                srt_path = audio_path.with_suffix(".srt")
                generate_subtitles.generate_subtitles(str(audio_path), str(srt_path), language="en")
                text = _srt_to_plain_text(srt_path.read_text(encoding="utf-8"))
                if text:
                    hooks.append(text)
            except Exception as e:
                print(f"[competitor_research] aviso: fallo transcribir hook de {v['video_id']}: {e}")

    return hooks


def analyze_competitor_data(videos: list, top_n: int = 10) -> dict:
    """De los `top_n` videos con mas vistas, extrae:
    a) palabras repetidas en titulos de mejor performance
    b) hashtags mas frecuentes en sus descripciones, rankeados
    c) longitud de titulo promedio (caracteres y palabras) de los que mejor andan
    d) hook_patterns: patrones estructurales del gancho (Nivel 2, desde la
       primera linea de la descripcion -- Nivel 3 los puede pisar con datos
       mas fieles, ver run_competitor_research)
    """
    if not videos:
        return {
            "top_title_words": [],
            "top_hashtags": [],
            "avg_title_length_chars": 0,
            "avg_title_length_words": 0,
            "sample_size": 0,
            "hook_patterns": {},
        }

    top_videos = sorted(videos, key=lambda v: v["view_count"], reverse=True)[:top_n]

    word_counter = Counter()
    hashtag_counter = Counter()
    char_lengths = []
    word_counts = []
    description_hooks = []

    for v in top_videos:
        word_counter.update(_tokenize_title(v["title"]))
        hashtag_counter.update(h.lower() for h in _extract_hashtags(v["description"]))
        char_lengths.append(len(v["title"]))
        word_counts.append(len(v["title"].split()))
        description_hooks.append(_extract_description_hook(v["description"]))

    return {
        "top_title_words": [w for w, _ in word_counter.most_common(15)],
        "top_hashtags": [h for h, _ in hashtag_counter.most_common(15)],
        "avg_title_length_chars": round(sum(char_lengths) / len(char_lengths), 1),
        "avg_title_length_words": round(sum(word_counts) / len(word_counts), 1),
        "sample_size": len(top_videos),
        "hook_patterns": _analyze_hook_patterns(description_hooks, source="video descriptions"),
    }


def _insights_path(channel_slug: str) -> Path:
    return CACHE_DIR / f"competitor_insights_{channel_slug}.json"


def save_insights(channel, insights: dict) -> Path:
    path = _insights_path(channel.CHANNEL_SLUG)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "insights": insights}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_recent_insights(channel_slug: str):
    """Devuelve el dict de insights si existe y tiene menos de INSIGHTS_MAX_AGE_DAYS
    de antiguedad, o None si no existe o esta vencido. generate_metadata.py (Paso 10)
    usa esto para decidir si recalcula o reusa."""
    path = _insights_path(channel_slug)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(payload["generated_at"])
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None

    if datetime.now(timezone.utc) - generated_at > timedelta(days=INSIGHTS_MAX_AGE_DAYS):
        return None
    return payload["insights"]


def run_competitor_research(channel, max_results: int = 25, use_audio_hooks: bool = True) -> dict:
    """Orquesta: busca videos, analiza, (opcionalmente) refina el hook_patterns
    con audio real, guarda en disco y devuelve los insights.

    use_audio_hooks=True intenta el Nivel 3 (yt-dlp + Whisper sobre el gancho
    real hablado de los videos top). Es mas lento (se baja y transcribe audio)
    pero mas fiel que solo mirar la descripcion. Si yt-dlp/ffmpeg no estan
    disponibles o algo falla, se loggea un aviso y se sigue con los patrones
    derivados de la descripcion (Nivel 2) sin cortar el resto del analisis.
    """
    videos = search_competitor_videos(channel, max_results=max_results)
    insights = analyze_competitor_data(videos)

    if use_audio_hooks and videos:
        try:
            audio_hooks = fetch_real_hook_transcripts(videos)
            audio_hook_patterns = _analyze_hook_patterns(audio_hooks, source="real audio transcripts")
            if audio_hook_patterns:
                insights["hook_patterns"] = audio_hook_patterns
        except Exception as e:
            print(
                f"[competitor_research] aviso: fallo el analisis de audio real "
                f"({e}); se usan los patrones derivados de descripciones."
            )

    save_insights(channel, insights)
    print(
        f"[competitor_research] {channel.CHANNEL_SLUG}: {insights['sample_size']} videos "
        f"analizados, {len(insights['top_hashtags'])} hashtags detectados, "
        f"hook_patterns source={insights['hook_patterns'].get('source', 'n/a')}"
    )
    return insights


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import config

    parser = argparse.ArgumentParser(description="Prueba standalone de competitor_research.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--max-results", type=int, default=25)
    parser.add_argument(
        "--no-audio-hooks", action="store_true", help="Saltea el Nivel 3 (yt-dlp+Whisper), mas rapido"
    )
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    result = run_competitor_research(ch, max_results=args.max_results, use_audio_hooks=not args.no_audio_hooks)
    print(json.dumps(result, indent=2, ensure_ascii=False))
