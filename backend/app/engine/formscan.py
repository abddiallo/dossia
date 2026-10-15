"""
Analyse des modèles « formulaire » et des structures en tableaux.  [D2]

  - lignes de tableau libellé → valeur (« Expérience | X années », « Réalisations | xxxxx ») ;
  - libellés en ligne (« Nom:\tMobilité géographique: ») ;
  - textes à remplacer (« POSTE », « Phrase de synthèse », « Langue1 : Niveau », « TRIGRAMME » dans l'en-tête) ;
  - grilles de compétences avec niveaux (chiffres ou jauges de symboles) ;
  - rôles des cellules dans une mission décrite par un tableau.
"""
from __future__ import annotations

import re

from docx.oxml.ns import qn

from . import docxutil as X
from . import forms as F
from .text import DATE_RANGE_RE, has_date_range, norm

W_SYM = qn("w:sym")


# ───────────────────────────── Utilitaires cellules ─────────────────────────────

def cell_paras(tc) -> list:
    return list(tc.iterchildren(qn("w:p")))


def cell_has_syms(tc) -> int:
    return sum(1 for _ in tc.iter(W_SYM))


def _para_index(el, p) -> int:
    for k, q in enumerate(X.element_paragraphs(el)):
        if q is p:
            return k
    return -1


# ───────────────────────────── Rôles dans un bloc mission ─────────────────────────────

ENV_PREFIX = re.compile(r"^(environnement( technique)?|technologies|outils|stack|env\.?)\s*:", re.I)


def _date_only(t: str) -> bool:
    m = DATE_RANGE_RE.search(t)
    if not m:
        return False
    rest = (t[: m.start()] + " " + t[m.end():])
    rest = re.sub(r"\((ou|si|or)\b[^)]*\)", " ", rest, flags=re.I)
    rest = re.sub(r"(?i)\b(dates?|p[ée]riode|du|de|from)\b", " ", rest)
    return not re.sub(r"[\s·\-–—|,:/()…\.]+", "", rest)


def paragraph_role(p, doc) -> str | None:
    """Rôle certain d'un paragraphe isolé, ou None si à déterminer par position."""
    t = X.para_text(p).strip()
    if not t:
        return "empty"
    labels = F.inline_labels(t, "mission")
    if len(labels) >= 2 or (len(labels) == 1 and t.rstrip().endswith(":") and labels[0][1] not in ("client", "poste")):
        return "labels:" + "|".join(f"{lab}={f}" for lab, f in labels)
    if has_date_range(t):
        return "dates" if _date_only(t) else "header"
    if ENV_PREFIX.match(t):
        return "env"
    f = F.mission_field(t)
    if f in ("client", "poste", "lieu"):
        return f
    if X.is_list_paragraph(p, doc):
        return "bullet"
    return None


def para_block_roles(paras: list, doc) -> list[str]:
    """Rôles pour une suite de paragraphes (blocs mission « classiques »)."""
    roles = [paragraph_role(p, doc) for p in paras]
    has_dates_only = "dates" in roles
    has_client = "header" in roles or "client" in roles
    has_poste = "poste" in roles
    has_ctx = False
    for idx, r in enumerate(roles):
        if r is not None:
            continue
        t = X.para_text(paras[idx]).strip()
        near_dates = has_dates_only and any(roles[j] == "dates" for j in (idx - 1, idx + 1) if 0 <= j < len(roles))
        if not has_client and near_dates and len(t) < 70:
            roles[idx], has_client = "client", True
        elif not has_poste and len(t) < 90 and not re.match(r"^(contexte|projet|mission|objectif)\s*:", t, re.I):
            roles[idx], has_poste = "poste", True
        elif not has_ctx:
            roles[idx], has_ctx = "contexte", True
        else:
            roles[idx] = "bullet" if idx and roles[idx - 1] == "bullet" else "other"
    return [r or "other" for r in roles]


