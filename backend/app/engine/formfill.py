"""
Remplissage des modèles « formulaire » : libellés en ligne, cellules valeur, grilles de compétences
avec niveaux (chiffres ou jauges de symboles recolorées), zones d'en-tête.  [D2]
Règle D3 : un niveau absent du profil n'est jamais inventé (la jauge reste vide).
"""
from __future__ import annotations

import copy
import re
from collections import Counter

from docx.oxml.ns import qn

from . import docxutil as X

W_SYM, W_COLOR = qn("w:sym"), qn("w:color")
FILLED_DEFAULT, EMPTY_DEFAULT = "002060", "BFBFBF"


# ───────────────────────────── Valeurs ─────────────────────────────

def scalar_value(field: str, view: dict) -> str:
    if field == "experience_annees":
        y = view.get("experience_annees")
        return f"{y} ans" if y else ""
    v = view.get(field)
    if isinstance(v, list):
        return ", ".join(x if isinstance(x, str) else str(x) for x in v)
    return v or ""


def list_item_text(field: str, item, extra: dict) -> str:
    """Mise en forme d'un élément de liste selon l'exemple du modèle."""
    if isinstance(item, str):
        return item
    year_first = extra.get("year_first")
    ysep = extra.get("year_sep", " — ")
    sep = extra.get("sep", " — ")
    kind = item.get("_kind") or field
    if kind in ("formations", "formations_certifications") and "intitule" in item and "langue" not in item:
        core = item.get("intitule", "")
        if item.get("etablissement"):
            core += f"{sep}{item['etablissement']}"
        if not item.get("annee"):
            return core
        return f"{item['annee']}{ysep}{core}" if year_first else (
            f"{core} ({item['annee']})" if extra.get("paren_year", True) else f"{core}{sep}{item['annee']}")
    if kind == "certifications":
        core = item.get("intitule", "")
        if not item.get("annee"):
            return core
        return f"{item['annee']}{ysep}{core}" if year_first else f"{core} ({item['annee']})"
    if kind == "langues":
        if not item.get("niveau"):
            return item.get("langue", "")
        if extra.get("paren") and not extra.get("colon"):
            return f"{item['langue']} ({item['niveau']})"
        return f"{item['langue']} : {item['niveau']}"
    return str(item)


# ───────────────────────────── Libellés en ligne ─────────────────────────────

def fill_labels(p, labels: list, view: dict) -> None:
    """« Nom:\tMobilité géographique: » → « Nom: DIALLO\tMobilité géographique: Toulouse »."""
    from .filler import fill_after_label
    values = [scalar_value(f, view) for _, f in labels]
    if len(labels) == 1:
        if values[0]:
            fill_after_label(p, values[0])
        return
    rs = X.runs(p)
    vi = 0
    for ri, r in enumerate(rs):
        t = X.run_text(r)
        if ":" not in t or vi >= len(values):
            continue
        new, pos, ended_on_colon = "", 0, False
        for m in re.finditer(":", t):
            if vi >= len(values):
                break
            new += t[pos: m.end()]
            nt = t.find("\t", m.end())
            end = nt if nt != -1 else len(t)          # l'éventuelle valeur d'exemple s'arrête à la tabulation
            new += (" " + values[vi]) if values[vi] else ""
            vi += 1
            pos = end
            ended_on_colon = end == len(t)
        new += t[pos:]
        X.set_run_text(r, new)
        if ended_on_colon:                              # valeur d'exemple dans les runs suivants : on l'efface
            for rr in rs[ri + 1:]:
                txt = X.run_text(rr)
                if rr.find(qn("w:tab")) is not None or ":" in txt:
                    break
                X.set_run_text(rr, "")


# ───────────────────────────── Cellule valeur ─────────────────────────────

def fill_cell_value(ps: list, field: str, extra: dict, sample: str, view: dict) -> None:
    from .filler import safe_remove, years_text
    proto = ps[0]
    for p in ps[1:]:
        safe_remove(p)
    if extra.get("list"):
        items = [list_item_text(field, it, extra) for it in view.get(field, []) or []]
        items = [i for i in items if i]
        if not items:
            X.set_para_text(proto, "")
            return
        anchor = proto
        for it in items:
            new = X.clone_after(proto, anchor)
            X.set_para_text(new, it)
            anchor = new
        X.remove(proto)
        return
    if field == "experience_annees":
        val = years_text(sample, view.get("experience_annees")) or ""
    else:
        val = scalar_value(field, view)
    X.set_para_text(proto, val)


