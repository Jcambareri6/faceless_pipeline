"""Paso 4: generar el guion estructurado (lista de escenas) con Claude."""

import json
import os

import anthropic

import competitor_research
import config
from prompts import build_script_prompt, build_script_retry_prompt, build_visual_keywords_update_prompt

REQUIRED_SCENE_KEYS = {"text", "visual_keywords", "duration_estimate"}
# Escenas cortas a proposito: mas cortes = ritmo mas rapido, y encaja mejor
# con subtitulos palabra por palabra (Paso 6) que con lineas largas.
MIN_SCENES = 12
MAX_SCENES = 20
MAX_TOKENS = 2000


class ScriptGenerationError(Exception):
    """Se levanta cuando Claude no devuelve un guion JSON valido tras reintentar."""


def _extract_json_array(raw: str) -> str:
    """Claude deberia responder solo el JSON, pero por las dudas toleramos que lo
    envuelva en backticks o texto alrededor: buscamos el primer '[' y el ultimo ']'."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start : end + 1]


def _validate_scenes(scenes) -> list:
    if not isinstance(scenes, list):
        raise ScriptGenerationError("La respuesta no es una lista JSON.")
    if not (MIN_SCENES <= len(scenes) <= MAX_SCENES):
        raise ScriptGenerationError(
            f"Cantidad de escenas fuera de rango: {len(scenes)} "
            f"(esperado {MIN_SCENES}-{MAX_SCENES})."
        )
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not REQUIRED_SCENE_KEYS.issubset(scene.keys()):
            raise ScriptGenerationError(f"Escena {i} le faltan campos requeridos: {scene}")
        if not isinstance(scene["text"], str) or not scene["text"].strip():
            raise ScriptGenerationError(f"Escena {i}: 'text' vacio o invalido.")
        if not isinstance(scene["visual_keywords"], list) or len(scene["visual_keywords"]) != 3:
            raise ScriptGenerationError(f"Escena {i}: 'visual_keywords' debe tener exactamente 3 items.")
        if not all(isinstance(k, str) and k.strip() for k in scene["visual_keywords"]):
            raise ScriptGenerationError(f"Escena {i}: 'visual_keywords' tiene items invalidos.")
        if not isinstance(scene["duration_estimate"], (int, float)):
            raise ScriptGenerationError(f"Escena {i}: 'duration_estimate' debe ser numerico.")
    return scenes


def _call_claude(client: anthropic.Anthropic, prompt: str) -> str:
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_script(channel, title: str, summary: str) -> list:
    """Genera el guion (lista de escenas) para un tema dado.

    Si hay competitor_insights recientes (<7 dias) con hook_patterns, se
    usan como guia real de gancho/ritmo ademas de las formulas de hook
    genericas (ver prompts.HOOK_FORMULAS). Si no hay, se usan solo esas.

    Si la primera respuesta no es JSON valido o no cumple el schema,
    reintenta una vez pidiendo explicitamente JSON valido. Si el segundo
    intento tambien falla, levanta ScriptGenerationError con un mensaje
    claro (nunca devuelve un guion a medio validar).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ScriptGenerationError("Falta la variable de entorno ANTHROPIC_API_KEY.")

    insights = competitor_research.load_recent_insights(channel.CHANNEL_SLUG)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_script_prompt(channel, title, summary, insights)
    raw = _call_claude(client, prompt)

    try:
        return _validate_scenes(json.loads(_extract_json_array(raw)))
    except (json.JSONDecodeError, ScriptGenerationError) as first_error:
        print(f"[generate_script] primer intento invalido ({first_error}); reintentando...")

    retry_prompt = build_script_retry_prompt(channel, title, summary, raw, insights)
    raw_retry = _call_claude(client, retry_prompt)

    try:
        return _validate_scenes(json.loads(_extract_json_array(raw_retry)))
    except (json.JSONDecodeError, ScriptGenerationError) as second_error:
        raise ScriptGenerationError(
            f"No se pudo generar un guion JSON valido tras 2 intentos. "
            f"Ultimo error: {second_error}. Respuesta cruda (primeros 500 chars): "
            f"{raw_retry[:500]!r}"
        ) from second_error


def _validate_visual_keywords_list(data, expected_len: int) -> list:
    if not isinstance(data, list) or len(data) != expected_len:
        raise ScriptGenerationError(
            f"Se esperaban {expected_len} arrays de keywords (uno por escena), recibido: {data}"
        )
    for i, kws in enumerate(data):
        if not isinstance(kws, list) or len(kws) != 3 or not all(isinstance(k, str) and k.strip() for k in kws):
            raise ScriptGenerationError(f"Escena {i}: keywords invalidos: {kws}")
    return data


def regenerate_visual_keywords(channel, scenes: list, notas_usuario: list) -> list:
    """Vuelve a pedirle a Claude solo los visual_keywords de cada escena,
    incorporando el feedback del usuario dejado sobre un preview anterior.
    El 'text' y 'duration_estimate' de las escenas no cambian.

    Usado por telegram_listener.py en 'regen_video' cuando el draft tiene
    notas_usuario. Si notas_usuario esta vacio, devuelve `scenes` sin tocar.

    Devuelve una copia nueva de la lista de escenas.
    """
    if not notas_usuario:
        return scenes

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ScriptGenerationError("Falta la variable de entorno ANTHROPIC_API_KEY.")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_visual_keywords_update_prompt(channel, scenes, notas_usuario)
    raw = _call_claude(client, prompt)

    try:
        updated_keywords = _validate_visual_keywords_list(json.loads(_extract_json_array(raw)), len(scenes))
    except (json.JSONDecodeError, ScriptGenerationError) as first_error:
        print(
            f"[generate_script] regenerate_visual_keywords: primer intento invalido "
            f"({first_error}); reintentando..."
        )
        retry_prompt = (
            f"{prompt}\n\nYour previous response could not be parsed as valid JSON. "
            f"Here is exactly what you returned:\n\n{raw}\n\nRespond again with ONLY "
            f"the JSON array of arrays described above, nothing else."
        )
        raw_retry = _call_claude(client, retry_prompt)
        try:
            updated_keywords = _validate_visual_keywords_list(
                json.loads(_extract_json_array(raw_retry)), len(scenes)
            )
        except (json.JSONDecodeError, ScriptGenerationError) as second_error:
            raise ScriptGenerationError(
                f"No se pudieron regenerar visual_keywords tras 2 intentos. "
                f"Ultimo error: {second_error}. Respuesta cruda (primeros 500 chars): "
                f"{raw_retry[:500]!r}"
            ) from second_error

    return [{**scene, "visual_keywords": kws} for scene, kws in zip(scenes, updated_keywords)]


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))

    parser = argparse.ArgumentParser(description="Prueba standalone de generate_script.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", default="")
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    scenes = generate_script(ch, args.title, args.summary)
    total = sum(s["duration_estimate"] for s in scenes)
    print(f"{len(scenes)} escenas generadas, duracion total estimada: {total:.1f}s\n")
    for i, s in enumerate(scenes):
        print(f"[{i}] ({s['duration_estimate']:.1f}s) {s['text']}")
        print(f"     keywords: {s['visual_keywords']}")
