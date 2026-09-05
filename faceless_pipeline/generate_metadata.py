"""Paso 10: generar titulo, descripcion y hashtags optimizados con Claude,
usando investigacion de competencia real cuando esta disponible."""

import json
import os

import anthropic

import competitor_research
import config
from prompts import build_metadata_prompt, build_metadata_retry_prompt

REQUIRED_KEYS = {"title", "description", "hashtags", "tiktok_caption"}
MIN_HASHTAGS = 5
MAX_HASHTAGS = 8
MAX_TOKENS = 1000


class MetadataGenerationError(Exception):
    pass


def _extract_json_object(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start : end + 1]


def _validate_metadata(data) -> dict:
    if not isinstance(data, dict) or not REQUIRED_KEYS.issubset(data.keys()):
        raise MetadataGenerationError(f"Faltan campos requeridos: {data}")
    if not isinstance(data["title"], str) or not data["title"].strip():
        raise MetadataGenerationError("'title' vacio o invalido.")
    if not isinstance(data["description"], str) or not data["description"].strip():
        raise MetadataGenerationError("'description' vacio o invalido.")
    hashtags = data["hashtags"]
    if not isinstance(hashtags, list) or not (MIN_HASHTAGS <= len(hashtags) <= MAX_HASHTAGS):
        raise MetadataGenerationError(
            f"'hashtags' debe ser una lista de {MIN_HASHTAGS}-{MAX_HASHTAGS} items, recibido: {hashtags}"
        )
    if not all(isinstance(h, str) and h.strip() for h in hashtags):
        raise MetadataGenerationError("'hashtags' tiene items invalidos.")
    if not isinstance(data["tiktok_caption"], str) or not data["tiktok_caption"].strip():
        raise MetadataGenerationError("'tiktok_caption' vacio o invalido.")
    return data


def _call_claude(client: anthropic.Anthropic, prompt: str) -> str:
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_metadata(channel, scenes: list, title_hint: str) -> dict:
    """Genera {"title", "description", "hashtags"} para el video final.

    Usa competitor_insights_{slug}.json si existe y tiene menos de 7 dias
    (via competitor_research.load_recent_insights). Si no existe o esta
    vencido, genera igual sin ese contexto y loggea un aviso.

    Si channel.AFFILIATE_TAG no es None, agrega el link de Amazon
    Associates al final de la descripcion.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise MetadataGenerationError("Falta la variable de entorno ANTHROPIC_API_KEY.")

    insights = competitor_research.load_recent_insights(channel.CHANNEL_SLUG)
    if insights is None:
        print(
            f"[generate_metadata] aviso: no hay competitor_insights recientes (<7 dias) "
            f"para {channel.CHANNEL_SLUG}. Generando metadata sin ese contexto; conviene "
            f"correr competitor_research.py pronto."
        )

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_metadata_prompt(channel, scenes, title_hint, insights)
    raw = _call_claude(client, prompt)

    try:
        metadata = _validate_metadata(json.loads(_extract_json_object(raw)))
    except (json.JSONDecodeError, MetadataGenerationError) as first_error:
        print(f"[generate_metadata] primer intento invalido ({first_error}); reintentando...")
        retry_prompt = build_metadata_retry_prompt(channel, scenes, title_hint, insights, raw)
        raw_retry = _call_claude(client, retry_prompt)
        try:
            metadata = _validate_metadata(json.loads(_extract_json_object(raw_retry)))
        except (json.JSONDecodeError, MetadataGenerationError) as second_error:
            raise MetadataGenerationError(
                f"No se pudo generar metadata JSON valida tras 2 intentos. "
                f"Ultimo error: {second_error}. Respuesta cruda (primeros 500 chars): "
                f"{raw_retry[:500]!r}"
            ) from second_error

    if channel.AFFILIATE_TAG is not None:
        affiliate_link = f"https://www.amazon.com/?tag={channel.AFFILIATE_TAG}"
        metadata["description"] = f"{metadata['description']}\n\n{affiliate_link}"

    # El caption de TikTok reusa los mismos hashtags que YouTube (no investigamos
    # competencia de TikTok por separado, ver conversacion sobre alcance): Claude
    # devuelve el texto sin hashtags y acá se los agregamos al final, formateados.
    hashtag_str = " ".join(f"#{h.lstrip('#')}" for h in metadata["hashtags"])
    metadata["tiktok_caption"] = f"{metadata['tiktok_caption'].strip()} {hashtag_str}".strip()

    return metadata


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))

    parser = argparse.ArgumentParser(description="Prueba standalone de generate_metadata.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    fake_scenes = [
        {"text": "Why did this actually happen?", "visual_keywords": [], "duration_estimate": 3},
        {"text": "It all started with one decision.", "visual_keywords": [], "duration_estimate": 3},
    ]
    metadata = generate_metadata(ch, fake_scenes, args.title)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
