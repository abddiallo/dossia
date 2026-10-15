"""
Modèles « formulaire » : libellés suivis d'une valeur (« Nom : », cellule « Réalisations » + cellule
valeur, « Langue1 : Niveau »…). Vocabulaire partagé par l'analyse et le remplissage.
Validé sur des modèles réels d'ESN de structures très différentes (paragraphes, tableaux, en-têtes).
"""
from __future__ import annotations

import re

from .text import norm

# Champs dont la valeur est une liste (une ligne / puce par élément)
LIST_FIELDS = {"certifications", "formations", "langues", "competences_top", "secteurs", "formations_certifications"}

IDENTITY_LABELS = [
    (r"^(nom et prenom|prenom et nom|nom prenom|prenom nom|consultant|candidat|nom complet)$", "nom_complet"),
    (r"^prenom$", "prenom"),
    (r"^(nom|nom de famille)$", "nom"),
    (r"^(initiales|trigramme)$", "trigramme"),
    (r"^(titre|intitule( du poste)?|poste( recherche| vise| souhaite)?|fonction|profil recherche)$", "titre"),
    (r"^(annees? d.?experience|experience|experiences?|nombre d.?annees d.?experience|seniorite)$", "experience_annees"),
    (r"^(date de )?disponibilite$", "disponibilite"),
    (r"^mobilite( geographique)?$", "mobilite"),
    (r"^(ville|localisation|lieu de residence|residence|lieu)$", "ville"),
    (r"^(certifications?|certificats?)$", "certifications"),
    (r"^(formations?|diplomes?|etudes|cursus|formation academique|academic training)$", "formations"),
    (r"^(langues?|langues etrangeres|languages?)$", "langues"),
    (r"^(principales competences|competences cles|competences principales|points forts)$", "competences_top"),
    (r"^(secteurs?( d.?activite)?|line of business|domaines? d.?intervention)$", "secteurs"),
]

MISSION_LABELS = [
    (r"^(nom de la societe|societe|entreprise|client|nom du client|employeur|structure|company|"
     r"sujets? ?-? ?client|projet ?-? ?client)$", "client"),
    (r"^(poste|poste occupe|fonction|role|intitule du poste|titre du poste|job title|job description)$", "poste"),
    (r"^(dates?|periode|duree)$", "dates"),
    (r"^(contexte|contexte de la mission|presentation du projet|projets?|description|objectifs?|"
     r"descriptif|presentation|context)$", "contexte"),
    (r"^(realisations?|responsabilites|taches|activites|actions|travaux realises|missions realisees|resultats|"
     r"missions? et realisations|achievements)$", "realisations"),
    (r"^(environnement( technique| technologique)?|technologies|outils( utilises)?|stack|"
     r"competences mises en oeuvre|technical environment)$", "env"),
    (r"^(lieu|localisation|ville)$", "lieu"),
]

# libellés de lignes de compétences → catégories du profil
COMPETENCE_LABELS = [
    (r"^(langages? et systemes)$", ["langages", "systemes"]),
    (r"^(outils et applications|outils et logiciels)$", ["outils"]),
    (r"^(methodologies? et normes|methodes et normes)$", ["methodes", "normes"]),
    (r"^(langages?( de (developpement|programmation))?|programmation)$", ["langages"]),
    (r"^(frameworks?|bibliotheques?)$", ["frameworks"]),
    (r"^(outils|logiciels|outillage|applications)$", ["outils"]),
    (r"^(plateformes?|systemes?( d.?exploitation)?|os|environnements?)$", ["systemes", "cloud"]),
    (r"^cloud$", ["cloud"]),
    (r"^(bases? de donnees|sgbd|bdd)$", ["bases"]),
    (r"^(protocoles?|reseaux?|bus)$", ["protocoles"]),
    (r"^(normes?( et standards)?|standards?)$", ["normes"]),
    (r"^(ia|intelligence artificielle|data|data science)$", ["ia"]),
    (r"^(methodes?|methodologies?|gestion de projet)$", ["methodes"]),
    (r"^(fonctionnelles?|competences fonctionnelles|soft skills|savoir.?etre|relationnelles?|functional)$", ["methodes", "soft"]),
    (r"^(techniques?|competences techniques|hard skills|technologies|technical)$", ["*"]),
    (r"^(secteurs?( d.?activite)?|domaines?( d.?intervention)?|line of business|metiers?)$", ["@secteurs"]),
    (r"^(langues?|langues etrangeres|languages?)$", ["@langues"]),
]