def table_block_roles(tbl, doc) -> dict:
    """Rôles des paragraphes d'un tableau-mission : {paragraphe: rôle} (clé = l'élément lui-même)."""
    out: dict = {}
    for tr in X.table_rows(tbl):
        cells = X.row_cells(tr)
        texts = [X.cell_text(c).strip() for c in cells]
        j = 0
        while j < len(cells):
            t = texts[j]
            f = F.mission_field(t) if t else None
            nxt = texts[j + 1] if j + 1 < len(cells) else None
            is_label = (f is not None and nxt is not None and nxt != "" and not F.mission_field(nxt)
                        and not has_date_range(nxt) and not re.search(r"\b[A-Z]{4,}\b", t)
                        and not t.lstrip().startswith(("[", "{", "<")))   # « [Poste] » = valeur à remplacer
            if is_label:
                for p in cell_paras(cells[j]):
                    out[p] = "keep"
                value_role = {"client": "client", "poste": "poste", "dates": "dates", "contexte": "contexte",
                              "realisations": "bullet", "env": "env", "lieu": "lieu"}[f]
                for k, p in enumerate(cell_paras(cells[j + 1])):
                    out[p] = value_role if (k == 0 or value_role == "bullet") else "drop"
                j += 2
                continue
            ps = cell_paras(cells[j])
            if len([p for p in ps if X.para_text(p).strip()]) >= 2:
                # cellule riche (contexte + puces + environnement…) : logique des paragraphes
                for p, role in zip(ps, para_block_roles(ps, doc)):
                    out[p] = role
                j += 1
                continue
            for k, p in enumerate(ps):
                pt = X.para_text(p).strip()
                if not pt:
                    out[p] = "empty"
                elif has_date_range(pt):
                    out[p] = "dates" if _date_only(pt) else "header"
                elif F.mission_field(pt) in ("client", "poste", "lieu"):
                    out[p] = F.mission_field(pt)
                elif re.fullmatch(r"\[.*\]", pt):
                    out[p] = "contexte"   # « [Contexte de la mission] » seul dans sa cellule
                else:
                    out[p] = "keep"
            j += 1
    return out


def block_roles(elements: list, doc) -> list[str]:
    """Rôles alignés sur l'ordre de X.element_paragraphs pour chaque élément du bloc."""
    roles: list[str] = []
    run: list = []

    def flush():
        if run:
            roles.extend(para_block_roles(run, doc))
            run.clear()

    for el in elements:
        if el.tag == X.W_P:
            run.append(el)
        else:
            flush()
            m = table_block_roles(el, doc)
            roles.extend(m.get(p, "keep") for p in X.element_paragraphs(el))
    flush()
    return roles


# ───────────────────────────── Grilles / lignes de compétences ─────────────────────────────

def competence_table(ctx, i: int, legend_text: str = "") -> dict | None:
    """Décrit un tableau de compétences à libellés de lignes, ou None si ce n'en est pas un."""
    tbl = ctx.els[i]
    rows = X.table_rows(tbl)
    entries, header_rows = [], []
    current = None
    numeric = bool(re.search(r"\bniv|niveau|level", norm(X.element_text(tbl)))) or bool(re.search(r"\d\s*-\s*\w", legend_text))
    for r, tr in enumerate(rows):
        cells = X.row_cells(tr)
        texts = [X.cell_text(c).strip() for c in cells]
        nt = [norm(t) for t in texts]
        if any(re.search(r"^(domaine|competences?|technologies?)$", t) for t in nt) and any(re.search(r"^(niv|niveau|level)", t) for t in nt):
            header_rows.append(r)
            continue
        label_text = texts[0]
        targets = F.competence_target(label_text) if label_text else None
        if label_text and targets is None:
            # libellé inconnu en 1re colonne : ce n'est pas un tableau de compétences à libellés
            if r == 0:
                return None
            continue
        if not label_text and current is None:
            continue
        if label_text:
            current = {"label": label_text.rstrip(" :"), "targets": targets}
        n = len(cells)
        if n == 1:
            mode, slots, values = "inline", [], []
        elif n == 2:
            mode, slots, values = "value", [], [1]
        else:
            mode = "grid"
            slots = [[c, c + 1] for c in range(1, n - 1, 2)]
            values = []
        entries.append({"r": r, "label": current["label"], "targets": current["targets"], "mode": mode,
                        "slots": slots, "value_cells": values, "continuation": not bool(label_text)})
    if not entries:
        return None
    sym_count = max((cell_has_syms(c) for tr in rows for c in X.row_cells(tr)), default=0)
    scale = None
    if sym_count:
        scale = sym_count
    elif numeric:
        nums = [int(x) for x in re.findall(r"(\d)\s*-", legend_text)] or [5]
        scale = max(nums)
    return {"rows": entries, "header_rows": header_rows, "level_kind": "sym" if sym_count else ("num" if numeric else None),
            "scale": scale}


# ───────────────────────────── Balayage « formulaire » ─────────────────────────────

def form_scan(ctx) -> None:
    """Repère les champs de formulaire dans tout ce qui n'a pas encore été attribué."""
    for i, el in enumerate(ctx.els):
        if i in ctx.claimed_el:
            continue
        if el.tag == X.W_TBL:
            _scan_table(ctx, i, el)
        else:
            _scan_para(ctx, i, 0, el, None)
    _scan_headers(ctx)


