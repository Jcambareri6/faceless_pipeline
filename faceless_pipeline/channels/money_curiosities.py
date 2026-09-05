"""Canal A: finanzas y economia contadas como curiosidad historica."""

CHANNEL_SLUG = "money_curiosities"
CHANNEL_EMOJI = "💰"

# En ingles a proposito: se usa tal cual en los prompts de Claude (Pasos 4 y 10)
# y como fuente de keywords para rank_topics.py, que compara contra articulos en ingles.
NICHE_DESCRIPTION = (
    "Finance and economics explained through historical events and curious what-if "
    "scenarios. Format: 'why this happened' / 'what would happen if...'. "
    "NEVER investment advice or personalized financial recommendations."
)

TARGET_AUDIENCE = "English-speaking audience in the US, Canada and UK, ages 22-45"

# Query corta para competitor_research.py (Paso 9): YouTube Search funciona mal
# con oraciones largas tipo NICHE_DESCRIPTION, necesita keywords concisas.
COMPETITOR_SEARCH_QUERY = "finance history explained"

# Verificados manualmente (HTTP 200 + XML valido) el 2026-09-03.
RSS_FEEDS = [
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",  # CNBC - Finance
    "https://www.marketwatch.com/rss/topstories",  # MarketWatch - Top Stories
    "https://www.investing.com/rss/news.rss",  # Investing.com - All News
]

# Voz edge-tts: masculina, tono analitico/serio (US), distinta a la de history_geopolitics.
TTS_VOICE = "en-US-GuyNeural"

# Placeholder Amazon Associates. Ver README "Cuando sumar Amazon Associates".
AFFILIATE_TAG = None

FALLBACK_KEYWORDS = [
    "stock market graph animation",
    "city financial district aerial",
    "coins closeup",
    "wall street street sign",
    "bank vault door",
    "calculator and paperwork desk",
    "hundred dollar bills fanned out",
    "office skyscraper glass windows",
    "handshake business deal closeup",
    "newspaper financial section closeup",
]

# Usado por prompts.py (Paso 4): cuando una escena es abstracta/analitica
# (no describe algo fisico), visual_keywords[0] debe ser una metafora visual
# concreta de esta lista/estilo, no un intento literal de filmar el concepto.
VISUAL_METAPHORS = {
    "fragility or market risk": ["house of cards falling", "tightrope walker balancing", "cracking ice surface"],
    "euphoria or speculative excess": ["crowd cheering stadium", "champagne celebration excess"],
    "understanding, perspective or clarity": [
        "person looking through telescope",
        "fog clearing over mountains",
        "puzzle pieces coming together",
    ],
    "correction or sudden fall": ["dominoes falling", "house of cards collapsing"],
    "hidden risk beneath the surface": ["iceberg tip above water", "shark fin cutting through calm water"],
    "growth or expansion": ["time-lapse plant growing", "balloon inflating"],
    "excessive debt or leverage": [
        "person carrying overloaded backpack uphill",
        "stack of boxes about to topple",
    ],
    "panic or chaos": ["stampede of people running", "flock of birds scattering suddenly"],
    "slow decline or erosion": ["sandcastle washed away by waves", "eroding cliffside"],
    "interconnected systems or contagion": ["spider web vibrating from one point", "row of dominoes across a map"],
}

# Usado por prompts.py (Paso 4): palabras con doble sentido comunes en este
# nicho -- nunca usarlas solas en visual_keywords[0], siempre con el
# contexto que las desambigua hacia el sentido de negocios/finanzas.
AMBIGUOUS_WORDS = {
    "streaming": "video streaming service subscription",
    "chain": "retail store chain closing",
    "crash": "stock market crash graph",
    "bubble": "economic bubble bursting",
    "correction": "stock market price correction",
    "leverage": "financial leverage debt",
    "spread": "market spread trading screen",
    "run": "bank run withdrawal queue",
    "default": "loan default notice document",
    "merger": "corporate merger handshake deal",
}