PLACEHOLDER_TEXT = re.compile(
    r"^(x{2,}|\.{3,}|_{3,}|lorem ipsum.*|a completer|debut ?- ?fin|yyyy ?- ?yyyy|aaaa ?- ?aaaa|"
    r"intitule du diplome.*|annee ?/? ?diplome.*|degree.*|phrase de synthese.*|competence ?\d+|activite ?\d+|"
    r"(langue|language) ?\d* ?(niveau|level)|(yy|xx) .*|yyyy ?titre|ville ?-? ?pays|x annees?|rappel des outils.*|"
    r"presentation du ou des projets.*)$", re.I)
SUMMARY_PLACEHOLDER = re.compile(
    r"^(phrase de synthese|synthese|resume( du profil| de parcours)?|presentation|description du parcours|"
    r"synthese des competences)", re.I)
TITLE_PLACEHOLDER = re.compile(r"^(poste|poste recherche|titre|title|intitule du poste|fonction|job title)$", re.I)
LANG_PLACEHOLDER = re.compile(r"^(langue|language) ?\d* ?(niveau|level)$", re.I)   # texte normalisé (sans « : »)
NAME_PLACEHOLDER = re.compile(r"^(prenom nom|nom prenom|prenom|nom|trigramme|initiales)$", re.I)


def label_norm(text: str) -> str:
    return norm(re.sub(r"\((s|es)\)", r"\1", text or "")).strip(" :.-•")


def _match(table, text: str):
    t = label_norm(text)
    for pat, val in table:
        if re.match(pat, t):
            return val
    return None


def identity_field(label: str) -> str | None:
    return _match(IDENTITY_LABELS, label)


def mission_field(label: str) -> str | None:
    return _match(MISSION_LABELS, label)


def competence_target(label: str) -> list[str] | None:
    return _match(COMPETENCE_LABELS, label)


def is_placeholder(text: str) -> bool:
    t = label_norm(text)
    return bool(t) and bool(PLACEHOLDER_TEXT.match(t))


def inline_labels(text: str, vocab: str = "identity") -> list[tuple[str, str]]:
    """« Nom:\tMobilité géographique: » → [("Nom", "nom"), ("Mobilité géographique", "mobilite")]."""
    fn = identity_field if vocab == "identity" else mission_field
    out, buf = [], ""
    for p in re.split(r"(:)", text or ""):
        if p == ":":
            label = re.split(r"\t|\s{2,}", buf.strip())[-1].strip() if buf.strip() else ""
            f = fn(label) if label else None
            if f:
                out.append((label, f))
            buf = ""
        else:
            buf = p
    return out


def list_format(samples: list[str]) -> dict:
    """Déduit la forme des éléments d'une liste à partir des exemples du modèle."""
    s = " ".join(samples)
    n = label_norm(samples[0]) if samples else ""
    year_first = bool(re.match(r"^(yyyy|aaaa|annee|debut|\d{4})", n))
    m = re.search(r"(?:YYYY|AAAA|Ann[ée]e|\d{4})\s*([:/\-–])", s, re.I)
    return {
        "sep": " — " if "—" in s else (" – " if " – " in s else (" - " if " - " in s else " — ")),
        "colon": ":" in s,
        "paren": "(" in s,
        "paren_year": bool(re.search(r"\((?:19|20)\d{2}|ann[ée]e|date\)", s, re.I)) or not s.strip()
                      or bool(re.fullmatch(r"\w+", s.strip())),
        "year_first": year_first,
        "year_sep": (f" {m.group(1)} " if m.group(1) != "/" else " / ") if m else " — ",
        "rating": next((c for c in "●★■" if c in s), None),
    }
