"""Conversion PDF (LibreOffice), comptage des pages et aperçus PNG (pdftoppm)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pdfplumber

SOFFICE = os.environ.get("SOFFICE_BIN") or shutil.which("soffice") or shutil.which("libreoffice") or "soffice"


def to_pdf(docx_path: str | Path, out_dir: str | Path | None = None, timeout: int = 90) -> Path:
    docx_path = Path(docx_path)
    out_dir = Path(out_dir or docx_path.parent)
    # profil LibreOffice isolé : permet plusieurs conversions en parallèle (un worker = un profil)
    with tempfile.TemporaryDirectory(prefix="lo-") as profile:
        cmd = [SOFFICE, f"-env:UserInstallation=file://{profile}", "--headless", "--norestore",
               "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)]
        subprocess.run(cmd, check=True, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pdf = out_dir / (docx_path.stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError(f"Conversion PDF échouée pour {docx_path.name}")
    return pdf


def page_count(pdf_path: str | Path) -> int:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return len(pdf.pages)


def previews(pdf_path: str | Path, out_dir: str | Path, dpi: int = 70, max_pages: int = 6) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", str(max_pages), str(pdf_path), str(prefix)],
                   check=True, timeout=60)
    return sorted(out_dir.glob("page-*.png"))


def pdf_text(pdf_path: str | Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)
