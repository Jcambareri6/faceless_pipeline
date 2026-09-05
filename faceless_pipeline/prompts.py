"""Paso 4: construccion de prompts para generate_script.py."""

import config


# Formulas de gancho de shorts que probaron funcionar en general (no
# dependen de ningun canal puntual): siempre se incluyen como piso minimo,
# incluso cuando no hay datos de competencia disponibles todavia.
HOOK_FORMULAS = """Proven short-form hook patterns you can draw from (pick
whichever fits the topic best, do not use the same one every time):
- A direct question the viewer wants answered ("Why did X actually happen?").
- A curiosity gap that withholds the key fact ("The real reason X happened
  has nothing to do with what you think.").
- Leading with a striking number or timeframe ("It took just 6 months for
  X to collapse.").
- A direct address that makes it personal ("If you had $1000 in X, here's
  what would've happened.").
Keep the hook to ONE short sentence. Do not stack multiple hook styles in
the same opening line."""

# Regla compartida (no depende del canal): aplica igual a marcas/empresas
# que a figuras historicas sin fotos de archivo disponibles.
PROPER_NOUN_RULE = """If the script mentions a specific PROPER NOUN or
BRAND (a company, product, or person), visual_keywords[0] must NEVER try
to search for that literal name -- stock footage sites do not have
licensed footage of a specific brand or person, so searching the name
literally returns irrelevant results or nothing at all. Instead, use the
most recognizable GENERIC SYMBOLIC representation of what that name
evokes. Examples:
- "Blockbuster" -> "old VHS tapes video rental shelf"
- "Netflix" -> "streaming service app on TV screen"
- "Enron" -> "corporate office skyscraper empty"
This applies to any company, brand, or historical figure without
available stock footage: translate it to its most recognizable symbolic
visual, never search for the literal name."""


def _build_hook_patterns_block(insights) -> str:
    """Si hay datos reales de competencia sobre como abren sus videos
    (insights['hook_patterns'], ver competitor_research.py), se agregan como
    guia adicional -- son patrones agregados (promedios, porcentajes), nunca
    el texto textual de ningun video ajeno."""
    if not insights:
        return ""
    hp = insights.get("hook_patterns")
    if not hp or not hp.get("sample_size"):
        return ""

    return f"""

REAL COMPETITOR HOOK PATTERNS (aggregated from {hp['sample_size']} top-performing
videos in this niche, source: {hp.get('source', 'competitor data')}):
- Average hook length: {hp.get('avg_hook_length_words', 'n/a')} words.
- {hp.get('pct_hooks_are_questions', 0)}% of their hooks are phrased as a question.
- {hp.get('pct_hooks_start_with_number', 0)}% start with a number or timeframe.
- {hp.get('pct_hooks_start_with_question_word', 0)}% start with why/how/what/did/etc.
Use these as guidance for hook STYLE and rhythm, not content. Never copy
any competitor's wording -- write a completely original hook for this
specific topic."""


def _build_metaphor_examples_block(channel) -> str:
    """Libreria de metaforas visuales del canal (channels/*.py), para escenas
    abstractas/analiticas donde no hay nada fisico que filmar directamente."""
    metaphors = getattr(channel, "VISUAL_METAPHORS", None)
    if not metaphors:
        return ""
    lines = [
        f"- {concept} -> " + ", ".join(f'"{example}"' for example in examples)
        for concept, examples in metaphors.items()
    ]
    return "\n\nVISUAL METAPHOR LIBRARY for this niche (use as inspiration, adapt to the specific scene, do not reuse verbatim every time):\n" + "\n".join(lines)


def _build_ambiguous_words_block(channel) -> str:
    """Palabras con doble sentido comunes en este nicho (channels/*.py):
    nunca deben usarse solas en visual_keywords[0], siempre con contexto
    que las desambigue hacia el sentido del nicho, no el literal/fisico."""
    ambiguous = getattr(channel, "AMBIGUOUS_WORDS", None)
    if not ambiguous:
        return ""
    lines = [f'- "{word}" -> "{disambiguation}"' for word, disambiguation in ambiguous.items()]
    return (
        "\n\nCOMMON AMBIGUOUS WORDS in this niche (never use the bare word "
        "alone in visual_keywords[0] -- a stock footage search engine will "
        "just as likely match the unrelated literal meaning; always add "
        "2-3 words of context like these examples):\n" + "\n".join(lines)
    )


