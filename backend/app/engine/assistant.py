"""
Assistant en langage courant : traduit une demande (« raccourcis la synthèse et enlève Python »)
en modifications des options du dossier. Il ne peut que masquer, réordonner, raccourcir,
reprendre l'original ou retoucher — jamais ajouter ce qui n'est pas dans le profil.  [D1] [D3]
"""
from __future__ import annotations

import copy
import re

from . import llm
from .skills import SECTORS
from .text import norm, split_sentences

SUGGESTIONS = ["Tenir en 2 pages", "Raccourcir la synthèse", "Ajouter ma disponibilité", "Mettre l'aéronautique en avant"]


def _find_fact(profile: dict, needle: str) -> tuple[str, str] | None:
    """Trouve une compétence, une mission, une réalisation… à partir d'un bout de texte."""
    n = norm(needle).strip(" .")
    if not n:
        return None
    for c in profile["competences"]:
        if norm(c["label"]) == n:
            return c["id"], f"la compétence « {c['label']} »"
    for m in profile["missions"]:
        if n and (n == norm(m.get("client", "")) or n in norm(m.get("client", "")) or
                  ("mission " + norm(m.get("client", ""))) == n):
            return m["id"], f"la mission {m.get('client')}"
    for c in profile["competences"]:
        if n in norm(c["label"]) and len(n) >= 3:
            return c["id"], f"la compétence « {c['label']} »"
    for m in profile["missions"]:
        for r in m["realisations"]:
            if len(n) >= 6 and n in norm(r["text"]):
                return r["id"], f"la réalisation « {r['text'][:50]} »"
    for key, f in (("formations", "intitule"), ("certifications", "intitule"), ("langues", "langue")):
        for it in profile[key]:
            if len(n) >= 3 and n in norm(it.get(f, "")):
                return it["id"], f"« {it.get(f)} »"
    return None


def _sector(text: str) -> str | None:
    t = norm(text)
    for s, kws in SECTORS.items():
        if norm(s) in t or any(k in t for k in kws):
            return s
    return None