# ───────────────────────────── Grilles de compétences ─────────────────────────────

def _assign(groups: list[dict], comps: list[dict]) -> None:
    """Répartit les compétences du profil entre les lignes du modèle selon leurs catégories."""
    used: set[int] = set()
    for g in groups:
        g["items"] = []
    for g in groups:
        cats = [t for t in g["targets"] if not t.startswith(("@", "*"))]
        for idx, c in enumerate(comps):
            if idx not in used and c.get("categorie") in cats:
                g["items"].append(c)
                used.add(idx)
    rest = [c for idx, c in enumerate(comps) if idx not in used]
    star = next((g for g in groups if "*" in g["targets"]), None)
    if rest:
        target = star or next((g for g in groups if "langages" in g["targets"]), None) or \
            next((g for g in groups if not any(t.startswith("@") for t in g["targets"])), None)
        if target is not None:
            target["items"].extend(rest)


def _level_text(niveau, scale) -> str:
    if not niveau or not scale:
        return ""
    return str(max(1, min(scale, round(int(niveau) * scale / 5))))


def _sym_colors(tbl) -> tuple[str, str]:
    colors = []
    for r in tbl.iter(X.W_R):
        if r.find(W_SYM) is not None:
            c = r.find(qn("w:rPr"))
            col = c.find(W_COLOR) if c is not None else None
            colors.append(col.get(qn("w:val")) if col is not None else None)
    cnt = Counter(c for c in colors if c)
    if not cnt:
        return FILLED_DEFAULT, EMPTY_DEFAULT
    filled = colors[0] or cnt.most_common(1)[0][0]
    others = [c for c in cnt if c != filled]
    return filled, (others[0] if others else EMPTY_DEFAULT)


def _set_gauge(tc, niveau, scale, colors) -> None:
    sym_runs = [r for r in tc.iter(X.W_R) if r.find(W_SYM) is not None]
    if not niveau:
        for r in sym_runs:          # niveau inconnu : jauge vide, rien n'est inventé
            r.getparent().remove(r)
        return
    k = max(1, min(len(sym_runs), round(int(niveau) * len(sym_runs) / 5)))
    for i, r in enumerate(sym_runs):
        rpr = r.find(qn("w:rPr"))
        if rpr is None:
            rpr = r.makeelement(qn("w:rPr"), {})
            r.insert(0, rpr)
        col = rpr.find(W_COLOR)
        if col is None:
            col = rpr.makeelement(W_COLOR, {})
            rpr.append(col)
        for a in list(col.attrib):
            if a != qn("w:val"):
                del col.attrib[a]
        col.set(qn("w:val"), colors[0] if i < k else colors[1])


def _set_cell_text(tc, text: str) -> None:
    ps = list(tc.iterchildren(qn("w:p")))
    if not ps:
        return
    X.set_para_text(ps[0], text)
    for p in ps[1:]:
        tc.remove(p)


def _clone_row_as_continuation(tr):
    new = copy.deepcopy(tr)
    first = X.row_cells(new)[0]
    tcpr = first.find(qn("w:tcPr"))
    vm = tcpr.find(qn("w:vMerge")) if tcpr is not None else None
    if vm is not None:
        vm.attrib.pop(qn("w:val"), None)   # cellule de libellé fusionnée verticalement
    else:
        _set_cell_text(first, "")
    tr.addnext(new)
    return new


def build_groups(extra: dict) -> list[dict]:
    """Groupes de lignes consécutives partageant un libellé."""
    groups: list[dict] = []
    for e in extra["rows"]:
        if e["continuation"] and groups:
            groups[-1]["rows"].append(e)
        else:
            groups.append({"label": e["label"], "targets": e["targets"], "rows": [e], "mode": e["mode"]})
    return groups


