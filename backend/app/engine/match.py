"""Correspondance offre ↔ profil : compétences demandées, présentes ou absentes, avec leur position dans le texte.

Sert à l'étape « L'offre » : le texte est surligné (présent dans le profil) ou souligné en pointillés (absent).
Rien n'est ajouté au profil ici : l'utilisateur confirme lui-même ce qu'il possède (« Je l'ai »).  [D3]
"""
from __future__ import annotations

import re
import unicodedata

from .adapter import mission_relevance
from .skills import _alias_index, detect_sectors, family, find_in_text

_ALLOWED = re.compile(r"[a-z0-9+#./' ]")


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Même normalisation que text.norm, caractère par caractère, avec la position d'origine de chaque caractère."""
    out: list[str] = []
    pos: list[int] = []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue
            c = c.lower().replace("’", "'")
            if not _ALLOWED.fullmatch(c):
                c = " "
            if c == " " and out and out[-1] == " ":
                continue
            out.append(c)
            pos.append(i)
    return "".join(out), pos


def skill_spans(text: str) -> list[dict]:
    """Compétences du référentiel citées dans le texte, avec leurs positions [start, end) dans le texte d'origine."""
    t, pos = _norm_with_map(text)
    t2, pos2 = " " + t + " ", [0, *pos, len(text)]
    taken: list[tuple[int, int]] = []
    spans = []
    for pat, label, _ in _alias_index():
        for m in pat.finditer(t2):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            start = pos2[m.start()]
            end = pos2[m.end() - 1] + 1
            spans.append({"start": start, "end": end, "label": label})
    return sorted(spans, key=lambda s: s["start"])


def profile_skills(profile: dict) -> dict[str, list[str]]:
    """Compétence → missions où elle apparaît (liste vide : déclarée dans les compétences seulement)."""
    have: dict[str, list[str]] = {}
    for c in profile.get("competences", []):
        have.setdefault(c["label"], [])
    resume = profile.get("resume") or {}
    for s in find_in_text(f'{profile.get("identite", {}).get("titre", "")} {resume.get("text", "") if isinstance(resume, dict) else resume}'):
        have.setdefault(s, [])
    for m in profile.get("missions", []):
        ctx = m.get("contexte") or {}
        words = " ".join([m.get("poste", ""), ctx.get("text", "") if isinstance(ctx, dict) else str(ctx),
                          *[r["text"] for r in m.get("realisations", [])]])
        found = set(m.get("environnement", [])) | set(find_in_text(words))
        for s in found:
            where = have.setdefault(s, [])
            if m["id"] not in where:
                where.append(m["id"])
    return have


def match(profile: dict, text: str) -> dict:
    spans = skill_spans(text)
    have = profile_skills(profile)
    have_fam: dict[str, str] = {}
    for label in have:
        for f in family(label):
            have_fam.setdefault(f, label)

    skills, seen = [], {}
    for s in spans:
        label = s["label"]
        mine = label if label in have else next((have_fam[f] for f in family(label) if f in have_fam), None)
        s["have"] = mine is not None
        if label not in seen:
            seen[label] = len(skills)
            skills.append({"label": label, "have": s["have"], "profile_label": mine,
                           "missions": have.get(mine, []) if mine else []})

    posting = {"skills": [s["label"] for s in skills], "sectors": detect_sectors(text), "text": text}
    missions = sorted(profile.get("missions", []), key=lambda m: mission_relevance(m, posting), reverse=True)
    first = missions[0] if missions and mission_relevance(missions[0], posting) > 0 else None
    n_have = sum(1 for s in skills if s["have"])
    return {
        "spans": spans,
        "skills": skills,
        "have": n_have,
        "total": len(skills),
        "sectors": posting["sectors"],
        "missions_order": [m["id"] for m in missions],
        "first_mission": ({"id": first["id"], "client": first.get("client", ""),
                           "skills": [s["label"] for s in skills if s["have"] and first["id"] in s["missions"]][:4]}
                          if first else None),
        "top_skills": [s["profile_label"] for s in skills if s["have"]][:5],
    }
