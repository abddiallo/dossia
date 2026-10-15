"""
Construction du contenu d'un dossier à partir du profil, avec traçabilité.  [D3]

build() renvoie :
  - view     : valeurs prêtes à injecter dans le modèle (filler.fill)
  - segments : chaque texte du dossier avec ses faits sources, l'opération (copie, reformulation,
               réordonnancement, retouche) et un niveau de risque
  - stats    : origine des éléments (« 0 % ajouté par l'IA »)
  - question : au plus UNE question avant envoi (parcours express)

Invariant : tout segment non vide doit citer au moins un fait existant du profil, sinon
build() lève InventionError. Les reformulations IA qui introduisent une compétence ou un
chiffre absent de la source sont rejetées et remplacées par le texte d'origine.
"""
from __future__ import annotations

import re
from collections import Counter

from . import llm
from .profile import display_name, facts, generic_client, known_skill_labels, mission_dates, years_of_experience
from .skills import detect_sectors, family, find_in_text
from .text import split_sentences


class InventionError(Exception):
    pass


DEFAULT_OPTIONS = {
    "adapt": True, "anonymize": None, "anonymize_clients": None, "max_missions": None, "realisations_max": None,
    "hidden": [], "overrides": {}, "order_missions": None, "skills_first": [], "emphasis_sector": None,
    "shorten": {}, "rephrased": {}, "language": "fr",
}


def analyze_posting(text: str | None) -> dict:
    if not text:
        return {"skills": [], "sectors": [], "text": ""}
    return {"skills": find_in_text(text), "sectors": detect_sectors(text), "text": text[:4000]}


def _main_sector(profile: dict) -> str | None:
    c = Counter()
    for m in profile["missions"]:
        if m.get("secteur"):
            c[m["secteur"]] += _months(m)
    return c.most_common(1)[0][0] if c else None


def _months(m: dict) -> int:
    try:
        a = int((m.get("debut") or "0")[:4])
        b = int((m.get("fin") or "2026")[:4])
        return max(1, (b - a) * 12)
    except ValueError:
        return 12


def mission_relevance(m: dict, posting: dict) -> float:
    want: set[str] = set()
    for s in posting["skills"]:
        want |= family(s)
    have = set(m.get("environnement", [])) | set(find_in_text(" ".join(r["text"] for r in m["realisations"])))
    score = len(have & want) * 2.0
    if posting["sectors"] and m.get("secteur") in posting["sectors"][:2]:
        score += 3
    score += int((m.get("debut") or "2000")[:4]) / 1000.0  # léger bonus récence
    return score


# ───────────────────────────── Reformulation IA contrôlée ─────────────────────────────

REPHRASE_SYSTEM = (
    "Tu adaptes un dossier de compétences à une fiche de poste. Tu peux uniquement REFORMULER les textes fournis "
    "pour mettre en avant ce qui correspond au poste. Interdits : ajouter une compétence, une technologie, un chiffre, "
    "une durée, un client, une responsabilité qui ne figure pas dans le texte source. Garde la même langue. "
    "Si un texte ne gagne rien à être reformulé, renvoie-le à l'identique."
)


def _numbers(t: str) -> set[str]:
    return set(re.findall(r"\d+", t or ""))


def validate_rephrase(source: str, new: str, allowed_skills: set[str]) -> bool:
    if not new or len(new) > len(source) * 1.6 + 80:
        return False
    if not _numbers(new) <= _numbers(source) | _numbers(" ".join(allowed_skills)):
        return False
    allowed = set()
    for s in allowed_skills | set(find_in_text(source)):
        allowed |= family(s)
    return set(find_in_text(new)) <= allowed


def llm_rephrase(profile: dict, posting: dict, ids: list[str]) -> dict[str, str]:
    """Reformule les faits demandés ; renvoie seulement les reformulations valides."""
    if not ids or not posting.get("text") or not llm.available():
        return {}
    f = facts(profile)
    items = [{"id": i, "text": f[i]} for i in ids if f.get(i)]
    import json
    data = llm.complete_json(
        REPHRASE_SYSTEM,
        "Fiche de poste :\n" + posting["text"] + "\n\nTextes à adapter (garde les id) :\n" + json.dumps(items, ensure_ascii=False),
        '[{"id": "...", "text": "..."}]', max_tokens=3000,
    )
    out: dict[str, str] = {}
    if not isinstance(data, list):
        return out
    skills = known_skill_labels(profile)
    for it in data:
        i, t = it.get("id"), (it.get("text") or "").strip()
        if i in f and t and t != f[i] and validate_rephrase(f[i], t, skills if i == "res" else _skills_near(profile, i)):
            out[i] = t
    return out


def _skills_near(profile: dict, fact_id: str) -> set[str]:
    mid = fact_id.split(".")[0]
    for m in profile["missions"]:
        if m["id"] == mid:
            return set(m["environnement"])
    return set()


# ───────────────────────────── Construction ─────────────────────────────

