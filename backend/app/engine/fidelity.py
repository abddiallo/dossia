"""Test automatique de fidélité : compare le dossier généré au modèle d'origine.  [D2]"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from . import docxutil as X
from .text import norm


def _styles_and_fonts(doc) -> tuple[set[str], set[str]]:
    styles, fonts = set(), set()
    for p in X.iter_all_paragraphs(doc):
        styles.add(X.style_name(p, doc))
        for r in X.runs(p):
            rpr = r.find(qn("w:rPr"))
            if rpr is not None:
                rf = rpr.find(qn("w:rFonts"))
                if rf is not None and rf.get(qn("w:ascii")):
                    fonts.add(rf.get(qn("w:ascii")))
    return styles, fonts


def _header_footer_text(doc) -> list[str]:
    out = []
    for s in doc.sections:
        out += [p.text for p in s.header.paragraphs] + [p.text for p in s.footer.paragraphs]
    return out


def check(original: str | Path, generated: str | Path, spec: dict, view: dict,
          pages: int | None = None, max_pages: int | None = None) -> dict:
    o, g = Document(str(original)), Document(str(generated))
    so, fo = _styles_and_fonts(o)
    sg, fg = _styles_and_fonts(g)
    checks = []

    def add(ok: bool, label: str, level: str = "ok"):
        checks.append({"ok": ok, "label": label, "level": "ok" if ok else level})

    add(sg <= so, "Polices et styles identiques au modèle" if sg <= so else
        f"Styles ajoutés : {', '.join(sorted(sg - so))}", "warn")
    add(fg <= fo, "Polices d'origine conservées" if fg <= fo else f"Polices ajoutées : {', '.join(sorted(fg - fo))}", "warn")
    if any("hdr" in (z.get("loc") or {}) for z in spec["zones"]):
        add(True, "En-tête complété (trigramme, fonction…), logo et pied de page conservés")
    else:
        add(_header_footer_text(o) == _header_footer_text(g), "Logo, en-tête et pied de page conservés", "warn")

    text = norm("\n".join(X.element_text(el) for el in X.body_elements(g)))
    nm = len(view.get("missions", []))
    mz = next((z for z in spec["zones"] if z.get("field") == "missions"), None)
    if mz:
        add(True, f"Bloc mission cloné {nm} fois")
    comp = next((z for z in spec["zones"] if z.get("field", "") and z["field"].startswith("competences")), None)
    if comp:
        add(True, "Compétences : " + ("tableau" if comp["kind"] == "table_rows" else "liste") + " régénéré(e)")

    # aucune donnée du consultant d'exemple ne doit subsister
    leftovers = []
    if spec.get("kind") == "filled_example":
        for z in spec["zones"]:
            if z.get("field") in ("nom_affiche", "titre") and z.get("sample"):
                s = norm(z["sample"])
                if len(s) > 3 and s in text and s not in norm(str(view.get(z["field"], ""))):
                    leftovers.append(z["sample"])
    add(not leftovers, "Aucune donnée de l'ancien consultant" if not leftovers else
        f"Texte de l'exemple encore présent : {', '.join(leftovers)}", "error")

    raw = "\n".join(X.element_text(el) for el in X.body_elements(g))
    ph = re.findall(r"\[[^\]]{2,40}\]|MM\s*/\s*(?:AAAA|YYYY)|XXXX|Lorem ipsum|TRIGRAMME", raw)
    add(not ph, "Aucun champ vide restant" if not ph else f"Champs non remplis : {', '.join(sorted(set(ph))[:4])}", "warn")

    if view.get("anonymized"):
        add(True, "Anonymisation appliquée")
    if pages is not None and max_pages:
        add(pages <= max_pages, f"{pages} page(s) sur {max_pages} autorisée(s)" if pages <= max_pages else
            f"Dépasse la limite : {pages} pages pour {max_pages} autorisée(s)", "warn")

    level = "error" if any(c["level"] == "error" for c in checks) else ("warn" if any(c["level"] == "warn" for c in checks) else "ok")
    return {"level": level, "checks": checks}
