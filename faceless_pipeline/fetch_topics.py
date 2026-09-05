"""Paso 2: descubrir temas candidatos desde los RSS feeds de un canal.

El cache topics_seen_{slug}.json guarda los ids de temas que ya se
convirtieron en un guion (no todo lo que se vio en el feed). Como cada
canal tiene su propio archivo de cache y sus propios RSS_FEEDS, un mismo
tema nunca se repite dentro de un canal ni queda compartido entre
canales.
"""

import json
import re
from html import unescape
from pathlib import Path

import feedparser

CACHE_DIR = Path(__file__).parent
MAX_SUMMARY_CHARS = 500
MAX_SEEN_IDS = 1000  # tope de ids viejos que conserva el cache


def _cache_path(channel) -> Path:
    return CACHE_DIR / f"topics_seen_{channel.CHANNEL_SLUG}.json"


def _load_seen_ids(channel) -> set:
    path = _cache_path(channel)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return set(data.get("seen_ids", []))


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_id(entry: dict) -> str:
    """Algunos feeds (ej. investing.com) no traen id/guid: usamos el link como fallback."""
    return entry.get("id") or entry.get("link") or ""


def fetch_candidate_topics(channel) -> list[dict]:
    """Trae items de todos los RSS_FEEDS del canal, filtrando los ya usados.

    Devuelve lista de dicts:
    {id, title, summary, link, published, source_feed}
    """
    seen_ids = _load_seen_ids(channel)
    candidates = []
    seen_in_this_run = set()

    for feed_url in channel.RSS_FEEDS:
        parsed = feedparser.parse(feed_url)
        if parsed.bozo and not parsed.entries:
            print(
                f"[fetch_topics] aviso: no se pudo leer {feed_url}: "
                f"{parsed.get('bozo_exception', 'error desconocido')}"
            )
            continue

        for entry in parsed.entries:
            entry_id = _entry_id(entry)
            if not entry_id or entry_id in seen_ids or entry_id in seen_in_this_run:
                continue
            seen_in_this_run.add(entry_id)
            candidates.append(
                {
                    "id": entry_id,
                    "title": _clean_html(entry.get("title", "")),
                    "summary": _clean_html(entry.get("summary", ""))[:MAX_SUMMARY_CHARS],
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source_feed": feed_url,
                }
            )

    return candidates


def mark_topics_used(channel, topic_ids: list[str]) -> None:
    """Agrega topic_ids al cache de usados. Llamado por orchestrator.py tras generar guiones."""
    if not topic_ids:
        return
    path = _cache_path(channel)
    seen_ids = _load_seen_ids(channel)
    seen_ids.update(topic_ids)
    trimmed = list(seen_ids)[-MAX_SEEN_IDS:]
    path.write_text(
        json.dumps({"seen_ids": trimmed}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import config

    parser = argparse.ArgumentParser(description="Prueba standalone de fetch_topics.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    topics = fetch_candidate_topics(ch)
    print(f"{len(topics)} temas nuevos encontrados para {ch.CHANNEL_SLUG}:\n")
    for t in topics[:10]:
        print(f"- [{t['source_feed']}] {t['title']}")
        if t["summary"]:
            print(f"    {t['summary'][:120]}...")
    if len(topics) > 10:
        print(f"... y {len(topics) - 10} mas")
