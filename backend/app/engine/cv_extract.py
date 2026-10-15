"""
Extraction d'un CV (PDF, Word, texte) vers le profil canonique.

1. Avec une clé d'API IA : extraction structurée (JSON contrôlé), puis normalisation.
2. Sans IA (ou en cas d'échec) : analyse heuristique des sections et des périodes.
Dans les deux cas, ce qui est déduit (et non lu tel quel) est marqué « à vérifier ».
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from . import docxutil as X
from . import llm
from .profile import EMPTY_PROFILE, ensure_ids
from .skills import canonical, find_in_text
from .text import (
    DATE_RANGE_RE, YEARS_EXP_RE, has_date_range, looks_like_person_name, norm, section_of_heading,
)

MONTHS_NUM = {"janv": 1, "jan": 1, "fev": 2, "feb": 2, "mars": 3, "mar": 3, "avr": 4, "apr": 4, "mai": 5, "may": 5,
              "juin": 6, "jun": 6, "juil": 7, "jul": 7, "aou": 8, "aug": 8, "sep": 9, "oct": 10, "nov": 11,
              "dec": 12, "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
              "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}


# ───────────────────────────── Texte brut ─────────────────────────────

def extract_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        doc = Document(str(path))
        lines = []
        for el in X.body_elements(doc):
            for p in X.element_paragraphs(el):
                t = X.para_text(p).strip()
                if t:
                    lines.append(("• " + t) if X.is_list_paragraph(p, doc) and not X.strip_leading_bullet_char(p) else t)
        return "\n".join(lines)
    if ext == ".pdf":
        from .render import pdf_text
        return pdf_text(path)
    return path.read_text(encoding="utf-8", errors="ignore")


# ───────────────────────────── Dates ─────────────────────────────

def _point(s: str) -> str | None:
    s = norm(s)
    if re.search(r"aujourd|present|ce jour|maintenant|now|en cours|actuel", s):
        return None
    m = re.search(r"(\d{1,2})\s*/\s*((?:19|20)\d{2})", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.search(r"([a-z]+)\.?\s+((?:19|20)\d{2})", s)
    if m:
        for k, v in MONTHS_NUM.items():
            if m.group(1).startswith(k):
                return f"{m.group(2)}-{v:02d}"
    m = re.search(r"(?:19|20)\d{2}", s)
    return m.group(0) if m else None


def parse_period(text: str) -> tuple[str | None, str | None, bool]:
    """→ (debut, fin, en_cours)."""
    m = DATE_RANGE_RE.search(text or "")
    if not m:
        return None, None, False
    raw = m.group(0)
    if re.match(r"(?i)\s*(depuis|since)", raw):
        return _point(raw), None, True
    parts = re.split(r"\s*(?:[-–—>→]|\bà\b|\bau\b|\bto\b)\s*", raw, maxsplit=1)
    debut = _point(parts[0])
    fin = _point(parts[1]) if len(parts) > 1 else None
    ongoing = len(parts) > 1 and fin is None
    return debut, fin, ongoing


# ───────────────────────────── Heuristique ─────────────────────────────

def heuristic_profile(text: str) -> tuple[dict, list[str]]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    prof = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in EMPTY_PROFILE.items()}
    prof["identite"] = dict(EMPTY_PROFILE["identite"])
    unverified: list[str] = []

    # sections
    sections: list[tuple[str, int]] = []
    for i, l in enumerate(lines):
        sec = section_of_heading(l)
        if sec and len(l) < 45:
            sections.append((sec, i))
    first = sections[0][1] if sections else len(lines)
    head = lines[:first]
    for i, l in enumerate(head):
        if looks_like_person_name(l) and not prof["identite"]["nom"]:
            words = l.split()
            upper = [w for w in words if w.isupper() and len(w) > 1]
            nom = " ".join(upper) if upper else words[-1]
            prenom = " ".join(w for w in words if w not in nom.split())
            prof["identite"].update(prenom=prenom.title(), nom=nom.title() if nom.isupper() else nom)
            if i + 1 < len(head) and "@" not in head[i + 1]:
                prof["identite"]["titre"] = head[i + 1]
        if "@" in l or re.search(r"\+?\d[\d .]{8,}", l):
            city = re.split(r"[·|,]", l)[0].strip()
            if city and "@" not in city and not re.search(r"\d", city):
                prof["identite"]["ville"] = city
        if "disponib" in norm(l):
            prof["identite"]["disponibilite"] = l.split(":", 1)[-1].strip()
        if "mobilit" in norm(l):
            prof["identite"]["mobilite"] = l.split(":", 1)[-1].strip()

    def block(sec: str) -> list[str]:
        out = []
        for k, (s, i) in enumerate(sections):
            if s == sec:
                end = sections[k + 1][1] if k + 1 < len(sections) else len(lines)
                out += lines[i + 1:end]
        return out

    res = " ".join(block("resume"))
    prof["resume"] = {"id": "res", "text": res}
    m = YEARS_EXP_RE.search(res)
    if m:
        prof["identite"]["annees_experience"] = int(m.group(1))

    comps, seen = [], set()
    for l in block("competences"):
        l = l.lstrip("•-–▪ ").strip()
        cat = None
        if ":" in l:
            cat_raw, l = l.split(":", 1)
            cat = norm(cat_raw)
        for item in re.split(r"[,;/]|\s{3,}|\t", l):
            item = item.strip(" .")
            if not item or len(item) > 40:
                continue
            label, c = canonical(item)
            if label.lower() in seen:
                continue
            seen.add(label.lower())
            comps.append({"label": label, "categorie": c if c != "autres" else _cat_from_heading(cat), "niveau": None})
    prof["competences"] = comps

    prof["missions"] = _parse_missions(block("missions"), unverified)
    for l in block("formations"):
        l = l.lstrip("•-– ").strip()
        y = re.search(r"((?:19|20)\d{2})", l)
        core = re.sub(r"\(?\s*(?:19|20)\d{2}\s*\)?", "", l).strip(" -–—,")
        parts = re.split(r"\s+[—–-]\s+", core, maxsplit=1)
        prof["formations"].append({"intitule": parts[0], "etablissement": parts[1] if len(parts) > 1 else "",
                                   "annee": y.group(1) if y else ""})
    for l in block("certifications"):
        y = re.search(r"((?:19|20)\d{2})", l)
        prof["certifications"].append({"intitule": re.sub(r"\(?\s*(?:19|20)\d{2}\s*\)?", "", l).strip(" -–—,•"),
                                       "annee": y.group(1) if y else ""})
    for l in block("langues"):
        l = l.lstrip("•-– ")
        if ":" in l:
            a, b = l.split(":", 1)
            prof["langues"].append({"langue": a.strip(), "niveau": b.strip()})
        else:
            prof["langues"].append({"langue": l.strip(), "niveau": ""})
    if not prof["identite"]["annees_experience"] and prof["missions"]:
        unverified.append("identite.annees_experience")
    return prof, unverified


def _cat_from_heading(cat: str | None) -> str:
    if not cat:
        return "autres"
    for k, v in (("langage", "langages"), ("framework", "frameworks"), ("outil", "outils"), ("norme", "normes"),
                 ("method", "methodes"), ("cloud", "cloud"), ("base", "bases"), ("system", "systemes")):
        if k in cat:
            return v
    return "autres"


def _parse_missions(lines: list[str], unverified: list[str]) -> list[dict]:
    missions: list[dict] = []
    cur = None
    for l in lines:
        if has_date_range(l):
            debut, fin, ongoing = parse_period(l)
            head = DATE_RANGE_RE.sub("", l).strip(" ·|-–—,")
            lieu = ""
            pm = re.search(r"\(([^)]+)\)", head)
            if pm:
                lieu = pm.group(1)
                head = head.replace(pm.group(0), "").strip()
            # « ESN — Client » : on garde le client final
            parts = [p.strip() for p in re.split(r"\s+[—–-]\s+|\s+pour\s+", head) if p.strip()]
            client = parts[-1] if parts else head
            cur = {"client": client, "lieu": lieu, "debut": debut, "fin": fin, "poste": "",
                   "contexte": "", "realisations": [], "environnement": []}
            if debut is None:
                unverified.append(f"missions[{len(missions)}].debut")
            missions.append(cur)
            continue
        if cur is None:
            continue
        clean = l.lstrip("•-–▪✓* ").strip()
        if re.match(r"(?i)^(environnement( technique)?|technologies|outils|stack)\s*:", clean):
            env = clean.split(":", 1)[1]
            cur["environnement"] = [canonical(e.strip())[0] for e in re.split(r"[,;/]", env) if e.strip()]
        elif not cur["poste"] and len(clean) < 90 and not l.startswith(("•", "-", "–")):
            cur["poste"] = clean
        elif l.startswith(("•", "-", "–", "▪", "✓", "*")) or cur["contexte"]:
            cur["realisations"].append(clean)
        else:
            cur["contexte"] = clean
    for m in missions:
        if not m["environnement"]:
            m["environnement"] = find_in_text(" ".join([m["contexte"], *m["realisations"]]))
    return missions


# ───────────────────────────── IA (optionnelle) ─────────────────────────────

LLM_SYSTEM = (
    "Tu extrais un CV en JSON. Tu recopies les informations telles qu'elles sont écrites, sans rien inventer, "
    "sans reformuler les réalisations. Dates au format AAAA-MM (ou AAAA si le mois est absent), fin=null si en cours. "
    "Si une information est absente, laisse une chaîne vide ou null."
)
LLM_SCHEMA_HINT = """{"identite":{"prenom":"","nom":"","titre":"","annees_experience":null,"disponibilite":"","mobilite":"","ville":""},
"resume":"","competences":[{"label":"","categorie":"langages|frameworks|outils|systemes|cloud|bases|normes|methodes|autres","niveau":null}],
"missions":[{"client":"","secteur":"","poste":"","lieu":"","debut":"","fin":null,"contexte":"","realisations":[""],"environnement":[""]}],
"formations":[{"intitule":"","etablissement":"","annee":""}],"certifications":[{"intitule":"","annee":""}],"langues":[{"langue":"","niveau":""}]}"""


def extract_profile(path: str | Path) -> tuple[dict, list[str], str]:
    """→ (profil normalisé avec ids, chemins à vérifier, méthode utilisée)."""
    text = extract_text(path)
    data = llm.complete_json(LLM_SYSTEM, f"CV :\n\n{text[:30000]}", LLM_SCHEMA_HINT) if llm.available() else None
    if data and isinstance(data, dict) and data.get("missions") is not None:
        prof = {**EMPTY_PROFILE, **data}
        unverified = [f"missions[{i}].secteur" for i, m in enumerate(prof["missions"]) if not m.get("secteur")]
        method = "ia"
    else:
        prof, unverified = heuristic_profile(text)
        method = "heuristique"
    return ensure_ids(prof), unverified, method


# ───────────────────────────── Mise à jour : seulement les différences ─────────────────────────────

def diff_profiles(old: dict, new: dict) -> dict:
    """Ce qu'apporte un nouveau CV par rapport au profil actuel (pour confirmation rapide)."""
    d = {"identite": {}, "competences": [], "missions": [], "formations": [], "certifications": [], "langues": [],
         "resume": None}
    for k, v in new["identite"].items():
        if v and v != old["identite"].get(k):
            d["identite"][k] = v
    if new["resume"]["text"] and new["resume"]["text"] != old["resume"]["text"]:
        d["resume"] = new["resume"]["text"]
    labels = {c["label"].lower() for c in old["competences"]}
    d["competences"] = [c for c in new["competences"] if c["label"].lower() not in labels]
    keys = {(norm(m.get("client", "")), (m.get("debut") or "")[:4]) for m in old["missions"]}
    d["missions"] = [m for m in new["missions"] if (norm(m.get("client", "")), (m.get("debut") or "")[:4]) not in keys]
    for key, f in (("formations", "intitule"), ("certifications", "intitule"), ("langues", "langue")):
        have = {norm(x.get(f, "")) for x in old[key]}
        d[key] = [x for x in new[key] if norm(x.get(f, "")) not in have]
    return d