def build(profile: dict, spec: dict, options: dict | None = None, posting: dict | None = None) -> dict:
    o = {**DEFAULT_OPTIONS, **(options or {})}
    posting = dict(posting or {"skills": [], "sectors": [], "text": ""})
    if o.get("emphasis_sector"):  # demandé explicitement par l'utilisateur → pas de question
        posting["sectors"] = [o["emphasis_sector"], *[s for s in posting.get("sectors", []) if s != o["emphasis_sector"]]]
        o["accepted"] = [*o.get("accepted", []), "res"]
    cons = spec.get("constraints", {})
    anonymize = cons.get("anonymize", False) if o["anonymize"] is None else o["anonymize"]
    anon_clients = cons.get("anonymize_clients", False) if o["anonymize_clients"] is None else o["anonymize_clients"]
    hidden = set(o["hidden"])
    over = o["overrides"]
    reph = o["rephrased"] if o["adapt"] else {}
    f = facts(profile)
    segs: list[dict] = []

    def seg(field: str, fact_ids: list[str], final: str, op: str, original: str | None = None,
            risk: str = "none", reason: str | None = None, hide: bool = False) -> str:
        key = f"{field}:{fact_ids[0] if fact_ids else '-'}"
        segs.append({"key": key, "field": field, "source_fact_ids": fact_ids, "final_text": final,
                     "original_text": original if original is not None else " / ".join(f.get(i, "") for i in fact_ids),
                     "op": op, "risk": risk, "risk_reason": reason, "hidden": hide})
        return final

    def text_of(fid: str, field: str) -> str:
        """Texte final d'un fait : retouche > raccourci > reformulation IA > original."""
        orig = f.get(fid, "")
        if fid in hidden:
            seg(field, [fid], orig, "copy", hide=True)
            return ""
        if fid in over:
            return seg(field, [fid], over[fid], "user_edit", hide=fid in hidden)
        if fid in o["shorten"]:
            n = int(o["shorten"][fid])
            return seg(field, [fid], " ".join(split_sentences(reph.get(fid, orig))[:n]), "user_edit", hide=fid in hidden)
        if fid in reph:
            return seg(field, [fid], reph[fid], "rephrase", hide=fid in hidden)
        return seg(field, [fid], orig, "copy", hide=fid in hidden)

    ident = profile["identite"]
    view: dict = {"anonymized": anonymize}
    view["nom_affiche"] = display_name(profile, anonymize)
    pre, nom = (ident.get("prenom") or "").strip(), (ident.get("nom") or "").strip()
    view["prenom"] = (pre[:1] + ".") if anonymize and pre else pre
    view["nom"] = (nom[:1] + ".") if anonymize and nom else nom.upper()
    view["nom_complet"] = view["nom_affiche"]
    view["trigramme"] = (pre[:1] + nom[:2]).upper() if (pre or nom) else ""
    view["ville"] = ident.get("ville") or ""
    view["titre"] = text_of("id.titre", "titre") if f.get("id.titre") else ""
    view["experience_annees"] = years_of_experience(profile)
    for k in ("disponibilite", "mobilite"):
        fid = f"id.{k}"
        view[k] = (over.get(fid) or ident.get(k) or "") if fid not in hidden else ""
        if view[k]:
            seg(k, [fid], view[k], "user_edit" if fid in over else "copy", original=ident.get(k) or "")

    # synthèse
    res = text_of("res", "resume") if f.get("res") else ""
    view["resume"] = res
    main = _main_sector(profile)
    if "res" in reph and posting["sectors"] and main and posting["sectors"][0] != main and "res" not in o.get("accepted", []):
        segs[-1]["risk"] = "review"
        segs[-1]["risk_reason"] = (f"La synthèse met en avant le secteur {posting['sectors'][0].lower()} "
                                   f"alors que votre expérience principale est dans le secteur {main.lower()}.")

    # compétences : pertinentes d'abord
    comps = [c for c in profile["competences"] if c["id"] not in hidden]
    want: set[str] = set()
    for s in posting["skills"] if o["adapt"] else []:
        want |= family(s)
    first = [s.lower() for s in o["skills_first"]]
    ranked = sorted(enumerate(comps), key=lambda x: (
        0 if x[1]["label"].lower() in first else 1,
        0 if x[1]["label"] in want else 1, x[0]))
    ordered = [c for _, c in ranked]
    view["competences"] = ordered
    seg("competences", [c["id"] for c in ordered], ", ".join(c["label"] for c in ordered),
        "reorder" if [c["id"] for c in ordered] != [c["id"] for c in comps] else "copy",
        original=", ".join(c["label"] for c in comps))
    for c in profile["competences"]:
        if c["id"] in hidden:
            seg("competences", [c["id"]], c["label"], "copy", hide=True)

    # missions
    missions = [m for m in profile["missions"] if m["id"] not in hidden]
    missions.sort(key=lambda m: (m.get("debut") or "0000"), reverse=True)
    if o["order_missions"]:
        pos = {mid: i for i, mid in enumerate(o["order_missions"])}
        missions.sort(key=lambda m: pos.get(m["id"], 999))
    if o["max_missions"] and len(missions) > o["max_missions"]:
        if o.get("drop_strategy") == "recent":
            keep = sorted(missions, key=lambda m: m.get("debut") or "0000", reverse=True)[: o["max_missions"]]
        else:
            keep = sorted(missions, key=lambda m: mission_relevance(m, posting), reverse=True)[: o["max_missions"]]
        keep_ids = {m["id"] for m in keep}
        missions = [m for m in missions if m["id"] in keep_ids]
    vm = []
    for m in missions:
        reals = [r for r in m["realisations"] if r["id"] not in hidden]  # masquées : tracées mais non affichées
        if o["adapt"] and want:
            reals.sort(key=lambda r: -len(set(find_in_text(r["text"])) & want))
        if o["realisations_max"]:
            reals = reals[: o["realisations_max"]]
        client = generic_client(m) if anon_clients else m.get("client", "")
        seg("mission.client", [m["id"]], client, "copy" if not anon_clients else "rephrase",
            original=m.get("client", ""))
        for r in m["realisations"]:
            if r["id"] in hidden:
                text_of(r["id"], "mission.realisation")  # tracée comme masquée
        vm.append({
            "id": m["id"],
            "client": client,
            "dates": mission_dates(m),
            "debut_fmt": _mmYYYY(m.get("debut")),
            "fin_fmt": _mmYYYY(m.get("fin")),
            "poste": seg("mission.poste", [m["id"]], over.get(m["id"] + ".poste", m.get("poste", "")),
                         "user_edit" if m["id"] + ".poste" in over else "copy", original=m.get("poste", "")),
            "lieu": m.get("lieu", ""),
            "contexte": text_of(m["contexte"]["id"], "mission.contexte") if m["contexte"]["text"] else "",
            "realisations": [text_of(r["id"], "mission.realisation") for r in reals],
            "environnement": seg("mission.env", [m["id"] + ".env"], ", ".join(m["environnement"]), "copy"),
            "secteur": m.get("secteur", ""),
        })
    view["missions"] = vm
    for key in ("formations", "certifications", "langues"):
        view[key] = [it for it in profile[key] if it["id"] not in hidden]
        for it in view[key]:
            seg(key, [it["id"]], f.get(it["id"], ""), "copy")
    view["formations_certifications"] = [{**x, "_kind": "formations"} for x in view["formations"]] + \
        [{**x, "_kind": "certifications"} for x in view["certifications"]]
    view["competences_top"] = [c["label"] for c in ordered[:6]]
    secteurs = []
    for m in missions:
        if m.get("secteur") and m["secteur"] not in secteurs:
            secteurs.append(m["secteur"])
    view["secteurs"] = secteurs
    if secteurs:
        seg("secteurs", [m["id"] for m in missions if m.get("secteur")], ", ".join(secteurs), "copy")

    verify(segs, f)
    return {"view": view, "segments": segs, "stats": origin_stats(segs), "question": first_question(segs)}


