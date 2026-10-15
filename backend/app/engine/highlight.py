"""Copie « surlignée » d'un dossier pour l'aperçu : les compétences demandées par l'offre apparaissent en jaune.

Le fichier livré n'est jamais modifié : seule une copie sert à produire les aperçus « Montrer les adaptations ».
"""
from __future__ import annotations

import copy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .match import skill_spans
from .skills import family


def _split_run(r, spans: list[tuple[int, int]]):
    """Découpe le run r en morceaux et surligne ceux qui correspondent aux intervalles donnés."""
    t = r.find(qn("w:t"))
    text = t.text or ""
    pieces, last = [], 0
    for a, b in spans:
        if a > last:
            pieces.append((text[last:a], False))
        pieces.append((text[a:b], True))
        last = b
    if last < len(text):
        pieces.append((text[last:], False))
    parent = r.getparent()
    idx = parent.index(r)
    for k, (chunk, hl) in enumerate(pieces):
        nr = copy.deepcopy(r)
        for child in list(nr):
            if child.tag not in (qn("w:rPr"),):
                nr.remove(child)
        nt = OxmlElement("w:t")
        nt.set(qn("xml:space"), "preserve")
        nt.text = chunk
        nr.append(nt)
        if hl:
            rpr = nr.find(qn("w:rPr"))
            if rpr is None:
                rpr = OxmlElement("w:rPr")
                nr.insert(0, rpr)
            h = OxmlElement("w:highlight")
            h.set(qn("w:val"), "yellow")
            rpr.append(h)
        parent.insert(idx + k, nr)
    parent.remove(r)


def highlight_copy(src: str | Path, dest: str | Path, skills: list[str]) -> int:
    """Écrit dest avec les compétences `skills` (et leurs variantes) surlignées. Renvoie le nombre de passages surlignés."""
    want: set[str] = set()
    for s in skills:
        want |= family(s)
    doc = Document(str(src))
    n = 0
    body = doc.element.body
    for r in list(body.iter(qn("w:r"))):
        ts = r.findall(qn("w:t"))
        if len(ts) != 1 or not (ts[0].text or "").strip():
            continue
        spans = [(s["start"], s["end"]) for s in skill_spans(ts[0].text) if s["label"] in want]
        if spans:
            _split_run(r, spans)
            n += len(spans)
    doc.save(str(dest))
    return n
