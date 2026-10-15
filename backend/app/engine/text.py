"""Outils texte partagés : normalisation, dates, titres de sections."""
from __future__ import annotations

import re
import unicodedata

MONTHS = (
    "janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre|"
    "janv\\.?|fevr?\\.?|févr?\\.?|avr\\.?|juil\\.?|sept?\\.?|oct\\.?|nov\\.?|dec\\.?|déc\\.?|"
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan\\.?|feb\\.?|mar\\.?|apr\\.?|jun\\.?|jul\\.?|aug\\.?"
)
_YEAR = r"(?:19|20)\d{2}"
_POINT = rf"(?:(?:0?[1-9]|1[0-2])\s*/\s*{_YEAR}|(?:{MONTHS})\s+{_YEAR}|{_YEAR})"
_NOW = r"(?:aujourd['’]hui|ce\s+jour|pr[ée]sent|maintenant|now|present|en\s+cours|actuel(?:lement)?)"
_SEP = r"\s*(?:[-–—]|à|a|au|to|>|→)\s*"
_PLACEHOLDER = r"(?:MM\s*/\s*(?:AAAA|YYYY)|AAAA|YYYY|date\s+(?:de\s+)?d[ée]but|jj\s*/\s*mm\s*/\s*aaaa)"
_XRANGE = r"(?:de\s+)?X{2,4}\s*(?:à|a|-|–)\s*X{2,4}"

DATE_RANGE_RE = re.compile(
    rf"(?:(?:depuis|since)\s+{_POINT}|(?:de\s+)?{_POINT}{_SEP}(?:{_POINT}|{_NOW})|{_PLACEHOLDER}(?:{_SEP}(?:{_PLACEHOLDER}|{_NOW}))?"
    rf"|{_XRANGE})",
    re.IGNORECASE,
)
YEAR_RE = re.compile(_YEAR)
YEARS_EXP_RE = re.compile(r"(\d{1,2})\s*(?:\+\s*)?ans?\b", re.IGNORECASE)
DATE_GUIDANCE_RE = re.compile(r"\s*\((?:ou|si|or)\b[^)]*\)\s*$", re.IGNORECASE)  # « (ou … si toujours en cours) »
RATING_CHARS = "●○★☆■□"

SECTION_KEYWORDS: dict[str, list[str]] = {
    "resume": ["synthese", "resume", "profil", "presentation", "a propos", "summary", "profile",
               "points forts", "synthese du profil", "resume du profil"],
    "competences": ["competences", "competences techniques", "competences cles", "savoir faire", "skills",
                    "expertises", "expertise", "domaines de competence", "environnement technique",
                    "technologies", "competences fonctionnelles"],
    "missions": ["experiences", "experience", "experiences professionnelles", "experience professionnelle",
                 "missions", "parcours", "parcours professionnel", "references", "realisations",
                 "projets", "experience significative", "experiences significatives", "carriere", "career",
                 "experiences professionnelles significatives", "historique professionnel"],
    "formations": ["formation", "formations", "diplomes", "diplome", "etudes", "education", "cursus",
                   "academic training", "formation academique"],
    "certifications": ["certifications", "certification", "certificats", "habilitations"],
    "langues": ["langues", "langue", "languages", "langues etrangeres"],
}
SECTION_LABELS = {
    "resume": "Synthèse", "competences": "Compétences", "missions": "Expériences",
    "formations": "Formations", "certifications": "Certifications", "langues": "Langues",
    "formations_certifications": "Formations et certifications",
}

GENERIC_CLIENT_WORDS = re.compile(
    r"\b(grand compte|secteur|acteur|leader|banque|assureur|op[ée]rateur|industriel|constructeur|"
    r"[ée]diteur|client|soci[ée]t[ée]|groupe|organisme|administration|energ[ée]ticien|"
    r"navigation a[ée]rienne)\b", re.IGNORECASE)


def norm(s: str) -> str:
    """minuscules, sans accents, ponctuation réduite à des espaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9+#./' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def section_of_heading(text: str) -> str | None:
    """Renvoie le type de section si le texte ressemble à un titre connu."""
    t = norm(text).strip(" :.'")
    if not t or len(t) > 45:
        return None
    best, best_len = None, 0
    for sec, kws in SECTION_KEYWORDS.items():
        for kw in kws:
            if t == kw or t.startswith(kw + " ") or t.endswith(" " + kw):
                if len(kw) > best_len:
                    best, best_len = sec, len(kw)
    return best


def has_date_range(text: str) -> bool:
    return bool(DATE_RANGE_RE.search(text or ""))


def looks_like_initials(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.fullmatch(r"(?:[A-ZÀ-Ý][a-z]?\.\s*-?\s*){1,4}", t)) and len(t) <= 14


def looks_like_person_name(text: str) -> bool:
    t = (text or "").strip()
    if looks_like_initials(t):
        return True
    words = t.split()
    if not (1 < len(words) <= 4) or len(t) > 40:
        return False
    return all(w[:1].isupper() for w in words if w.isalpha() or "-" in w)


def initials(prenom: str, nom: str) -> str:
    parts = []
    for p in (prenom or "").replace("-", " ").split()[:1] + (nom or "").split()[:1]:
        parts.append(p[0].upper() + ".")
    return " ".join(parts) or "X."


def placeholder_like(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.search(r"\[[^\]]+\]|\{\{.*\}\}|_{3,}|X{3,}|lorem ipsum|<[^>]+>|\.{4,}", t, re.IGNORECASE))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9])", (text or "").strip())
    return [p for p in (x.strip() for x in parts) if p]


def format_period(debut: str | None, fin: str | None) -> str:
    def fmt(v: str | None) -> str:
        if not v:
            return "aujourd'hui"
        m = re.fullmatch(r"(\d{4})-(\d{2})", v)
        if m:
            return f"{m.group(2)}/{m.group(1)}"
        return v
    if not debut and not fin:
        return ""
    return f"{fmt(debut)} – {fmt(fin)}"