def assign_all(groups_by_table: list[list[dict]], comps: list[dict]) -> None:
    """Répartition unique sur tous les tableaux de compétences du modèle (évite les doublons)."""
    _assign([g for gs in groups_by_table for g in gs], comps)


def _text_width_dxa(tbl) -> int:
    root = tbl.getroottree().getroot()
    sect = next(iter(root.iter(qn("w:sectPr"))), None)
    try:
        pg, mar = sect.find(qn("w:pgSz")), sect.find(qn("w:pgMar"))
        return int(pg.get(qn("w:w"))) - int(mar.get(qn("w:left"))) - int(mar.get(qn("w:right")))
    except (AttributeError, TypeError, ValueError):
        return 9600


def _widen_single_column(tbl) -> None:
    """Tableau d'une seule colonne étroite (« Techniques: ») : la valeur a besoin de toute la largeur."""
    if any(len(X.row_cells(tr)) != 1 for tr in X.table_rows(tbl)):
        return
    w = str(_text_width_dxa(tbl) - 200)
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for gc in grid.iterchildren(qn("w:gridCol")):
            gc.set(qn("w:w"), w)
    for tc in tbl.iter(qn("w:tc")):
        tcpr = tc.find(qn("w:tcPr"))
        tcw = tcpr.find(qn("w:tcW")) if tcpr is not None else None
        if tcw is not None:
            tcw.set(qn("w:w"), w)
            tcw.set(qn("w:type"), "dxa")


def fill_comp_table(tbl, extra: dict, view: dict, groups: list[dict] | None = None) -> None:
    from .filler import fill_after_label
    rows = X.table_rows(tbl)
    if groups is None:
        groups = build_groups(extra)
        _assign(groups, view.get("competences", []))
    if any(g["mode"] == "inline" for g in groups):
        _widen_single_column(tbl)
    colors = _sym_colors(tbl)
    scale = extra.get("scale")
    for g in groups:
        trs = [rows[e["r"]] for e in g["rows"]]
        if "@secteurs" in g["targets"]:
            values = view.get("secteurs", [])
        elif "@langues" in g["targets"]:
            from .formfill import list_item_text as li
            values = [li("langues", x, {"paren": True}) for x in view.get("langues", [])]
        else:
            values = [c["label"] for c in g["items"]]
        if g["mode"] in ("inline", "value"):
            tr = trs[0]
            if not values:
                for t in trs:
                    X.remove(t)
                continue
            cells = X.row_cells(tr)
            if g["mode"] == "inline":
                p = list(cells[0].iterchildren(qn("w:p")))[0]
                if ":" in X.para_text(p):
                    fill_after_label(p, ", ".join(values))
                else:
                    X.set_para_text(p, f"{g['label']} : {', '.join(values)}")
            else:
                sample = X.cell_text(cells[1])
                if "•" in sample:
                    _set_cell_text(cells[1], "   ".join("•" + v for v in values))
                else:
                    _set_cell_text(cells[1], ", ".join(values))
            continue
        # grille compétence / niveau
        items = g["items"] if not g["targets"][0].startswith("@") else [{"label": v, "niveau": None} for v in values]
        slots = [(tr, s) for tr, e in zip(trs, g["rows"]) for s in e["slots"]]
        per_row = max(1, len(g["rows"][-1]["slots"]))
        while len(slots) < len(items):
            new = _clone_row_as_continuation(trs[-1])
            trs.append(new)
            slots += [(new, s) for s in g["rows"][-1]["slots"]]
        for idx, (tr, (sc, lc)) in enumerate(slots):
            cells = X.row_cells(tr)
            if sc >= len(cells):
                continue
            it = items[idx] if idx < len(items) else None
            _set_cell_text(cells[sc], it["label"] if it else "")
            if lc < len(cells):
                if extra.get("level_kind") == "sym":
                    _set_gauge(cells[lc], it.get("niveau") if it else None, scale, colors)
                else:
                    _set_cell_text(cells[lc], _level_text(it.get("niveau"), scale) if it else "")
        # lignes entièrement vides en trop (on garde la première ligne du groupe)
        needed_rows = max(1, -(-len(items) // per_row))
        for tr in trs[needed_rows:]:
            X.remove(tr)
        if not items:
            for tr in trs[:1]:
                X.remove(tr)