def build_script_prompt(channel, title: str, summary: str, insights=None) -> str:
    hook_patterns_block = _build_hook_patterns_block(insights)
    metaphor_block = _build_metaphor_examples_block(channel)
    ambiguous_words_block = _build_ambiguous_words_block(channel)

    return f"""You are a scriptwriter for a YouTube Shorts channel.

CHANNEL NICHE: {channel.NICHE_DESCRIPTION}
TARGET AUDIENCE: {channel.TARGET_AUDIENCE}

TOPIC TITLE: {title}
TOPIC SUMMARY: {summary}

Write a short-form video script as a JSON array of 12 to 20 scenes. Keep
scenes SHORT and punchy on purpose: more, quicker cuts read better than
a few long ones, and the captions are shown one word at a time, which
favors short bursts of text over long sentences. Follow these rules exactly:

- Each scene is an object with exactly these fields:
  - "text": string, 3 to 8 words, meant to be spoken aloud in 1 to 3
    seconds. Natural spoken English, no stage directions, no on-screen
    text markup. Break longer thoughts into two or more consecutive short
    scenes instead of one long one.
  - "visual_keywords": array of exactly 3 strings, in this order:
    1. A very specific, concrete, filmable object/place/scene
       (e.g. "trader slamming hand on desk"). IMPORTANT: if "text" for
       this scene is abstract or analytical -- an opinion, a trend, a
       feeling, an analysis, not something directly physical -- then
       visual_keywords[0] must be a CONCRETE VISUAL METAPHOR that
       represents the idea, not a literal attempt to film the abstract
       concept. Example: a line about market fragility maps to something
       like "house of cards falling", not to something literal like
       "fragile market graphic".{metaphor_block}
       ALSO IMPORTANT: if the word that best describes this scene has a
       common double meaning in English, NEVER use that word alone in
       visual_keywords[0] -- always add 2-3 words of context that
       disambiguate it toward this channel's niche, never toward an
       unrelated literal/physical meaning a stock footage site would
       just as easily match on. For example "streaming" alone could
       match flowing water instead of video streaming.{ambiguous_words_block}
       This disambiguation rule applies specifically to visual_keywords[0].
       visual_keywords[1] and [2] can stay simpler, since they are the
       fallback if the first one finds nothing.
       ALSO IMPORTANT: {PROPER_NOUN_RULE}
    2. A broader shot within the same concept
       (e.g. "stock exchange trading floor").
    3. A generic but thematically related shot
       (e.g. "city skyline financial district").
  - "duration_estimate": number (seconds), your best estimate of how long
    "text" takes to say out loud at a natural pace.
- The FIRST scene must be a hook: grab attention in the first 2-3 seconds
  and make the viewer want to keep watching. {HOOK_FORMULAS}{hook_patterns_block}
- The LAST scene must be a self-contained closing/payoff: resolve the
  hook, do not leave an open loop, do not ask the viewer to "wait for
  part 2", "follow for more", or similar.
- The sum of all "duration_estimate" values should be close to
  {config.SCRIPT_TARGET_SECONDS} seconds (within +/-10 seconds).
- Do not invent statistics, numbers, dates, or quotes that are not
  clearly supported by the topic summary provided. If you are not sure a
  specific fact is correct, phrase it more generally instead of making up
  a number.
- Stay strictly within the channel niche described above. If the niche
  says never to give investment advice, this applies to EVERY scene, not
  just the framing: never tell the viewer what THEY should do with their
  money, even phrased as a general historical tip. Do NOT write lines like
  "diversifying has helped reduce exposure" or "holding some cash gives
  you options" -- those are investment advice regardless of how they're
  worded. Explain what happened or why, not what the viewer should do
  about it. If the source topic itself reads like advice (e.g. "what
  investors should do"), reframe the whole script around the underlying
  explanation instead ("why this is happening"), not the advice angle.

Respond with ONLY a valid JSON array. No markdown code fences, no
explanation, no text before or after the JSON.
"""


