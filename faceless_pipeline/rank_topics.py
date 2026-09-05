"""Paso 3: rankear temas candidatos por relevancia al nicho y por potencial de
angulo 'por que paso esto' / 'que pasaria si...', antes de gastar tokens de
Claude generando guiones solo para los mejores 3.

Es un filtro barato y heuristico, no un juicio de calidad final: ese lo hace
Claude en generate_script.py. Aca solo se trata de no desperdiciar llamadas
en temas irrelevantes o en simples recaps de noticias sin angulo narrativo.
"""

import re

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "of",
    "to", "in", "on", "at", "by", "for", "with", "about", "against",
    "between", "into", "through", "during", "before", "after", "above",
    "below", "from", "up", "down", "out", "off", "over", "under", "again",
    "further", "once", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing", "will",
    "would", "could", "should", "can", "this", "that", "these", "those",
    "it", "its", "as", "not", "no", "never", "personalized", "format",
    "explained", "current", "present", "situation", "audience", "english",
    "speaking", "ages",
}

# Senales de un buen angulo explicativo/especulativo (bonus).
ANGLE_KEYWORDS = [
    "why", "how", "behind", "explained", "explains", "explainer",
    "origin", "origins", "history of", "root cause", "led to", "causes",
    "caused", "sparked", "triggered", "what if", "could", "would",
    "risk", "threat", "warns", "warning", "collapse", "crisis", "unravel",
    "secret", "hidden", "untold", "myth", "truth about", "lesson",
    "lessons", "rise and fall", "downfall", "domino effect", "turning point",
]

# Senales de recap plano de noticia del dia, sin angulo (penalizacion).
RECAP_KEYWORDS = [
    "earnings", "closed at", "shares rose", "shares fell", "stock rose",
    "stock fell", "announced today", "press release", "quarterly report",
    "earnings call", "guidance for", "price target", "q1 20", "q2 20",
    "q3 20", "q4 20",
]

RELEVANCE_WEIGHT = 3.0
ANGLE_BONUS = 1.0
RECAP_PENALTY = 1.5


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _relevance_score(candidate_words: set, niche_words: set) -> float:
    if not candidate_words or not niche_words:
        return 0.0
    overlap = candidate_words & niche_words
    return len(overlap) / len(niche_words)


def _angle_score(raw_text_lower: str) -> float:
    score = 0.0
    for kw in ANGLE_KEYWORDS:
        if kw in raw_text_lower:
            score += ANGLE_BONUS
    for kw in RECAP_KEYWORDS:
        if kw in raw_text_lower:
            score -= RECAP_PENALTY
    return score


def rank_topics(candidates: list, channel) -> list:
    """Puntua y ordena candidatos de mayor a menor.

    Devuelve una copia de cada dict candidato con 'score', 'relevance_score'
    y 'angle_score' agregados, ordenada descendente por 'score'.
    """
    niche_words = _tokenize(channel.NICHE_DESCRIPTION)
    ranked = []

    for c in candidates:
        raw_text = f"{c.get('title', '')} {c.get('summary', '')}"
        candidate_words = _tokenize(raw_text)

        relevance = _relevance_score(candidate_words, niche_words)
        angle = _angle_score(raw_text.lower())
        total = relevance * RELEVANCE_WEIGHT + angle

        ranked.append(
            {
                **c,
                "score": round(total, 4),
                "relevance_score": round(relevance, 4),
                "angle_score": round(angle, 4),
            }
        )

    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    import config
    from fetch_topics import fetch_candidate_topics

    parser = argparse.ArgumentParser(description="Prueba standalone de rank_topics.py")
    parser.add_argument("--channel", required=True, choices=config.AVAILABLE_CHANNELS)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    ch = config.load_channel(args.channel)
    candidates = fetch_candidate_topics(ch)
    ranked = rank_topics(candidates, ch)

    print(f"Top {args.top} de {len(ranked)} candidatos para {ch.CHANNEL_SLUG}:\n")
    for t in ranked[: args.top]:
        print(
            f"score={t['score']:5.2f} (rel={t['relevance_score']:.2f} "
            f"angle={t['angle_score']:+.1f})  {t['title']}"
        )
