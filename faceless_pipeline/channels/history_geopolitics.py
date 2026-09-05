"""Canal B: historia y geopolitica, mismo formato 'por que paso esto' / 'que pasaria si...'."""

CHANNEL_SLUG = "history_geopolitics"
CHANNEL_EMOJI = "🏛️"

# En ingles a proposito: se usa tal cual en los prompts de Claude (Pasos 4 y 10)
# y como fuente de keywords para rank_topics.py, que compara contra articulos en ingles.
NICHE_DESCRIPTION = (
    "History and geopolitics explained with the 'why this happened' / "
    "'what would happen if...' format. Historical events and current geopolitical "
    "tensions, connecting the historical origin to the present situation."
)

TARGET_AUDIENCE = "English-speaking audience in the US, Canada and UK, ages 22-45"

# Query corta para competitor_research.py (Paso 9): YouTube Search funciona mal
# con oraciones largas tipo NICHE_DESCRIPTION, necesita keywords concisas.
COMPETITOR_SEARCH_QUERY = "history geopolitics explained"

# Verificados manualmente (HTTP 200 + XML valido) el 2026-09-03.
RSS_FEEDS = [
    "https://foreignpolicy.com/feed/",  # Foreign Policy
    "https://www.smithsonianmag.com/rss/history/",  # Smithsonian Magazine - History
    "https://www.warhistoryonline.com/feed",  # War History Online
]

# Voz edge-tts: masculina, tono narrativo/documental (UK), distinta a la de money_curiosities.
TTS_VOICE = "en-GB-RyanNeural"

# Placeholder Amazon Associates. Ver README "Cuando sumar Amazon Associates".
AFFILIATE_TAG = None

FALLBACK_KEYWORDS = [
    "old map parchment texture",
    "historical archive black and white",
    "world globe rotating",
    "ancient ruins aerial",
    "vintage newspaper close up",
    "national flag waving slow motion",
    "government building columns exterior",
    "old photographs archive drawer",
    "candle burning in dark room",
    "cobblestone street european old town",
]

# Usado por prompts.py (Paso 4): cuando una escena es abstracta/analitica
# (no describe algo fisico), visual_keywords[0] debe ser una metafora visual
# concreta de esta lista/estilo, no un intento literal de filmar el concepto.
VISUAL_METAPHORS = {
    "rising tension or imminent conflict": ["pressure cooker steam building", "storm clouds gathering over horizon"],
    "fragile alliance or peace": ["tightrope walker between two cliffs", "thin ice cracking underfoot"],
    "empire or power collapsing": ["ancient statue crumbling", "sandcastle collapsing at the tide"],
    "slow historical decline": ["sand falling through an hourglass", "candle burning down to nothing"],
    "hidden influence or behind-the-scenes power": [
        "puppet strings from above",
        "chess pieces moved by an unseen hand",
    ],
    "turning point or pivotal moment": ["compass needle spinning then settling", "fork in the road with two paths"],
    "spreading conflict or domino effect": ["dominoes falling across a map", "wildfire spreading across dry field"],
    "isolation or being cut off": ["single lit window in a dark building", "island surrounded by rising water"],
    "power struggle or rivalry": ["two chess kings facing off", "tug of war rope straining"],
    "historical memory or legacy": ["old photograph fading at the edges", "weathered monument overgrown with vines"],
}

# Usado por prompts.py (Paso 4): palabras con doble sentido comunes en este
# nicho -- nunca usarlas solas en visual_keywords[0], siempre con el
# contexto que las desambigua hacia el sentido de historia/geopolitica.
AMBIGUOUS_WORDS = {
    "revolution": "political revolution protest crowd",
    "crown": "royal crown monarchy",
    "treaty": "peace treaty signing document",
    "party": "political party rally crowd",
    "state": "nation state flag government building",
    "campaign": "military campaign battlefield map",
    "cabinet": "government cabinet meeting room",
    "occupation": "military occupation soldiers checkpoint",
    "front": "military front line trenches",
    "resolution": "United Nations resolution vote assembly",
}