def build_script_retry_prompt(channel, title: str, summary: str, bad_response: str, insights=None) -> str:
    original = build_script_prompt(channel, title, summary, insights)
    return f"""{original}

Your previous response could not be parsed as valid JSON. Here is exactly
what you returned:

{bad_response}

Respond again with ONLY a valid JSON array of scene objects as described
above. Do not include markdown code fences, comments, or any text outside
the JSON array itself.
"""


def build_visual_keywords_update_prompt(channel, scenes: list, notas_usuario: list) -> str:
    scenes_summary = "\n".join(
        f'{i}. text: "{s["text"]}" | current visual_keywords: {s["visual_keywords"]}'
        for i, s in enumerate(scenes)
    )
    notes_block = "\n".join(f"- {n}" for n in notas_usuario)

    return f"""You previously wrote visual_keywords for each scene of a YouTube
Shorts script in the "{channel.NICHE_DESCRIPTION}" niche.

CURRENT SCENES:
{scenes_summary}

The user watched a preview of this video and left this feedback about the
FOOTAGE/VISUALS specifically (the narration text itself is not changing):
{notes_block}

Update ONLY the "visual_keywords" for each scene to better address this
feedback. Keep the same structure as before: exactly 3 keywords per scene,
ordered from most specific/concrete to most generic (specific -> broader
shot of the same concept -> generic but thematically related).

Respond with ONLY a valid JSON array of {len(scenes)} arrays, one per
scene in the same order as above, each containing exactly 3 keyword
strings. Example shape for 2 scenes:
[["keyword1a", "keyword1b", "keyword1c"], ["keyword2a", "keyword2b", "keyword2c"]]

No markdown code fences, no explanation, no text before or after the JSON.
"""


def build_metadata_prompt(channel, scenes: list, title_hint: str, insights: dict = None) -> str:
    narration = " ".join(s["text"].strip() for s in scenes)

    if insights:
        insights_block = f"""
COMPETITOR RESEARCH (from real recent top-performing videos in this niche):
- Frequently used words in high-performing titles: {", ".join(insights.get("top_title_words", [])) or "n/a"}
- Frequently used hashtags: {", ".join(insights.get("top_hashtags", [])) or "n/a"}
- Average title length of top performers: {insights.get("avg_title_length_words")} words ({insights.get("avg_title_length_chars")} characters)

Use these patterns as inspiration for style, tone and structure. Do NOT
copy any competitor title verbatim.
"""
    else:
        insights_block = "\nNo competitor research data is available yet for this channel.\n"

    return f"""You are writing the YouTube metadata for a Shorts video.

CHANNEL NICHE: {channel.NICHE_DESCRIPTION}
TARGET AUDIENCE: {channel.TARGET_AUDIENCE}
TOPIC: {title_hint}

VIDEO SCRIPT (full narration, in order):
{narration}
{insights_block}
Write:
1. "title": an optimized YouTube title. If competitor research patterns
   are provided above, draw inspiration from them, but never copy a
   competitor's title word for word.
2. "description": 2 to 3 lines that summarize the video and make people
   want to watch.
3. "hashtags": an array of 5 to 8 hashtags, as plain words WITHOUT the
   "#" symbol (e.g. "personalfinance", not "#personalfinance"). If
   competitor research is provided, mix in the most frequent ones with
   2-3 hashtags specific to this exact topic. If no competitor research
   is provided, just use hashtags relevant to the topic and niche.
4. "tiktok_caption": a short TikTok-style caption for the SAME video,
   1-2 short sentences (under 150 characters), punchier and more casual
   than the YouTube title/description. Do NOT include hashtags in this
   field, they will be appended separately.

Respond with ONLY a valid JSON object with exactly these four keys:
"title", "description", "hashtags", "tiktok_caption". No markdown code
fences, no explanation, no text before or after the JSON.
"""


def build_metadata_retry_prompt(channel, scenes: list, title_hint: str, insights, bad_response: str) -> str:
    original = build_metadata_prompt(channel, scenes, title_hint, insights)
    return f"""{original}

Your previous response could not be parsed as valid JSON. Here is exactly
what you returned:

{bad_response}

Respond again with ONLY a valid JSON object with exactly the keys "title",
"description", "hashtags" and "tiktok_caption" as described above. Do not
include markdown code fences, comments, or any text outside the JSON
object itself.
"""
