"""
Remplissage d'un modèle d'ESN à partir de sa spec et d'une « vue » du profil.  [D2]

Règle d'or : on ne crée jamais de mise en forme. On réutilise les paragraphes, lignes
de tableau et runs du modèle (clonage XML), puis on remplace uniquement le texte.
"""
from __future__ import annotations

import copy
import re
from collections import OrderedDict
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from . import docxutil as X
from .text import DATE_GUIDANCE_RE, DATE_RANGE_RE

PUNCT_RUN = re.compile(r"^[\s·\-–—|,:/()•]*$")
CAT_LABELS = {
    "langages": "Langages", "frameworks": "Frameworks", "outils": "Outils", "cloud": "Cloud",
    "bases": "Bases de données", "normes": "Normes", "methodes": "Méthodes", "secteurs": "Secteurs",
    "systemes": "Systèmes", "autres": "Autres",
}


# ───────────────────────────── Formatage des valeurs ─────────────────────────────

def stars(level: int | None, char: str | None) -> str:
    if not char or not level:
        return ""
    empty = {"●": "○", "★": "☆", "■": "□"}[char]
    lvl = max(1, min(5, int(level)))
    return char * lvl + empty * (5 - lvl)


def competences_by_cat(comps: list[dict]) -> list[tuple[str, str]]:
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for c in comps:
        cat = c.get("categorie_label") or CAT_LABELS.get(c.get("categorie") or "", (c.get("categorie") or "Autres").title())
        groups.setdefault(cat, []).append(c["label"])
    return [(k, ", ".join(v)) for k, v in groups.items()]


def fmt_list_item(field: str, item, extra: dict) -> str:
    sep = extra.get("sep", " — ")
    if isinstance(item, str):
        return item
    if field == "formations":
        s = item.get("intitule", "")
        if item.get("etablissement"):
            s += f"{sep}{item['etablissement']}"
        if item.get("annee"):
            s += f" ({item['annee']})" if extra.get("paren_year", True) else f"{sep}{item['annee']}"
        return s
    if field == "certifications":
        s = item.get("intitule", "")
        return s + (f" ({item['annee']})" if item.get("annee") else "")
    if field == "langues":
        if item.get("niveau"):
            return f"{item['langue']} : {item['niveau']}" if extra.get("colon", True) else f"{item['langue']} ({item['niveau']})"
        return item.get("langue", "")
    return str(item)


def years_text(sample: str, years: int | None) -> str | None:
    if years is None:
        return None
    new, n = re.subn(r"(\[[^\]]*\]|\bX+\b|\d+\+?)(\s*ann[ée]es?\b|\s*ans?\b)", lambda m: f"{years}{m.group(2)}",
                     sample, count=1)
    return new if n else f"{years} ans d'expérience"


# ───────────────────────────── Écriture dans les paragraphes ─────────────────────────────

def fill_after_label(p_el, value: str) -> None:
    """« Disponibilité : sous 1 mois » → garde « Disponibilité : », remplace la valeur (et sa mise en forme)."""
    rs = X.runs(p_el)
    texts = [X.run_text(r) for r in rs]
    k = next((i for i, t in enumerate(texts) if ":" in t), None)
    if k is None:
        X.set_para_text(p_el, value)
        return
    head = texts[k][: texts[k].index(":") + 1] + " "
    tail_text = texts[k][texts[k].index(":") + 1:].strip()
    if k + 1 < len(rs) and not tail_text:
        X.set_run_text(rs[k], head)
        X.set_run_text(rs[k + 1], value)
        for r in rs[k + 2:]:
            X.remove(r)
    else:
        X.set_run_text(rs[k], head + value)
        for r in rs[k + 1:]:
            X.remove(r)


