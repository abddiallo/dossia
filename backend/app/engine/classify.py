"""Tri automatique des fichiers déposés : CV, modèle d'ESN ou fiche de poste.  [D1]"""
from __future__ import annotations

import re
from pathlib import Path

from .text import has_date_range, norm

POSTING_WORDS = re.compile(
    r"nous recherchons|profil recherche|competences requises|competences souhaitees|missions? principales?|"
    r"demarrage|duree de la mission|\btjm\b|taux journalier|teletravail|vous serez|le consultant devra|"
    r"fiche de poste|appel d'offres|cahier des charges|besoin client|lieu de la mission|date de debut", re.I)
TEMPLATE_WORDS = re.compile(r"dossier de competences|dossier technique|\bdc\b|modele|template|profil consultant", re.I)


NAME_TEMPLATE = re.compile(r"modele|template|\bdc\b|dossier|format|trame|gabarit")


def classify(path: str | Path, text: str, owner_names: list[str] | None = None,
             expected: str | None = None) -> tuple[str, float]:
    """→ (cv | template | job_posting | unknown, confiance).

    `expected` : ce que l'écran attend (ex. « template » sur la page Modèles) ; un .docx est alors pris tel quel.
    """
    name = norm(Path(path).stem)
    ext = Path(path).suffix.lower()
    if expected == "template" and ext == ".docx":
        return "template", 1.0
    if expected == "cv" and ext in (".docx", ".pdf", ".txt", ".md"):
        return "cv", 1.0
    t = norm(text)
    posting_hits = len(POSTING_WORDS.findall(t))
    dates = sum(1 for line in text.splitlines() if has_date_range(line))
    owner = any(n and norm(n) in t for n in (owner_names or []) if len(norm(n)) > 3)

    if re.search(r"\b(fiche|offre|ao|besoin|poste|mission)\b", name) and dates < 2:
        return "job_posting", 0.9
    if posting_hits >= 2 and dates < 3:
        return "job_posting", 0.85
    if ext == ".docx":
        # « Template_Atos_CV_FR », « Dossier de compétences VIVERIS » (même rempli à son nom) : c'est un modèle
        if NAME_TEMPLATE.search(name):
            return "template", 0.95
        if re.search(r"\b(cv|curriculum)\b", name) or owner:
            return "cv", 0.9
        if TEMPLATE_WORDS.search(t):
            return "template", 0.9
        if re.search(r"\[[^\]]+\]|mm\s*/\s*aaaa", t):
            return "template", 0.85
        # un .docx inconnu avec des périodes : le plus souvent le modèle (ou l'exemple) d'une ESN
        return ("template", 0.6) if dates else ("job_posting", 0.5)
    if ext in (".pdf", ".txt", ".md"):
        if owner or (dates >= 2 and posting_hits == 0):
            return "cv", 0.8
        return ("job_posting", 0.7) if posting_hits else ("cv", 0.5)
    return "unknown", 0.0
