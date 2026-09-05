"""Paso 7: conseguir un clip de stock footage por escena.

Proveedores: Pexels y Pixabay (ambos gratis). Para cada nivel de
especificidad de keyword se prueban TODOS los proveedores antes de bajar
al siguiente nivel, asi match_quality sigue reflejando que tan especifico
fue el keyword, no que proveedor lo sirvio. Un proveedor con menos de
MIN_POOL_SIZE candidatos utilizables para una query se trata como si no
hubiera encontrado nada (ver _find_usable_clip): un pool muy chico sugiere
un keyword demasiado especifico/raro, mas que un buen match.

Cadena de intentos por escena: visual_keywords[0] (especifico, todos los
proveedores) -> visual_keywords[1] (amplio, todos los proveedores) ->
visual_keywords[2] (amplio/generico, todos los proveedores) -> si todo eso
falla, un clip random de channel.FALLBACK_KEYWORDS ("fallback", todos los
proveedores). Nunca deja una escena sin clip: si ni siquiera los
FALLBACK_KEYWORDS devuelven algo usable en ningun proveedor, levanta
FootageError en vez de producir un video roto en silencio.
"""

import os
import random
from pathlib import Path

import requests

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"

RESULTS_PER_QUERY = 15
DURATION_BUFFER_SECONDS = 1.0  # margen sobre duration_estimate para poder recortar en ffmpeg
MIN_VIDEO_WIDTH = 640  # por debajo de esto, calidad insuficiente
MIN_POOL_SIZE = 3  # menos candidatos utilizables que esto = keyword demasiado raro, se descarta el pool

# Orden de intento de proveedores dentro de cada nivel de keyword.
PROVIDERS = ["pexels", "pixabay"]

# visual_keywords[0] = "specific" (calidad de match maxima).
# visual_keywords[1] y [2] son ambos progresivamente mas amplios que el primero,
# asi que los dos mapean a "broad". FALLBACK_KEYWORDS del canal = "fallback".
_QUALITY_BY_KEYWORD_INDEX = {0: "specific", 1: "broad", 2: "broad"}

_warned_missing_key = set()  # evita repetir el mismo aviso de key faltante en cada escena


class FootageError(Exception):
    """Ni siquiera los FALLBACK_KEYWORDS del canal devolvieron un clip usable
    en ningun proveedor."""


def _warn_once(provider: str, message: str) -> None:
    if provider not in _warned_missing_key:
        print(f"[fetch_footage] aviso: {message}")
        _warned_missing_key.add(provider)


# --- Pexels ---


def _pexels_search_raw(query: str) -> list:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        _warn_once("pexels", "falta PEXELS_API_KEY, se salta este proveedor.")
        return []

    headers = {"Authorization": api_key}
    params = {"query": query, "orientation": "portrait", "per_page": RESULTS_PER_QUERY}
    try:
        resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if videos:
            return videos

        # sin resultados verticales: reintenta sin filtro de orientacion (se
        # recorta al centro despues, en generate_video.py)
        params.pop("orientation")
        resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("videos", [])
    except requests.RequestException as e:
        print(f"[fetch_footage] aviso: fallo la busqueda en Pexels '{query}': {e}")
        return []


def _pick_best_pexels_file(video_files: list):
    mp4_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
    candidates = [f for f in mp4_files if f.get("width", 0) >= MIN_VIDEO_WIDTH]
    if not candidates:
        return None
    candidates.sort(key=lambda f: f["width"])
    return candidates[0]


def _search_pexels_normalized(query: str) -> list:
    """Devuelve candidatos normalizados: {id, duration, download_url, width, provider}."""
    normalized = []
    for video in _pexels_search_raw(query):
        best_file = _pick_best_pexels_file(video.get("video_files", []))
        if not best_file:
            continue
        normalized.append(
            {
                "id": f"pexels:{video['id']}",
                "duration": video.get("duration", 0),
                "download_url": best_file["link"],
                "width": best_file["width"],
                "provider": "pexels",
            }
        )
    return normalized


# --- Pixabay ---


