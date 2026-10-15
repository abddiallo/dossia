"""
Génère des modèles d'ESN réalistes pour les tests (structures volontairement différentes) :
  - nexo_rempli.docx   : dossier REMPLI d'un autre consultant, missions en paragraphes + puces,
                         compétences en tableau, en-tête de section en gras majuscules
  - helix_tableau.docx : missions dans UN tableau (une ligne par mission), styles « Heading »
  - alpha_vide.docx    : modèle VIDE avec placeholders, chaque mission dans son propre tableau
  - orbis_complexe.docx: zone de texte flottante + liste alignée avec des espaces + section inconnue
  - cv_candidat.docx   : un CV (pas un modèle)
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Pt, RGBColor

ORANGE = RGBColor(0xE8, 0x59, 0x0C)
GREEN = RGBColor(0x12, 0xA3, 0x6B)
GREY = RGBColor(0x80, 0x80, 0x80)


def _font(doc, name="Calibri", size=10.5):
    st = doc.styles["Normal"]
    st.font.name = name
    st.font.size = Pt(size)


def section_title(doc, text, color):
    p = doc.add_paragraph()
    r = p.add_run(text.upper())
    r.bold = True
    r.font.color.rgb = color
    r.font.size = Pt(12)
    return p


def shade(cell, hex_color):
    cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{hex_color}"/>'))


def nexo_rempli(path: Path):
    doc = Document()
    _font(doc)
    hp = doc.sections[0].header.paragraphs[0]
    hp.text = "NEXO INGÉNIERIE — Dossier de compétences"
    p = doc.add_paragraph()
    r = p.add_run("NEXO")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), GREEN
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run("J. M.")
    r.bold, r.font.size = True, Pt(16)
    p = doc.add_paragraph()
    r = p.add_run("Architecte logiciel Java / Spring")
    r.bold = True
    p = doc.add_paragraph()
    r = p.add_run("12 ans d'expérience")
    r.font.color.rgb = GREY
    p = doc.add_paragraph("Disponibilité : sous 1 mois")

    section_title(doc, "Synthèse", GREEN)
    doc.add_paragraph("Architecte expérimenté, spécialisé dans les plateformes bancaires à forte volumétrie. "
                      "Pilotage d'équipes de 6 à 10 développeurs.")
    doc.add_paragraph("Habitué aux environnements réglementés et aux démarches DevOps.")

    section_title(doc, "Compétences techniques", GREEN)
    t = doc.add_table(rows=4, cols=2)
    t.style = "Table Grid"
    rows = [("Domaine", "Compétences"), ("Langages", "Java, Kotlin, SQL"),
            ("Frameworks", "Spring Boot, Hibernate"), ("Outils", "Docker, Kubernetes, GitLab")]
    for i, (a, b) in enumerate(rows):
        t.cell(i, 0).text, t.cell(i, 1).text = a, b
        if i == 0:
            for c in t.rows[0].cells:
                c.paragraphs[0].runs[0].bold = True
                shade(c, "DDEEE6")

    section_title(doc, "Expériences professionnelles", GREEN)
    missions = [
        ("Banque de détail", "01/2022 – 06/2025", "Architecte technique",
         "Refonte de la plateforme de paiement.", ["Conception de l'architecture microservices", "Encadrement de 8 développeurs"],
         "Java 17, Spring Boot, Kafka, Kubernetes"),
        ("Assureur", "03/2019 – 12/2021", "Lead développeur",
         "Modernisation du SI sinistres.", ["Migration vers Spring Boot", "Mise en place de la CI/CD", "Revue de code"],
         "Java 11, Spring, Jenkins, Oracle"),
        ("Opérateur télécom", "2016 – 2019", "Développeur Java",
         "Outils de facturation.", ["Développement de batchs", "Optimisation SQL"],
         "Java 8, Oracle, Linux"),
    ]
    for client, dates, poste, ctx, bullets, env in missions:
        p = doc.add_paragraph()
        r1 = p.add_run(client)
        r1.bold = True
        p.add_run(" · ")
        r3 = p.add_run(dates)
        r3.font.color.rgb = GREY
        p = doc.add_paragraph()
        r = p.add_run(poste)
        r.bold, r.italic = True, True
        doc.add_paragraph(ctx)
        for b in bullets:
            doc.add_paragraph(b, style="List Bullet")
        p = doc.add_paragraph()
        r = p.add_run("Environnement : ")
        r.bold = True
        p.add_run(env)
        doc.add_paragraph()

    section_title(doc, "Formation", GREEN)
    doc.add_paragraph("Diplôme d'ingénieur informatique — INSA Lyon (2012)")
    doc.add_paragraph("Baccalauréat S (2007)")

    section_title(doc, "Langues", GREEN)
    doc.add_paragraph("Anglais : courant")
    doc.save(path)


def helix_tableau(path: Path):
    doc = Document()
    _font(doc, "Arial", 10)
    doc.add_heading("HELIX TECH", level=0)
    t = doc.add_table(rows=1, cols=2)
    a, b = t.rows[0].cells
    a.text = "P. L."
    a.paragraphs[0].runs[0].bold = True
    a.add_paragraph("Consultant DevOps senior")
    b.text = "8 ans d'expérience"
    b.add_paragraph("Mobilité : Île-de-France")
    doc.add_heading("Profil", level=1)
    doc.add_paragraph("Consultant DevOps orienté automatisation et fiabilité des plateformes cloud.")
    doc.add_heading("Compétences", level=1)
    doc.add_paragraph("Cloud : AWS, Azure", style="List Bullet")
    doc.add_paragraph("Conteneurs : Docker, Kubernetes", style="List Bullet")
    doc.add_paragraph("IaC : Terraform, Ansible", style="List Bullet")
    doc.add_heading("Missions", level=1)
    t = doc.add_table(rows=4, cols=2)
    t.style = "Table Grid"
    t.cell(0, 0).text, t.cell(0, 1).text = "Période / Client", "Mission"
    data = [("Énergéticien", "2022 – aujourd'hui", "Ingénieur DevOps", ["Industrialisation des déploiements", "Supervision Prometheus"]),
            ("Banque", "2019 – 2022", "Administrateur systèmes", ["Automatisation Ansible", "Migration RHEL 8"]),
            ("Éditeur SaaS", "2017 – 2019", "Ingénieur cloud", ["Mise en place AWS"])]
    for i, (client, dates, poste, bl) in enumerate(data, start=1):
        c0, c1 = t.cell(i, 0), t.cell(i, 1)
        c0.text = client
        c0.paragraphs[0].runs[0].bold = True
        c0.add_paragraph(dates)
        c1.text = poste
        c1.paragraphs[0].runs[0].bold = True
        for x in bl:
            c1.add_paragraph(x, style="List Bullet")
    doc.add_heading("Certifications", level=1)
    doc.add_paragraph("AWS Solutions Architect Associate (2021)")
    doc.add_paragraph("CKA – Certified Kubernetes Administrator (2022)")
    doc.save(path)


def alpha_vide(path: Path):
    doc = Document()
    _font(doc, "Calibri", 11)
    p = doc.add_paragraph()
    r = p.add_run("ALPHA CONSEIL")
    r.bold, r.font.color.rgb = True, RGBColor(0x3D, 0x6D, 0xFD)
    doc.add_paragraph("[Prénom NOM]")
    doc.add_paragraph("[Titre du poste]")
    doc.add_paragraph("[X] ans d'expérience")
    doc.add_heading("Résumé", level=1)
    doc.add_paragraph("[Résumé du profil en 4 à 5 lignes]")
    doc.add_heading("Compétences clés", level=1)
    doc.add_paragraph("[Compétence 1, compétence 2, compétence 3…]")
    doc.add_heading("Expériences", level=1)
    t = doc.add_table(rows=2, cols=2)
    t.style = "Table Grid"
    t.cell(0, 0).text = "[Client]"
    t.cell(0, 1).text = "MM/AAAA – MM/AAAA"
    t.cell(1, 0).text = "[Poste]"
    c = t.cell(1, 1)
    c.text = "[Contexte de la mission]"
    c.add_paragraph("[Réalisation]", style="List Bullet")
    c.add_paragraph("Environnement : [technologies]")
    doc.add_paragraph()
    doc.add_heading("Formations", level=1)
    doc.add_paragraph("[Diplôme — École (année)]")
    doc.save(path)


def orbis_complexe(path: Path):
    doc = Document()
    _font(doc)
    p = doc.add_paragraph()
    r = p.add_run("ORBIS")
    r.bold = True
    doc.add_paragraph("P. L.")
    doc.add_paragraph("Consultant DevOps")
    # zone de texte flottante (DrawingML) « Disponibilité / Mobilité »
    anchor_xml = f'''
<w:r {nsdecls("w", "wp", "a")} xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
     xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
 <mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="1" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">
  <wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="margin"><wp:posOffset>3600000</wp:posOffset></wp:positionH>
  <wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV><wp:extent cx="1800000" cy="600000"/>
  <wp:wrapNone/><wp:docPr id="10" name="Zone 10"/><wp:cNvGraphicFramePr/>
  <a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"><wps:wsp><wps:cNvSpPr txBox="1"/>
   <wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1800000" cy="600000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></wps:spPr>
   <wps:txbx><w:txbxContent><w:p><w:r><w:t>Disponibilité : Immédiate</w:t></w:r></w:p><w:p><w:r><w:t>Mobilité : IDF</w:t></w:r></w:p></w:txbxContent></wps:txbx>
   <wps:bodyPr/></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>
  <mc:Fallback><w:pict><w:txbxContent><w:p><w:r><w:t>Disponibilité : Immédiate</w:t></w:r></w:p><w:p><w:r><w:t>Mobilité : IDF</w:t></w:r></w:p></w:txbxContent></w:pict></mc:Fallback></mc:AlternateContent></w:r>'''
    holder = doc.add_paragraph()
    holder._p.append(parse_xml(anchor_xml))
    section_title(doc, "Profil", ORANGE)
    doc.add_paragraph("Ingénieur DevOps avec une forte culture de l'automatisation.")
    section_title(doc, "Outils", ORANGE)
    doc.add_paragraph("Docker        Terraform        GitLab CI")
    doc.add_paragraph("Ansible       AWS              Kubernetes")
    section_title(doc, "Missions", ORANGE)
    doc.add_paragraph("Énergéticien · 2021 – 2024")
    doc.add_paragraph("Ingénieur DevOps")
    doc.add_paragraph("Mise en place de pipelines.", style="List Bullet")
    section_title(doc, "Centres d'intérêt", ORANGE)
    doc.add_paragraph("Trail, photographie")
    doc.save(path)


def cv_candidat(path: Path):
    doc = Document()
    _font(doc)
    doc.add_paragraph("Abdoulaye DIALLO")
    doc.add_paragraph("Développeur C++ / Qt / QML")
    doc.add_paragraph("Toulouse · abdoulaye@example.com")
    doc.add_heading("Profil", level=1)
    doc.add_paragraph("Développeur C++/Qt/QML avec 8 ans d'expérience sur des IHM critiques dans l'aéronautique, "
                      "l'énergie et la navigation aérienne.")
    doc.add_heading("Compétences", level=1)
    doc.add_paragraph("Langages : C++17, QML, Python, Java")
    doc.add_paragraph("Frameworks : Qt 5, Qt 6, Eclipse RCP")
    doc.add_paragraph("Outils : Git, Jenkins, CMake, Linux")
    doc.add_heading("Expériences professionnelles", level=1)
    doc.add_paragraph("Capgemini — Airbus (Toulouse) · 01/2023 – 06/2024")
    doc.add_paragraph("Développeur IHM")
    doc.add_paragraph("Conception d'écrans cockpit en QML", style="List Bullet")
    doc.add_paragraph("Migration Qt 5 vers Qt 6", style="List Bullet")
    doc.add_paragraph("Environnement : C++17, Qt 6, QML, Linux")
    doc.add_paragraph("Capgemini — EDF (Lyon) · 09/2021 – 12/2022")
    doc.add_paragraph("Développeur C++/Qt")
    doc.add_paragraph("Développement d'outils de supervision temps réel", style="List Bullet")
    doc.add_paragraph("Environnement : C++17, Qt 5, CMake")
    doc.add_paragraph("Capgemini — DSNA (Toulouse) · 2020 – 2021")
    doc.add_paragraph("Développeur Java / Eclipse RCP")
    doc.add_paragraph("Évolution d'une application de gestion de l'espace aérien", style="List Bullet")
    doc.add_paragraph("Environnement : Java, Eclipse RCP")
    doc.add_heading("Formation", level=1)
    doc.add_paragraph("Master Informatique et Systèmes d'Information — EPSI Toulouse (2019)")
    doc.add_paragraph("Licence Informatique — Université d'Angers (2017)")
    doc.add_heading("Langues", level=1)
    doc.add_paragraph("Anglais : professionnel")
    doc.add_paragraph("Peul : langue maternelle")
    doc.save(path)


def formulaire(path: Path):
    """Modèle « formulaire » de synthèse reprenant les mécanismes de vrais modèles d'ESN :
    bandeaux de section en tableau (icône + texte), en-tête « TRIGRAMME / Fonction », libellés en ligne,
    tableau libellé/valeur, grille de compétences avec niveaux, missions = un tableau par mission."""
    doc = Document()
    _font(doc)
    hdr = doc.sections[0].header
    hdr.paragraphs[0].text = "ESN CV"
    hdr.add_paragraph("TRIGRAMME")
    hdr.add_paragraph("Fonction")

    def banner(text):
        t = doc.add_table(rows=1, cols=2)
        t.cell(0, 1).text = text
        doc.add_paragraph()

    doc.add_paragraph("Nom:\tMobilité géographique:")
    doc.add_paragraph("Date de disponibilité:")
    banner("Profil")
    t = doc.add_table(rows=1, cols=1)
    t.cell(0, 0).text = "Synthèse des compétences et savoir-faire."
    t.cell(0, 0).add_paragraph("Résumé de parcours")
    doc.add_paragraph()
    t = doc.add_table(rows=4, cols=3)
    for r, (lab, vals) in enumerate([("Expérience", ["X années"]), ("Certifications", ["YYYY : titre"]),
                                      ("Langues", ["YY (langue maternelle)"]), ("Localisation", ["Ville - Pays"])]):
        t.cell(r, 1).text = lab
        t.cell(r, 2).text = vals[0]
    banner("Compétences techniques et méthodologiques")
    doc.add_paragraph("Niveaux : 1- Connaissances | 2- Maîtrise | 3- Expert")
    t = doc.add_table(rows=5, cols=5)
    t.style = "Table Grid"
    for j, h in enumerate(["", "Domaine", "Niv", "Domaine", "Niv"]):
        t.cell(0, j).text = h
    t.cell(1, 0).text = "Langages et systèmes"
    t.cell(3, 0).text = "Outils et applications"
    banner("Expériences professionnelles")
    for _ in range(2):
        t = doc.add_table(rows=5, cols=2)
        t.style = "Table Grid"
        t.cell(0, 0).text = "Sujets - CLIENT"
        t.cell(1, 1).text = "MM/YYYY – MM/YYYY (ou … si toujours en cours)"
        t.cell(2, 0).text, t.cell(2, 1).text = "Fonction", "Lorem ipsum"
        t.cell(3, 0).text = "Mission(s) et réalisations"
        c = t.cell(3, 1)
        c.text = "Activité 1"
        c.paragraphs[0].style = doc.styles["List Bullet"]
        c.add_paragraph("Activité 2", style="List Bullet")
        t.cell(4, 0).text, t.cell(4, 1).text = "Environnement", "Rappel des outils propres à cette mission"
        doc.add_paragraph()
    doc.save(path)


def build_all(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "nexo": out / "nexo_rempli.docx", "helix": out / "helix_tableau.docx",
        "alpha": out / "alpha_vide.docx", "orbis": out / "orbis_complexe.docx", "cv": out / "cv_candidat.docx",
        "formulaire": out / "formulaire.docx",
    }
    nexo_rempli(files["nexo"]); helix_tableau(files["helix"]); alpha_vide(files["alpha"])
    orbis_complexe(files["orbis"]); cv_candidat(files["cv"]); formulaire(files["formulaire"])
    return files


if __name__ == "__main__":
    print(build_all(Path(sys.argv[1] if len(sys.argv) > 1 else "out")))
