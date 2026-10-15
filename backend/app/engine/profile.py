"""
Profil canonique du consultant.

Chaque élément porte un identifiant stable (« fact id ») — c'est la base de la garantie
« zéro invention » [D3] : tout texte d'un dossier doit pointer vers au moins un fait.

Format :
{
  "identite": {"prenom", "nom", "titre", "annees_experience", "disponibilite", "mobilite", "ville"},
  "resume": {"id": "res", "text": "..."},
  "competences": [{"id": "c1", "label": "C++17", "categorie": "langages", "niveau": 4}],
  "missions": [{"id": "m1", "client", "secteur", "poste", "lieu", "debut": "2023-01", "fin": "2024-06"|null,
                "contexte": {"id": "m1.ctx", "text"}, "realisations": [{"id": "m1.r1", "text"}],
                "environnement": ["C++17", "Qt 6"]}],
  "formations": [{"id", "intitule", "etablissement", "annee"}],
  "certifications": [{"id", "intitule", "annee"}],
  "langues": [{"id", "langue", "niveau"}]
}
"""
from __future__ import annotations

import copy
import re
from datetime import date

from .skills import canonical, detect_sectors
from .text import format_period, initials

EMPTY_PROFILE = {
    "identite": {"prenom": "", "nom": "", "titre": "", "annees_experience": None,
                 "disponibilite": "", "mobilite": "", "ville": ""},
    "resume": {"id": "res", "text": ""},
    "competences": [], "missions": [], "formations": [], "certifications": [], "langues": [],
}


def ensure_ids(profile: dict) -> dict:
    """Complète les identifiants manquants, sans jamais changer ceux qui existent."""
    p = copy.deepcopy(profile)
    for k, v in EMPTY_PROFILE.items():
        p.setdefault(k, copy.deepcopy(v))
    if isinstance(p["resume"], str):
        p["resume"] = {"id": "res", "text": p["resume"]}
    p["resume"].setdefault("id", "res")

    def next_id(prefix: str, items: list[dict]) -> str:
        nums = [int(m.group(1)) for it in items if (m := re.fullmatch(rf"{prefix}(\d+)", str(it.get("id", ""))))]
        return f"{prefix}{max(nums, default=0) + 1}"

    for key, prefix in (("competences", "c"), ("missions", "m"), ("formations", "f"), ("certifications", "ce"), ("langues", "l")):
        for it in p[key]:
            if not it.get("id"):
                it["id"] = next_id(prefix, p[key])
    for c in p["competences"]:
        label, cat = canonical(c.get("label", ""))
        c["label"] = label
        if not c.get("categorie") or c["categorie"] == "autres":
            c["categorie"] = cat
    for m in p["missions"]:
        if isinstance(m.get("contexte"), str) or m.get("contexte") is None:
            m["contexte"] = {"text": m.get("contexte") or ""}
        m["contexte"].setdefault("id", f"{m['id']}.ctx")
        real = []
        for r in m.get("realisations", []):
            real.append({"text": r} if isinstance(r, str) else r)
        for r in real:
            if not r.get("id"):
                nums = [int(x["id"].split(".r")[1]) for x in real if x.get("id", "").startswith(m["id"] + ".r")]
                r["id"] = f"{m['id']}.r{max(nums, default=0) + 1}"
        m["realisations"] = real
        m["environnement"] = [canonical(e)[0] for e in m.get("environnement", []) if e]
        if not m.get("secteur"):
            sec = detect_sectors(" ".join([m.get("client", ""), m["contexte"]["text"], *[r["text"] for r in real]]))
            m["secteur"] = sec[0] if sec else ""
    return p


def facts(profile: dict) -> dict[str, str]:
    """Tous les faits citables : id → texte."""
    out = {"res": profile["resume"]["text"]}
    ident = profile["identite"]
    for k in ("titre", "disponibilite", "mobilite"):
        if ident.get(k):
            out[f"id.{k}"] = ident[k]
    if ident.get("annees_experience"):
        out["id.exp"] = f"{ident['annees_experience']} ans"
    for c in profile["competences"]:
        out[c["id"]] = c["label"]
    for m in profile["missions"]:
        out[m["id"]] = " ".join(filter(None, [m.get("client"), m.get("poste"), m.get("secteur")]))
        out[m["contexte"]["id"]] = m["contexte"]["text"]
        for r in m["realisations"]:
            out[r["id"]] = r["text"]
        out[f"{m['id']}.env"] = ", ".join(m["environnement"])
    for key in ("formations", "certifications", "langues"):
        for it in profile[key]:
            out[it["id"]] = " ".join(str(v) for k, v in it.items() if k != "id" and v)
    return out


def known_skill_labels(profile: dict) -> set[str]:
    labels = {c["label"] for c in profile["competences"]}
    for m in profile["missions"]:
        labels |= set(m["environnement"])
    return labels


def years_of_experience(profile: dict) -> int | None:
    if profile["identite"].get("annees_experience"):
        return int(profile["identite"]["annees_experience"])
    starts = [m.get("debut") for m in profile["missions"] if m.get("debut")]
    if not starts:
        return None
    first = min(int(s[:4]) for s in starts)
    return max(1, date.today().year - first)


def display_name(profile: dict, anonymize: bool) -> str:
    i = profile["identite"]
    if anonymize:
        return initials(i.get("prenom", ""), i.get("nom", ""))
    return f"{i.get('prenom', '')} {i.get('nom', '').upper()}".strip()


def generic_client(m: dict) -> str:
    """« Airbus » → « Grand compte aéronautique » (anonymisation des clients)."""
    sec = m.get("secteur") or ""
    if not sec:
        return "Grand compte"
    return {"Énergie": "Énergéticien", "Navigation aérienne": "Navigation aérienne",
            "Banque / Finance": "Grand compte bancaire", "Télécom": "Opérateur télécom",
            "Industrie": "Industriel", "Automobile": "Constructeur automobile",
            "Ferroviaire": "Acteur ferroviaire", "Médical": "Acteur de la santé"}.get(sec, f"Grand compte {sec.lower()}")


def mission_dates(m: dict) -> str:
    return format_period(m.get("debut"), m.get("fin"))