def _pixabay_search_raw(query: str) -> list:
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        _warn_once("pixabay", "falta PIXABAY_API_KEY, se salta este proveedor.")
        return []

    params = {"key": api_key, "q": query, "per_page": RESULTS_PER_QUERY, "safesearch": "true"}
    try:
        resp = requests.get(PIXABAY_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except requests.RequestException as e:
        print(f"[fetch_footage] aviso: fallo la busqueda en Pixabay '{query}': {e}")
        return []


def _pick_best_pixabay_file(videos: dict):
    """Pixabay ofrece tamanios fijos (tiny/small/medium/large), todos horizontales
    (no tiene filtro de orientacion como Pexels). Elegimos el mas chico que
    cumpla MIN_VIDEO_WIDTH."""
    for size in ("tiny", "small", "medium", "large"):
        info = videos.get(size)
        if info and info.get("width", 0) >= MIN_VIDEO_WIDTH:
            return info
    return None


def _search_pixabay_normalized(query: str) -> list:
    normalized = []
    for hit in _pixabay_search_raw(query):
        best = _pick_best_pixabay_file(hit.get("videos", {}))
        if not best:
            continue
        normalized.append(
            {
                "id": f"pixabay:{hit['id']}",
                "duration": hit.get("duration", 0),
                "download_url": best["url"],
                "width": best["width"],
                "provider": "pixabay",
            }
        )
    return normalized


_PROVIDER_SEARCH_FUNCS = {
    "pexels": _search_pexels_normalized,
    "pixabay": _search_pixabay_normalized,
}


def _find_usable_clip(query: str, min_duration: float, avoid_clip_ids: set):
    """Prueba cada proveedor de PROVIDERS en orden. Un proveedor solo se acepta
    si junta al menos MIN_POOL_SIZE candidatos utilizables (duracion ok, no
    evitados): un pool mas chico sugiere que el keyword es demasiado
    especifico/raro para ese proveedor, asi que se trata igual que "sin
    resultados" y se prueba el siguiente proveedor (y, si ninguno alcanza el
    minimo, el llamador baja al siguiente keyword, mas amplio).

    Devuelve el primer candidato del primer pool que alcance el minimo, o None.
    """
    for provider in PROVIDERS:
        candidates = _PROVIDER_SEARCH_FUNCS[provider](query)
        usable = [
            c for c in candidates if c["id"] not in avoid_clip_ids and c["duration"] >= min_duration
        ]
        if len(usable) < MIN_POOL_SIZE:
            continue
        return usable[0]
    return None


def _download_clip(url: str, output_path: Path) -> None:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)


def fetch_footage_for_scenes(scenes: list, channel, output_dir: str, avoid_clip_ids=None) -> list:
    """Descarga un clip por escena. Devuelve lista alineada con `scenes`, cada item:
    {"clip_path", "matched_keyword", "match_quality", "clip_id", "provider"}.

    avoid_clip_ids: ids ya usados en un preview anterior de este mismo draft
    (formato "proveedor:id"), para variedad real al regenerar (Paso 13, regen_video).
    """
    avoid_clip_ids = set(avoid_clip_ids or set())
    output_dir = Path(output_dir)
    results = []

    for i, scene in enumerate(scenes):
        min_duration = scene["duration_estimate"] + DURATION_BUFFER_SECONDS
        chosen = matched_keyword = match_quality = None

        for kw_index, keyword in enumerate(scene["visual_keywords"]):
            found = _find_usable_clip(keyword, min_duration, avoid_clip_ids)
            if found:
                chosen, matched_keyword = found, keyword
                match_quality = _QUALITY_BY_KEYWORD_INDEX[kw_index]
                break

        if not chosen:
            fallback_keywords = list(channel.FALLBACK_KEYWORDS)
            random.shuffle(fallback_keywords)
            for keyword in fallback_keywords:
                found = _find_usable_clip(keyword, min_duration, avoid_clip_ids)
                if found:
                    chosen, matched_keyword, match_quality = found, keyword, "fallback"
                    break

        if not chosen:
            raise FootageError(
                f"Escena {i}: no se encontro ningun clip usable en ningun proveedor "
                f"({', '.join(PROVIDERS)}), ni siquiera en FALLBACK_KEYWORDS de "
                f"{channel.CHANNEL_SLUG}. Revisar las API keys o conectividad."
            )

        avoid_clip_ids.add(chosen["id"])
        safe_id = chosen["id"].replace(":", "_")
        clip_path = output_dir / f"scene_{i:02d}_{safe_id}.mp4"
        _download_clip(chosen["download_url"], clip_path)

        print(
            f"[fetch_footage] escena {i}: keyword='{matched_keyword}' "
            f"quality={match_quality} provider={chosen['provider']} id={chosen['id']}"
        )

        results.append(
            {
                "clip_path": str(clip_path),
                "matched_keyword": matched_keyword,
                "match_quality": match_quality,
                "clip_id": chosen["id"],
                "provider": chosen["provider"],
            }
        )

    return results


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import config

    parser = argparse.ArgumentParser(description="Prueba standalone de fetch_footage.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--output-dir", default="test_footage")
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    test_scenes = [
        {
            "text": "This is a test scene.",
            "visual_keywords": ["nonexistent keyword xyz123", "city skyline", "abstract background"],
            "duration_estimate": 3.0,
        }
    ]
    result = fetch_footage_for_scenes(test_scenes, ch, args.output_dir)
    print(result)
