"""
Génération complète d'un dossier (sans base de données) :
profil + modèle + options → .docx, .pdf, aperçus, segments tracés, contrôle de fidélité.
Respecte la limite de pages selon la règle choisie pour le modèle.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import adapter, fidelity
from .filler import fill
from .render import page_count, previews, to_pdf


def generate(profile: dict, template_path: str | Path, spec: dict, options: dict, posting: dict | None,
             workdir: str | Path, basename: str = "dossier", overflow_policy: str = "keep_recent",
             make_previews: bool = True) -> dict:
    t0 = time.monotonic()
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    opts = dict(options)
    max_pages = opts.get("max_pages") or spec.get("constraints", {}).get("max_pages")
    if overflow_policy == "allow_extra_page" and max_pages and not opts.get("max_pages"):
        max_pages += 1
    docx_out, pdf_out = workdir / f"{basename}.docx", workdir / f"{basename}.pdf"
    adjustments: list[str] = []

    for _ in range(8):
        built = adapter.build(profile, spec, opts, posting)
        fill(template_path, spec, built["view"], docx_out)
        pdf = to_pdf(docx_out, workdir)
        pages = page_count(pdf)
        if not max_pages or pages <= max_pages:
            break
        n_missions = len(built["view"]["missions"])
        if overflow_policy == "shorten" and (opts.get("realisations_max") or 99) > 1:
            current = opts.get("realisations_max") or max((len(m["realisations"]) for m in built["view"]["missions"]), default=1)
            opts["realisations_max"] = max(1, current - 1)
            adjustments.append(f"réalisations limitées à {opts['realisations_max']} par mission")
        elif n_missions > 1:
            opts["max_missions"] = n_missions - 1
            opts.setdefault("drop_strategy", "recent" if overflow_policy != "shorten" else "relevant")
            adjustments.append(f"{n_missions - 1} mission(s) conservée(s)")
        else:
            break
    pdf_out = pdf if pdf == pdf_out else pdf
    report = fidelity.check(template_path, docx_out, spec, built["view"], pages=pages, max_pages=max_pages)
    pngs = previews(pdf_out, workdir / "pages") if make_previews else []
    hl_pngs: list[Path] = []
    if make_previews and posting and posting.get("skills") and opts.get("adapt", True):
        try:  # aperçu « Montrer les adaptations » : copie surlignée, le fichier livré reste intact
            from .highlight import highlight_copy
            hl_dir = workdir / "hl"
            hl_dir.mkdir(exist_ok=True)
            hl_docx = hl_dir / f"{basename}.docx"
            if highlight_copy(docx_out, hl_docx, posting["skills"]):
                hl_pngs = previews(to_pdf(hl_docx, hl_dir), hl_dir / "pages")
        except Exception:  # noqa: BLE001 — l'aperçu surligné est un plus, jamais bloquant
            hl_pngs = []
    return {
        "docx": docx_out, "pdf": pdf_out, "pages": pages, "max_pages": max_pages, "previews": pngs, "highlight_previews": hl_pngs,
        "view": built["view"], "segments": built["segments"], "stats": built["stats"],
        "question": built["question"], "fidelity": report, "adjustments": adjustments,
        "effective_options": opts, "generation_ms": int((time.monotonic() - t0) * 1000),
    }