def _scan_table(ctx, i: int, tbl) -> None:
    for r, tr in enumerate(X.table_rows(tbl)):
        cells = X.row_cells(tr)
        texts = [X.cell_text(c).strip() for c in cells]
        nonempty = [j for j, t in enumerate(texts) if t]
        handled = False
        if nonempty:
            j = nonempty[0]
            f = F.identity_field(texts[j]) if len(texts[j]) <= 40 else None
            if f and j + 1 < len(cells) and not F.identity_field(texts[j + 1] or "-"):
                tc = cells[j + 1]
                ps = cell_paras(tc)
                idxs = [_para_index(tbl, p) for p in ps]
                if all((i, k) not in ctx.claimed_p for k in idxs):
                    samples = [X.para_text(p).strip() for p in ps if X.para_text(p).strip()]
                    is_list = f in F.LIST_FIELDS
                    ctx.zone(kind="cell_value", field=f, confidence=0.93, key=f"cell:{f}",
                             loc={"el": i, "row": r, "cell": j + 1, "ps": idxs},
                             sample=" / ".join(samples)[:160] or texts[j], label=texts[j],
                             extra={"list": is_list, **F.list_format(samples or [""])})
                    for k in idxs + [_para_index(tbl, p) for p in cell_paras(cells[j])]:
                        ctx.claimed_p.add((i, k))
                    handled = True
        if handled:
            continue
        for c in cells:
            ps = cell_paras(c)
            lang = [p for p in ps if F.LANG_PLACEHOLDER.match(F.label_norm(X.para_text(p)))]
            if len(lang) >= 1 and len(lang) == len([p for p in ps if X.para_text(p).strip()]):
                idxs = [_para_index(tbl, p) for p in lang]
                ctx.zone(kind="list", field="langues", confidence=0.92, key="langues",
                         loc={"paras": [[i, k] for k in idxs]}, sample=" / ".join(X.para_text(p) for p in lang),
                         label="Langues", extra=F.list_format([X.para_text(p) for p in lang]))
                continue
            for p in ps:
                k = _para_index(tbl, p)
                if (i, k) in ctx.claimed_p:
                    continue
                others = [_para_index(tbl, q) for q in ps if q is not p]
                _scan_para(ctx, i, k, p, others)


def _scan_para(ctx, i: int, k: int, p, cell_siblings: list[int] | None) -> None:
    if (i, k) in ctx.claimed_p:
        return
    t = X.para_text(p).strip()
    if not t:
        return
    n = F.label_norm(t)
    labels = F.inline_labels(t, "identity")
    if labels and (t.rstrip().endswith(":") or len(labels) >= 2 or re.search(r":\s*\S", t)):
        ctx.zone(kind="labels", field=",".join(f for _, f in labels), confidence=0.93,
                 key="labels:" + ",".join(f for _, f in labels), loc={"el": i, "p": k}, sample=t,
                 label=" / ".join(lab for lab, _ in labels), extra={"labels": [[lab, f] for lab, f in labels]})
        return
    if F.TITLE_PLACEHOLDER.match(n) and "id:titre" not in ctx.keys():
        ctx.zone(kind="field", field="titre", confidence=0.92, key="id:titre", loc={"el": i, "p": k}, sample=t,
                 label="Titre", extra={"mode": "replace"})
        return
    if F.SUMMARY_PLACEHOLDER.match(n) and "resume" not in ctx.keys():
        ctx.zone(kind="field", field="resume", confidence=0.92, key="resume",
                 loc={"el": i, "p": k, "extra_ps": cell_siblings or []}, sample=t, label="Synthèse",
                 extra={"mode": "replace"})
        return


def _scan_headers(ctx) -> None:
    seen_parts: list = []
    for si, sec in enumerate(ctx.doc.sections):
        for part_name in ("header", "footer"):
            part = getattr(sec, part_name)
            if part.is_linked_to_previous or any(part._element is e for e in seen_parts):
                continue
            seen_parts.append(part._element)
            for k, para in enumerate(part.paragraphs):
                t = para.text.strip()
                n = F.label_norm(t)
                field = None
                if re.fullmatch(r"trigramme|initiales", n):
                    field = "trigramme"
                elif re.fullmatch(r"prenom nom|nom prenom|nom et prenom", n):
                    field = "nom_complet"
                elif F.TITLE_PLACEHOLDER.match(n) and len(t) < 30:
                    field = "titre"
                if field:
                    ctx.zone(kind="field", field=field, confidence=0.9, key=f"hdr:{si}:{part_name}:{k}",
                             loc={"hdr": [si, part_name, k]}, sample=t, label=f"En-tête : {t}", extra={"mode": "replace"})