def fill_header(p_el, client: str, dates: str) -> None:
    """Ligne « Client · période » : conserve séparateurs et mise en forme de chaque partie."""
    rs = X.runs(p_el)
    texts = [X.run_text(r) for r in rs]
    full = "".join(texts)
    m = DATE_RANGE_RE.search(full)
    if not m or not rs:
        X.set_para_text(p_el, f"{client} · {dates}" if client else dates)
        return
    before, after = full[: m.start()], full[m.end():]
    sep = re.search(r"[\s·\-–—|,:/(]*$", before).group(0) or " · "
    date_first = m.start() < len(before.strip()) or not before.strip()
    # positions des runs
    pos, bounds = 0, []
    for t in texts:
        bounds.append((pos, pos + len(t)))
        pos += len(t)
    on_boundary = any(b[0] == m.start() for b in bounds) and any(b[1] == m.end() for b in bounds)
    if not on_boundary or date_first:
        new = (f"{client}{sep}{dates}" if client else dates) + (after if PUNCT_RUN.match(after or "") else "")
        X.set_run_text(rs[0], new)
        for r in rs[1:]:
            X.remove(r)
        return
    client_done = date_done = False
    for r, (a, b), t in zip(rs, bounds, texts):
        if b <= m.start():                       # partie client
            if PUNCT_RUN.match(t):
                continue
            if not client_done:
                X.set_run_text(r, client + (re.search(r"[\s·\-–—|,:/(]*$", t).group(0) if b == m.start() else ""))
                client_done = True
            else:
                X.remove(r)
        elif a < m.end():                        # partie période
            if not date_done:
                X.set_run_text(r, dates)
                date_done = True
            else:
                X.remove(r)
        elif not PUNCT_RUN.match(t):             # reste (ex. lieu de l'autre consultant)
            X.remove(r)


def _clear_extra_paras_in_cell(p_el) -> None:
    tc = p_el.getparent()
    if tc is not None and tc.tag == qn("w:tc"):
        ps = list(tc.iterchildren(qn("w:p")))
        for p in ps[1:]:
            X.remove(p)


# ───────────────────────────── Blocs mission ─────────────────────────────

def safe_remove(p) -> None:
    """Supprime un paragraphe, sauf s'il est le dernier de sa cellule (Word l'exige) : on le vide alors."""
    parent = p.getparent()
    if parent is not None and parent.tag == qn("w:tc") and len(list(parent.iterchildren(qn("w:p")))) <= 1:
        X.set_para_text(p, "")
        return
    X.remove(p)


def fill_dates(p, m: dict) -> None:
    """« Dates: De XXXX à XXXX » → « Dates: De 01/2023 à 06/2024 » ; retire « (ou … si toujours en cours) »."""
    text = X.para_text(p)
    mt = DATE_RANGE_RE.search(text)
    if not mt:
        X.set_para_text(p, m.get("dates", ""))
        return
    raw = mt.group(0)
    if re.match(r"(?i)de\s", raw) and re.search(r"\bà\b|\ba\b", raw):
        fmt = f"De {m.get('debut_fmt') or '?'} à {m.get('fin_fmt') or 'aujourd’hui'}"
    else:
        fmt = m.get("dates", "")
    after = DATE_GUIDANCE_RE.sub("", text[mt.end():])
    X.set_para_text(p, text[: mt.start()] + fmt + after)


TOKEN_RE = re.compile(r"\b(CLIENT|ENTREPRISE|SOCI[EÉ]T[EÉ]|COMPANY)\b")


def fill_client(p, m: dict) -> None:
    text = X.para_text(p).strip()
    client = m.get("client", "")
    if TOKEN_RE.search(text) and not TOKEN_RE.fullmatch(text):
        new = TOKEN_RE.sub(client, text)
        new = re.sub(r"(?i)^sujets?\b", m.get("poste") or "Mission", new)
        X.set_para_text(p, new)
    else:
        X.set_para_text(p, client)


def _fix_narrow_paragraph(p) -> None:
    """Les modèles qui alignent des libellés grâce à un paragraphe très étroit : on rend la largeur normale."""
    ppr = p.find(qn("w:pPr"))
    if ppr is None:
        return
    ind = ppr.find(qn("w:ind"))
    if ind is not None and ind.get(qn("w:right")):
        ind.set(qn("w:right"), "0")
    sp = ppr.find(qn("w:spacing"))
    if sp is not None and sp.get(qn("w:line")) and int(sp.get(qn("w:line"))) > 360:
        sp.attrib.pop(qn("w:line"), None)
        sp.attrib.pop(qn("w:lineRule"), None)


LINE_EMU = 180000          # ≈ 0,5 cm par ligne de texte courant
CHARS_PER_LINE = 95


def _resize_vertical_rule(p, n_lines: int) -> None:
    """Filet vertical décoratif (dessin très fin de hauteur fixe) : on l'ajuste à la hauteur réelle du texte,
    sinon il déborde sur le bloc suivant. Toutes les valeurs de géométrie sont modifiées ensemble (DrawingML + VML)."""
    for alt in p.iter(X.MC_ALT):
        ext = next(alt.iter(qn("wp:extent")), None)
        if ext is None:
            continue
        try:
            cx, cy = int(ext.get("cx")), int(ext.get("cy"))
        except (TypeError, ValueError):
            continue
        if not (cx < 30000 and cy > 300000):      # uniquement les filets verticaux
            continue
        new = max(LINE_EMU, n_lines * LINE_EMU + 60000)
        old_s, new_s = str(cy), str(new)
        for el in alt.iter():
            for k, v in list(el.attrib.items()):
                if old_s in v:
                    el.set(k, v.replace(old_s, new_s))
                elif k == "style" and "height:" in v:
                    el.set(k, re.sub(r"height:[\d.]+pt", f"height:{round(new / 12700, 2)}pt", v))


