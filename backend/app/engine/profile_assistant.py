"""« Dites-le simplement » sur le profil : une phrase en français → modification du profil.

Ne fait que ce que l'utilisateur affirme lui-même sur son propre profil (disponibilité, mobilité, ville, titre,
années d'expérience, compétence ajoutée ou retirée, langue). Toute autre demande reçoit une réponse qui
explique quoi écrire.  [D1]
"""
from __future__ import annotations

import copy
import re

from .profile import ensure_ids
from .skills import canonical
from .text import norm

LANG_LEVELS = r"(a1|a2|b1|b2|c1|c2|courant|bilingue|natif|maternelle|professionnel|intermediaire|scolaire|notions)"


def _clean(s: str) -> str:
    return s.strip().strip(" .,;:!\"«»'").strip()


def interpret(message: str, profile: dict) -> dict:
    """→ {"profile": profil modifié, "changes": [phrases], "reply": texte}"""
    p = copy.deepcopy(profile)
    ident = p["identite"]
    changes: list[str] = []
    parts = [x for x in re.split(r"\s*(?:;|\bet\b|\bpuis\b|\n)\s*(?=(?:je|j'|ajout|enl[eè]v|retir|supprim|mets|mon|ma|mes|dispo|mobil|habite|niveau|anglais|allemand|espagnol))",
                                 message.strip(), flags=re.I) if x.strip()]
    for part in parts:
        t = norm(part)
        raw = part.strip()
        if m := re.search(r"dispon\w*\s+(?:a partir d[ue']?\s*|des le |des |le |en |immediatement|tout de suite)?(.*)", t):
            rest = m.group(1).strip()
            # on reprend le texte d'origine (accents, majuscules) après « disponible »
            mo = re.search(r"(?i)dispon\w*\s+(.*)", raw)
            val = _clean(mo.group(1)) if mo else rest
            if not val or re.fullmatch(r"(?i)(immédiatement|tout de suite|maintenant)", val):
                val = "Immédiate"
            else:
                val = re.sub(r"(?i)^(à partir d[ue']?\s*|dès (le )?)", "", val)
                val = "À partir du " + val if re.match(r"\d|1er", val) else val[:1].upper() + val[1:]
            ident["disponibilite"] = val
            changes.append(f"Disponibilité : {val}")
            continue
        if re.search(r"mobil", t):
            mo = re.search(r"(?i)mobil\w*\s*(?:sur|en|:|dans)?\s*(.*)", raw)
            val = _clean(mo.group(1)) if mo else ""
            if val:
                ident["mobilite"] = val[:1].upper() + val[1:]
                changes.append(f"Mobilité : {ident['mobilite']}")
                continue
        if m := re.search(r"(?i)(?:j'habite|je vis|je suis bas[ée]e? |ville)\s*(?:à|a|:|sur)?\s*(.+)", raw):
            ident["ville"] = _clean(m.group(1))
            changes.append(f"Ville : {ident['ville']}")
            continue
        if m := re.search(r"(?i)(?:mon titre|mon poste|mon intitul[ée]|je suis)\s*(?:est|:|un|une)?\s*(?:un |une )?(.+)", raw):
            if not re.search(r"dispon|mobil|bas[ée]", m.group(1), re.I):
                ident["titre"] = _clean(m.group(1))
                changes.append(f"Titre : {ident['titre']}")
                continue
        if m := re.search(r"(\d{1,2})\s*ans? d.?experience", t):
            ident["annees_experience"] = int(m.group(1))
            changes.append(f"Années d'expérience : {m.group(1)}")
            continue
        if m := re.search(rf"(anglais|allemand|espagnol|italien|francais|arabe|chinois|portugais|neerlandais)\W+(?:niveau\s*)?{LANG_LEVELS}", t):
            lang, lvl = m.group(1), m.group(2)
            lang_label = {"francais": "Français", "neerlandais": "Néerlandais"}.get(lang, lang.capitalize())
            lvl_label = lvl.upper() if re.fullmatch(r"[abc][12]", lvl) else {"intermediaire": "Intermédiaire"}.get(lvl, lvl.capitalize())
            for l in p["langues"]:
                if norm(l.get("langue", "")) == lang:
                    l["niveau"] = lvl_label
                    break
            else:
                p["langues"].append({"langue": lang_label, "niveau": lvl_label})
            changes.append(f"{lang_label} : {lvl_label}")
            continue
        if m := re.search(r"(?i)(?:enl[eè]ve|retire|supprime)\s+(?:la compétence\s+|le |la |les |l')?(.+)", raw):
            target = norm(_clean(m.group(1)))
            before = len(p["competences"])
            p["competences"] = [c for c in p["competences"] if norm(c["label"]) != target and norm(canonical(m.group(1))[0]) != norm(c["label"])]
            if len(p["competences"]) < before:
                changes.append(f"Compétence retirée : {_clean(m.group(1))}")
                continue
        if m := re.search(r"(?i)(?:ajoute|j'ai|je ma[iî]trise|je connais|je fais du|je fais de la)\s+(?:la compétence\s+|aussi\s+|du |de la |des |le |la |l')?(.+)", raw):
            for item in re.split(r"\s*,\s*|\s+et\s+", _clean(m.group(1))):
                label, cat = canonical(item)
                if label and not any(norm(c["label"]) == norm(label) for c in p["competences"]):
                    p["competences"].append({"label": label, "categorie": cat, "niveau": None})
                    changes.append(f"Compétence ajoutée : {label}")
            continue
    if not changes:
        return {"profile": profile, "changes": [],
                "reply": "Je n'ai pas compris la modification. Essayez par exemple : « disponible à partir du 1er décembre », "
                         "« mobile sur toute la France », « ajoute Docker », « anglais C1 »."}
    return {"profile": ensure_ids(p), "changes": changes, "reply": "C'est fait : " + " · ".join(changes) + "."}