def diff_is_empty(d: dict) -> bool:
    return not (d["identite"] or d["resume"] or any(d[k] for k in ("competences", "missions", "formations", "certifications", "langues")))


def apply_diff(old: dict, d: dict, accepted: list[str] | None = None) -> dict:
    """accepted : liste de chemins acceptés (ex. "missions:2", "identite.titre"). None = tout."""
    def ok(path: str) -> bool:
        return accepted is None or path in accepted
    p = {**old, "identite": dict(old["identite"])}
    for k, v in d["identite"].items():
        if ok(f"identite.{k}"):
            p["identite"][k] = v
    if d.get("resume") and ok("resume"):
        p["resume"] = {"id": old["resume"].get("id", "res"), "text": d["resume"]}
    for key in ("competences", "missions", "formations", "certifications", "langues"):
        add = []
        for i, x in enumerate(d[key]):
            if not ok(f"{key}:{i}"):
                continue
            x = {k: v for k, v in x.items() if k != "id"}
            if key == "missions":  # nouveaux identifiants pour les sous-éléments
                ctx = x.get("contexte")
                x["contexte"] = ctx.get("text", "") if isinstance(ctx, dict) else (ctx or "")
                x["realisations"] = [r["text"] if isinstance(r, dict) else r for r in x.get("realisations", [])]
            add.append(x)
        p[key] = list(old[key]) + add
    return ensure_ids(p)
