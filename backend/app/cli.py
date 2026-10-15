"""
Diagnostic d'un modèle d'ESN, sans base de données :

    python -m app.cli analyse "Dossier de compétences VIVERIS.docx"
    python -m app.cli analyse modele.docx --cv mon_cv.pdf      # génère aussi un dossier d'essai

Affiche les sections et zones détectées, le statut et la durée de chaque étape.
"""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from .engine.analyzer import analyze
from .engine.render import page_count, to_pdf


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyse", help="analyser un modèle .docx")
    a.add_argument("modele")
    a.add_argument("--cv", help="CV pour générer un dossier d'essai")
    args = ap.parse_args()

    t0 = time.monotonic()
    spec = analyze(args.modele)
    t1 = time.monotonic()
    print(f"\nAnalyse : {t1 - t0:.1f} s · type {spec['kind']} · statut {spec['status']} · "
          f"reconnaissance {spec['recognition_score']:.0%} · ESN « {spec['esn_name_guess']} »")
    if spec["complex_notes"]:
        print("Points complexes :", ", ".join(spec["complex_notes"]))
    print("\nSections :", " | ".join(f"{s['title']} → {s['type'] or '?'}" for s in spec["sections"]) or "aucune")
    print("\nZones :")
    for z in spec["zones"]:
        roles = z.get("extra", {}).get("roles")
        print(f"  [{z['status']:9}] {z['kind']:15} {str(z['field']):26} {z['confidence']:.0%}  « {(z.get('sample') or '')[:60]} »"
              + (f"\n{'':40}rôles : {roles}" if roles else ""))
    with tempfile.TemporaryDirectory() as tmp:
        t2 = time.monotonic()
        pages = page_count(to_pdf(args.modele, tmp))
        print(f"\nConversion PDF (LibreOffice) : {time.monotonic() - t2:.1f} s · {pages} page(s)")
        if args.cv:
            from .engine.cv_extract import extract_profile
            from .engine.generate import generate
            prof, _, method = extract_profile(args.cv)
            out = Path(args.modele).with_name(Path(args.modele).stem + "_ESSAI")
            spec["constraints"]["max_pages"] = pages if spec["kind"] == "filled_example" else None
            t3 = time.monotonic()
            r = generate(prof, args.modele, spec, {}, None, out, basename="dossier_essai", make_previews=False)
            print(f"\nDossier d'essai ({method}) : {time.monotonic() - t3:.1f} s · {r['pages']} page(s) → {r['docx']}")
            for c in r["fidelity"]["checks"]:
                print(f"  {'✓' if c['ok'] else '!'} {c['label']}")


if __name__ == "__main__":
    main()
