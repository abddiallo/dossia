"""Primitives bas niveau sur le XML Word (python-docx + lxml)."""
from __future__ import annotations

import copy
from typing import Iterator

from docx.document import Document as _Doc
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

W_P, W_TBL, W_R, W_T = qn("w:p"), qn("w:tbl"), qn("w:r"), qn("w:t")
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
MC_ALT, MC_FALLBACK = MC + "AlternateContent", MC + "Fallback"


def body_elements(doc: _Doc) -> list:
    """Enfants directs du corps (paragraphes et tableaux), hors sectPr."""
    return [el for el in doc.element.body.iterchildren() if el.tag in (W_P, W_TBL)]


def para_text(p_el) -> str:
    """Texte visible d'un w:p, y compris liens hypertexte, hors zones de texte imbriquées."""
    out = []
    for node in p_el.iter():
        if node.tag == qn("w:txbxContent"):
            continue
        if node.tag == W_T and not _inside_txbx(node, p_el):
            out.append(node.text or "")
        elif node.tag == qn("w:tab") and not _inside_txbx(node, p_el):
            out.append("\t")
        elif node.tag in (qn("w:br"), qn("w:cr")) and not _inside_txbx(node, p_el):
            out.append("\n")
    return "".join(out)


def _inside_txbx(node, stop) -> bool:
    n = node.getparent()
    while n is not None and n is not stop:
        if n.tag == qn("w:txbxContent"):
            return True
        n = n.getparent()
    return False


def table_paragraphs(tbl_el) -> list:
    """Paragraphes d'un tableau dans l'ordre de lecture (chaque cellule w:tc est un élément distinct)."""
    out = []
    for tc in tbl_el.iter(qn("w:tc")):
        out.extend(tc.iterchildren(qn("w:p")))
    return out


def element_paragraphs(el) -> list:
    return [el] if el.tag == W_P else table_paragraphs(el)


def element_text(el) -> str:
    return "\n".join(para_text(p) for p in element_paragraphs(el))


def table_rows(tbl_el) -> list:
    return list(tbl_el.iterchildren(qn("w:tr")))


def row_cells(tr) -> list:
    return list(tr.iterchildren(qn("w:tc")))


def cell_text(tc) -> str:
    return "\n".join(para_text(p) for p in tc.iterchildren(qn("w:p")))


def style_name(p_el, doc: _Doc) -> str:
    ppr = p_el.find(qn("w:pPr"))
    if ppr is None:
        return "Normal"
    ps = ppr.find(qn("w:pStyle"))
    if ps is None:
        return "Normal"
    sid = ps.get(qn("w:val"))
    try:
        for s in doc.styles:
            if s.style_id == sid:
                return s.name or sid
    except Exception:  # noqa: BLE001
        pass
    return sid or "Normal"


def is_list_paragraph(p_el, doc: _Doc) -> bool:
    ppr = p_el.find(qn("w:pPr"))
    if ppr is not None and ppr.find(qn("w:numPr")) is not None:
        return True
    name = style_name(p_el, doc).lower()
    if "list" in name or "liste" in name or "puce" in name or "bullet" in name:
        return True
    t = para_text(p_el).lstrip()
    return t[:1] in ("•", "-", "–", "▪", "◦", "·", "*", "➢", "►", "✓")


def runs(p_el) -> list:
    """w:r directs ou dans des liens hypertexte (pas dans les zones de texte)."""
    out = []
    for child in p_el.iterchildren():
        if child.tag == W_R:
            out.append(child)
        elif child.tag in (qn("w:hyperlink"), qn("w:smartTag"), qn("w:ins")):
            out.extend(r for r in child.iter(W_R))
    return [r for r in out if not _has_drawing(r)]


def _has_drawing(r) -> bool:
    return r.find(qn("w:drawing")) is not None or r.find(qn("w:pict")) is not None or \
        r.find(MC_ALT) is not None


def run_text(r) -> str:
    return "".join(
        (n.text or "") if n.tag == W_T else ("\t" if n.tag == qn("w:tab") else ("\n" if n.tag == qn("w:br") else ""))
        for n in r.iterchildren()
    )


def run_is_bold(r) -> bool:
    rpr = r.find(qn("w:rPr"))
    if rpr is None:
        return False
    b = rpr.find(qn("w:b"))
    return b is not None and b.get(qn("w:val")) not in ("0", "false")


def para_is_bold(p_el) -> bool:
    rs = [r for r in runs(p_el) if run_text(r).strip()]
    return bool(rs) and all(run_is_bold(r) for r in rs)


def set_run_text(r, text: str) -> None:
    """Remplace le texte d'un run en conservant sa mise en forme (rPr). Gère les retours à la ligne."""
    for child in list(r):
        if child.tag != qn("w:rPr"):
            r.remove(child)
    lines = (text or "").split("\n")
    for i, line in enumerate(lines):
        if i:
            r.append(r.makeelement(qn("w:br"), {}))
        t = r.makeelement(W_T, {})
        t.text = line
        if line != line.strip():
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)


def set_para_text(p_el, text: str) -> None:
    """Remplace le texte du paragraphe en gardant la mise en forme du premier run qui porte du texte visible
    (et non d'une espace ou tabulation de mise en page). Les runs de tabulation sont conservés."""
    rs = runs(p_el)
    if not rs:
        r = p_el.makeelement(W_R, {})
        p_el.append(r)
        rs = [r]
    visible = [r for r in rs if run_text(r).strip()]
    target = visible[0] if visible else rs[0]
    set_run_text(target, text)
    for r in rs:
        if r is target:
            continue
        layout = r.find(qn("w:tab")) is not None and not run_text(r).replace("\t", "").strip()
        if not layout:          # seuls les runs de pure tabulation (mise en page) sont conservés
            r.getparent().remove(r)


def strip_leading_bullet_char(p_el) -> str:
    t = para_text(p_el)
    s = t.lstrip()
    if s[:1] in ("•", "-", "–", "▪", "◦", "·", "*", "➢", "►", "✓"):
        return s[0]
    return ""


def clone_after(el, anchor):
    new = copy.deepcopy(el)
    anchor.addnext(new)
    return new


def remove(el) -> None:
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def is_empty_para(el) -> bool:
    return el.tag == W_P and not para_text(el).strip() and not _contains_drawing(el)


def _contains_drawing(el) -> bool:
    return any(True for _ in el.iter(qn("w:drawing"))) or any(True for _ in el.iter(qn("w:pict")))


def textboxes(doc: _Doc) -> list:
    """Zones de texte du corps (hors copies VML de repli)."""
    out = []
    for tx in doc.element.body.iter(qn("w:txbxContent")):
        anc, fallback = tx.getparent(), False
        while anc is not None:
            if anc.tag == MC_FALLBACK:
                fallback = True
                break
            anc = anc.getparent()
        if not fallback:
            out.append(tx)
    return out


def textbox_twins(tx) -> list:
    """La zone de texte et sa copie VML éventuelle (mc:AlternateContent)."""
    anc = tx.getparent()
    while anc is not None and anc.tag != MC_ALT:
        anc = anc.getparent()
    if anc is None:
        return [tx]
    return list(anc.iter(qn("w:txbxContent")))


def iter_all_paragraphs(doc: _Doc) -> Iterator:
    for el in body_elements(doc):
        yield from element_paragraphs(el)


def wrap_paragraph(p_el, doc) -> Paragraph:
    return Paragraph(p_el, doc)


def wrap_table(tbl_el, doc) -> Table:
    return Table(tbl_el, doc)