def _mmYYYY(v: str | None) -> str:
    if not v:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{2})", v)
    return f"{m.group(2)}/{m.group(1)}" if m else v


def verify(segs: list[dict], f: dict) -> None:
    for s in segs:
        if not s["final_text"]:
            continue
        if not s["source_fact_ids"] or any(i not in f for i in s["source_fact_ids"]):
            raise InventionError(f"Segment sans source : {s['field']} « {s['final_text'][:60]} »")


def origin_stats(segs: list[dict]) -> dict:
    tot = Counter()
    for s in segs:
        if s["hidden"] or not s["final_text"]:
            continue
        tot[s["op"]] += len(s["final_text"])
    n = sum(tot.values()) or 1
    return {"copy": round(tot["copy"] / n, 3), "rephrase": round(tot["rephrase"] / n, 3),
            "reorder": round(tot["reorder"] / n, 3), "user_edit": round(tot["user_edit"] / n, 3), "added": 0.0}


def first_question(segs: list[dict]) -> dict | None:
    for s in segs:
        if s["risk"] == "review":
            return {"id": s["key"], "text": s["risk_reason"] + " Ça vous va ?",
                    "choices": ["Oui, parfait", "Revenir à l'original"]}
    return None


def rephrase_targets(profile: dict, posting: dict, limit: int = 8) -> list[str]:
    """Faits qui valent la peine d'être adaptés : la synthèse + les réalisations les plus proches du poste."""
    if not posting.get("skills") and not posting.get("sectors"):
        return []
    want: set[str] = set()
    for s in posting["skills"]:
        want |= family(s)
    ids = ["res"] if profile["resume"]["text"] else []
    scored = []
    for m in profile["missions"]:
        for r in m["realisations"]:
            scored.append((len(set(find_in_text(r["text"])) & want) + (1 if m.get("secteur") in posting["sectors"] else 0), r["id"]))
    ids += [i for s, i in sorted(scored, reverse=True) if s > 0][:limit]
    return ids