def interpret(message: str, profile: dict, options: dict, view: dict | None = None) -> dict:
    """→ {"options": nouvelles options, "reply": texte, "changes": [...], "undo": bool, "propose_profile": {...}|None}"""
    o = copy.deepcopy(options)
    o.setdefault("hidden", []); o.setdefault("overrides", {}); o.setdefault("shorten", {}); o.setdefault("skills_first", [])
    changes, notes, propose = [], [], None
    raw = message.strip()
    # plusieurs demandes dans une phrase : « raccourcis la synthèse et enlève Python »
    parts = [p for p in re.split(r"\s*(?:,|;|\bet\b|\bpuis\b)\s*(?=(?:raccourc|enl[eè]v|retir|supprim|masqu|cach|mets?|place|ajout|tien|limit|annul|revien|affich|remets?|r[ée]affich|dispon|mobil|garde|passe))",
                                         raw, flags=re.I) if p.strip()]
    for part in parts:
        t = norm(part)
        if re.search(r"\b(annule|defai|reviens en arriere|undo)\b", t):
            return {"options": options, "reply": "J'annule la dernière modification.", "changes": [], "undo": True, "propose_profile": None}
        if m := re.search(r"(\d)\s*pages?", t):
            o["max_pages"] = int(m.group(1))
            changes.append({"action": "max_pages", "value": int(m.group(1))})
            notes.append(f"limite fixée à {m.group(1)} page(s)")
            continue
        if re.search(r"raccourc|plus court|condense|resume moins|allege", t):
            if re.search(r"mission|experience|realisation|description", t):
                o["realisations_max"] = 2
                changes.append({"action": "shorten", "target": "missions"})
                notes.append("2 réalisations maximum par mission")
            else:
                cur = len(split_sentences(view.get("resume", "") if view else profile["resume"]["text"]))
                o["shorten"]["res"] = max(1, min(2, cur - 1))
                changes.append({"action": "shorten", "target": "res"})
                notes.append(f"synthèse raccourcie ({o['shorten']['res']} phrase(s))")
            continue
        if m := re.search(r"(?:enleve|enlever|retire|retirer|supprime|supprimer|masque|masquer|cache|cacher|vire|sans)\s+(?:la |le |les |l')?(?:competence |mission |ligne )?(.+)", t):
            hit = _find_fact(profile, m.group(1))
            if hit:
                if hit[0] not in o["hidden"]:
                    o["hidden"].append(hit[0])
                changes.append({"action": "hide", "fact_id": hit[0]})
                notes.append(f"{hit[1]} masquée pour ce dossier")
            else:
                notes.append(f"je n'ai pas trouvé « {m.group(1)} » dans le dossier")
            continue
        if m := re.search(r"(?:remets?|reaffiche|affiche|ajoute|ajouter)\s+(?:la |le |les |l')?(?:competence |mission )?(.+)", t):
            hit = _find_fact(profile, m.group(1))
            if hit and hit[0] in o["hidden"]:
                o["hidden"].remove(hit[0])
                changes.append({"action": "unhide", "fact_id": hit[0]})
                notes.append(f"{hit[1]} réaffichée")
            elif hit:
                notes.append(f"{hit[1]} est déjà dans le dossier")
            elif m2 := re.search(r"disponib\w*\s*(?::)?\s*(.*)", part, re.I):
                val = m2.group(1).strip() or "Immédiate"
                o["overrides"]["id.disponibilite"] = val
                changes.append({"action": "set", "field": "disponibilite", "value": val})
                notes.append(f"disponibilité indiquée : {val}")
            else:
                label = part.split(maxsplit=1)[-1].strip(" .")
                propose = {"type": "competence", "label": label}
                notes.append(f"« {label} » n'est pas dans votre profil : je ne l'ajoute pas au dossier sans votre accord. "
                             "Voulez-vous l'ajouter à votre profil ?")
            continue
        if m := re.search(r"(?:je suis )?disponib\w*\s*(?::)?\s*(.+)", part, re.I):
            val = m.group(1).strip(" .")
            o["overrides"]["id.disponibilite"] = val[0].upper() + val[1:] if val else "Immédiate"
            changes.append({"action": "set", "field": "disponibilite", "value": o["overrides"]["id.disponibilite"]})
            notes.append(f"disponibilité : {o['overrides']['id.disponibilite']}")
            continue
        if m := re.search(r"mobil\w*\s*(?::)?\s*(.+)", part, re.I):
            o["overrides"]["id.mobilite"] = m.group(1).strip(" .")
            changes.append({"action": "set", "field": "mobilite", "value": o["overrides"]["id.mobilite"]})
            notes.append(f"mobilité : {o['overrides']['id.mobilite']}")
            continue
        if m := re.search(r"(?:mets?|met|place|passe)\s+(?:la |le |les |l')?(.+?)\s+(?:en premier|en tete|en avant|d'abord|en haut|en 1er)", t):
            target = m.group(1)
            sec = _sector(target)
            hit = _find_fact(profile, target.replace("mission ", ""))
            if hit and hit[0].startswith("m") and "." not in hit[0] and not hit[0].startswith("c"):
                order = [x["id"] for x in sorted(profile["missions"], key=lambda x: x.get("debut") or "", reverse=True)]
                order.remove(hit[0])
                o["order_missions"] = [hit[0], *order]
                changes.append({"action": "order_missions", "first": hit[0]})
                notes.append(f"{hit[1]} placée en premier")
            elif hit and hit[0].startswith("c"):
                lbl = next(c["label"] for c in profile["competences"] if c["id"] == hit[0])
                o["skills_first"] = [lbl, *[s for s in o["skills_first"] if s != lbl]]
                changes.append({"action": "skills_first", "label": lbl})
                notes.append(f"« {lbl} » en tête des compétences")
            elif sec:
                o["emphasis_sector"] = sec
                o["rephrased"] = {k: v for k, v in o.get("rephrased", {}).items() if k != "res"}
                changes.append({"action": "emphasis", "sector": sec})
                notes.append(f"secteur {sec.lower()} mis en avant")
            else:
                notes.append(f"je n'ai pas trouvé « {target} »")
            continue
        if re.search(r"original|reformul|comme avant|sans adaptation", t):
            o["rephrased"] = {}
            o["adapt"] = False
            changes.append({"action": "revert_all"})
            notes.append("textes d'origine repris partout")
            continue
        if re.search(r"anglais|english", t):
            notes.append("la version anglaise arrive bientôt ; je ne traduis pas encore automatiquement")
            continue
        notes.append(_llm_hint(part) or "je n'ai pas compris cette demande")

    def end(x: str) -> str:
        return x if x.endswith((".", "?", "!")) else x + "."
    reply = end("C'est fait : " + " ; ".join(notes)) if changes else (end(notes[0][0].upper() + notes[0][1:]) if notes else "D'accord.")
    if changes and any(c["action"] in ("hide", "shorten", "set") for c in changes):
        reply += " Ces changements ne concernent que ce dossier ; votre profil n'a pas changé."
    return {"options": o, "reply": reply, "changes": changes, "undo": False, "propose_profile": propose}


def _llm_hint(text: str) -> str | None:
    out = llm.complete_text(
        "Tu es l'assistant d'un outil de dossiers de compétences. Tu sais seulement : raccourcir la synthèse ou les "
        "missions, masquer ou réafficher un élément, mettre une mission/compétence/un secteur en avant, limiter le "
        "nombre de pages, indiquer la disponibilité ou la mobilité, revenir aux textes d'origine. "
        "En une phrase, propose la formulation à utiliser pour la demande de l'utilisateur.", text, max_tokens=120)
    return out.strip() if out else None