def fill_label_lines(p, spec: str, m: dict) -> None:
    """Paragraphe « Contexte : Présentation : Responsabilités : Environnement : » → une ligne par libellé."""
    pairs = [x.split("=", 1) for x in spec.split("|") if "=" in x]
    lines: list[str] = []
    used = set()
    for label, field in pairs:
        if field == "contexte":
            if "contexte" in used or not m.get("contexte"):
                continue
            used.add("contexte")
            lines.append(f"{label} : {m['contexte']}")
        elif field == "realisations":
            if m.get("realisations"):
                lines.append(f"{label} :")
                lines += [f"•  {r}" for r in m["realisations"]]
        elif field == "env":
            if m.get("environnement"):
                lines.append(f"{label} : {m['environnement']}")
        elif field in ("client", "poste", "lieu", "dates"):
            v = m.get(field if field != "dates" else "dates")
            if v:
                lines.append(f"{label} : {v}")
    if not lines:
        safe_remove(p)
        return
    _fix_narrow_paragraph(p)
    _resize_vertical_rule(p, sum(max(1, -(-len(line) // CHARS_PER_LINE)) for line in lines))
    template = copy.deepcopy(p)
    for r in list(template.iterchildren(X.W_R)):   # le clone ne garde pas les dessins (ex. filet vertical)
        if r.find(qn("w:drawing")) is not None or r.find(X.MC_ALT) is not None or r.find(qn("w:pict")) is not None:
            template.remove(r)
    X.set_para_text(p, lines[0])
    anchor = p
    for line in lines[1:]:
        new = copy.deepcopy(template)
        X.set_para_text(new, line)
        anchor.addnext(new)
        anchor = new


def fill_mission(paras: list, roles: list[str], m: dict) -> None:
    bullet_proto = None
    for p, role in zip(paras, roles):
        if role == "header":
            fill_header(p, m.get("client", ""), m.get("dates", ""))
        elif role == "dates":
            fill_dates(p, m)
        elif role == "client":
            fill_client(p, m)
        elif role == "poste":
            X.set_para_text(p, m.get("poste", ""))
        elif role == "lieu":
            X.set_para_text(p, m.get("lieu", "")) if m.get("lieu") else safe_remove(p)
        elif role == "contexte":
            if m.get("contexte"):
                if re.match(r"^\s*(contexte|projet)[^:]{0,30}:", X.para_text(p), re.I):
                    fill_after_label(p, m["contexte"])
                else:
                    X.set_para_text(p, m["contexte"])
            else:
                safe_remove(p)
        elif role == "env":
            if m.get("environnement"):
                fill_after_label(p, m["environnement"])
            else:
                safe_remove(p)
        elif role.startswith("labels:"):
            fill_label_lines(p, role[7:], m)
        elif role == "bullet":
            if bullet_proto is None:
                bullet_proto = p
            else:
                safe_remove(p)
        elif role in ("other", "drop"):
            safe_remove(p)
    if bullet_proto is not None:
        items = m.get("realisations") or []
        bullet_char = X.strip_leading_bullet_char(bullet_proto)
        anchor = bullet_proto
        for it in items:
            new = X.clone_after(bullet_proto, anchor)
            X.set_para_text(new, f"{bullet_char} {it}" if bullet_char else it)
            anchor = new
        safe_remove(bullet_proto) if not items else X.remove(bullet_proto)


def _resolve_p(doc, els, loc):
    """Paragraphe ciblé : dans le corps (el, p) ou dans un en-tête / pied de page (hdr)."""
    if "hdr" in loc:
        si, part, k = loc["hdr"]
        return getattr(doc.sections[si], part).paragraphs[k]._p
    return X.element_paragraphs(els[loc["el"]])[loc["p"]]


def fill_labels(p, labels, view):
    from .formfill import fill_labels as _fl
    _fl(p, labels, view)


def _fill_cell_value(ps, field, extra, sample, view):
    from .formfill import fill_cell_value
    fill_cell_value(ps, field, extra, sample, view)


def _fill_comp_table(tbl, extra, view, groups=None):
    from .formfill import fill_comp_table
    fill_comp_table(tbl, extra, view, groups)


def _flat_paras(elements: list) -> list:
    return [p for el in elements for p in X.element_paragraphs(el)]


# ───────────────────────────── Point d'entrée ─────────────────────────────

def fill(template_path: str | Path, spec: dict, view: dict, out_path: str | Path) -> dict:
    doc = Document(str(template_path))
    els = X.body_elements(doc)
    txs = X.textboxes(doc)
    report = {"missions": 0, "warnings": []}

    # 1) Résolution de toutes les cibles AVANT modification (les index bougent ensuite)
    jobs = []
    for z in spec["zones"]:
        if z["status"] == "pending" or z["kind"] == "missing":
            continue  # zone non tranchée : laissée telle quelle (le statut du modèle l'empêche en pratique)
        loc, kind = z["loc"], z["kind"]
        try:
            if kind in ("field", "labels"):
                p = _resolve_p(doc, els, loc)
                extra = [els[i] for i in loc.get("extra_els", [])]
                if "extra_ps" in loc:
                    eps = X.element_paragraphs(els[loc["el"]])
                    extra += [eps[k] for k in loc["extra_ps"]]
                jobs.append((z, {"p": p, "extra": extra}))
            elif kind == "list":
                if "paras" in loc:
                    items = [X.element_paragraphs(els[e])[k] for e, k in loc["paras"]]
                else:
                    items = [els[i] for i in loc["els"]]
                jobs.append((z, {"items": items}))
            elif kind == "cell_value":
                tc = X.row_cells(X.table_rows(els[loc["el"]])[loc["row"]])[loc["cell"]]
                jobs.append((z, {"ps": list(tc.iterchildren(qn("w:p")))}))
            elif kind == "comp_table":
                jobs.append((z, {"tbl": els[loc["el"]]}))
            elif kind == "table_rows":
                tbl = els[loc["el"]]
                rows = X.table_rows(tbl)
                jobs.append((z, {"rows": rows[loc["first_row"]: loc["last_row"] + 1]}))
            elif kind == "block":
                jobs.append((z, {"proto": [els[i] for i in loc["els"]], "others": [els[i] for i in loc["others"]]}))
            elif kind == "row_block":
                rows = X.table_rows(els[loc["el"]])
                jobs.append((z, {"proto": rows[loc["proto_row"]], "others": [rows[r] for r in loc["other_rows"]]}))
            elif kind == "textbox":
                tx = txs[loc["tx"]]
                twins = X.textbox_twins(tx)
                ps = [list(t.iterchildren(qn("w:p")))[loc["p"]] for t in twins
                      if len(list(t.iterchildren(qn("w:p")))) > loc["p"]]
                jobs.append((z, {"ps": ps}))
            elif kind in ("remove", "section_unknown"):
                if kind == "section_unknown" and z.get("answer") not in ("remove",):
                    continue
                els_ = loc.get("els", [])
                if "heading" in loc:
                    els_ = [loc["heading"], *els_]
                jobs.append((z, {"els": [els[i] for i in els_]}))
        except (IndexError, KeyError) as e:  # modèle modifié depuis l'analyse
            report["warnings"].append(f"zone {z['key']} introuvable ({e})")

    # 2) Compétences : une seule répartition pour tous les tableaux du modèle
    from .formfill import assign_all, build_groups
    comp_jobs = [(z, t) for z, t in jobs if z["kind"] == "comp_table"]
    for z, t in comp_jobs:
        t["groups"] = build_groups(z["extra"])
    assign_all([t["groups"] for _, t in comp_jobs], view.get("competences", []))

    # 3) Application
    for z, t in jobs:
        kind, field, extra = z["kind"], z.get("field"), z.get("extra", {})
        if kind == "field":
            _fill_field(t["p"], t["extra"], field, extra, z.get("sample") or "", view)
        elif kind == "labels":
            fill_labels(t["p"], extra["labels"], view)
        elif kind == "cell_value":
            _fill_cell_value(t["ps"], field, extra, z.get("sample") or "", view)
        elif kind == "comp_table":
            _fill_comp_table(t["tbl"], extra, view, t.get("groups"))
        elif kind == "list":
            _fill_list(t["items"], field, extra, view)
        elif kind == "table_rows":
            _fill_table_rows(t["rows"], field, extra, view)
        elif kind == "block":
            report["missions"] = _fill_block(t["proto"], t["others"], extra["roles"], view.get("missions", []))
        elif kind == "row_block":
            report["missions"] = _fill_row_block(t["proto"], t["others"], extra["roles"], view.get("missions", []))
        elif kind == "textbox":
            for p in t["ps"]:
                if extra.get("mode") == "clear" or not field:
                    X.set_para_text(p, "")
                else:
                    val = view.get(field) or ""
                    if extra.get("mode") == "after_label" and val:
                        fill_after_label(p, val)
                    else:
                        X.set_para_text(p, val)
        elif kind in ("remove", "section_unknown"):
            for el in t["els"]:
                X.remove(el)

    doc.save(str(out_path))
    return report


def _fill_field(p, extra_els, field, extra, sample, view):
    mode = extra.get("mode", "replace")
    if field == "experience_annees":
        val = years_text(sample, view.get("experience_annees"))
        if val is None:
            safe_remove(p)
            return
        X.set_para_text(p, val)
        return
    val = view.get(field)
    if not val:
        safe_remove(p)
        for el in extra_els:
            safe_remove(el) if el.tag == X.W_P else X.remove(el)
        return
    if mode == "after_label":
        fill_after_label(p, val)
    else:
        X.set_para_text(p, val)
    for el in extra_els:
        safe_remove(el) if el.tag == X.W_P else X.remove(el)


def _list_values(field: str, extra: dict, view: dict) -> list[str]:
    comps = view.get("competences", [])
    if field == "competences_par_categorie":
        return [f"{cat} : {vals}" for cat, vals in competences_by_cat(comps)]
    if field == "competences_flat":
        r = extra.get("rating")
        return [(f"{c['label']} {stars(c.get('niveau'), r)}".strip()) for c in comps]
    if field == "competences_inline":
        return [", ".join(c["label"] for c in comps)]
    from .formfill import list_item_text
    return [list_item_text(field, it, extra) for it in view.get(field, []) or []]


def _fill_list(items: list, field: str, extra: dict, view: dict) -> None:
    values = _list_values(field, extra, view)
    proto = items[0]
    for el in items[1:]:
        safe_remove(el)
    if not values:
        safe_remove(proto)
        return
    anchor = proto
    first_char = X.strip_leading_bullet_char(proto)
    for v in values:
        new = X.clone_after(proto, anchor)
        X.set_para_text(new, f"{first_char} {v}" if first_char else v)
        anchor = new
    X.remove(proto)


def _fill_table_rows(rows: list, field: str, extra: dict, view: dict) -> None:
    proto = rows[0]
    for r in rows[1:]:
        X.remove(r)
    if field == "competences_par_categorie":
        r = extra.get("rating")
        data = [[cat, vals] for cat, vals in competences_by_cat(view.get("competences", []))]
        if r:
            data = [[c["label"], stars(c.get("niveau"), r)] for c in view.get("competences", [])]
    elif field == "competences_flat":
        data = [[c["label"]] for c in view.get("competences", [])]
    elif field == "formations":
        data = [[f.get("annee", ""), f"{f.get('intitule','')} — {f.get('etablissement','')}".strip(" —")] for f in view.get("formations", [])]
    elif field == "langues":
        data = [[x.get("langue", ""), x.get("niveau", "")] for x in view.get("langues", [])]
    else:
        data = [[fmt_list_item(field, it, extra)] for it in view.get(field, [])]
    anchor = proto
    for values in data:
        new = X.clone_after(proto, anchor)
        cells = X.row_cells(new)
        if len(values) > len(cells):
            values = values[: len(cells) - 1] + [" ".join(values[len(cells) - 1:])]
        for tc, v in zip(cells, values + [""] * (len(cells) - len(values))):
            ps = list(tc.iterchildren(qn("w:p")))
            X.set_para_text(ps[0], v)
            for p in ps[1:]:
                X.remove(p)
        anchor = new
    X.remove(proto)


def _fill_block(proto: list, others: list, roles: list[str], missions: list[dict]) -> int:
    for el in others:
        X.remove(el)
    pristine = [copy.deepcopy(el) for el in proto]
    anchor = proto[-1]
    for m in missions:
        clones = []
        for el in pristine:
            new = copy.deepcopy(el)
            anchor.addnext(new)
            anchor = new
            clones.append(new)
        paras = _flat_paras(clones)
        if len(paras) == len(roles):
            fill_mission(paras, roles, m)
    for el in proto:
        X.remove(el)
    return len(missions)


def _fill_row_block(proto, others, roles, missions) -> int:
    for r in others:
        X.remove(r)
    anchor = proto
    for m in missions:
        new = X.clone_after(proto, anchor)
        paras = [p for tc in X.row_cells(new) for p in tc.iterchildren(qn("w:p"))]
        if len(paras) == len(roles):
            fill_mission(paras, roles, m)
        anchor = new
    X.remove(proto)
    return len(missions)
