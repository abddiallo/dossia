"""
Bibliothèque partagée de modèles.  [D4]

Quand un utilisateur a validé un modèle, on partage :
  - les DÉCISIONS (quoi faire des sections inconnues, des zones flottantes…) indexées par l'empreinte
    structurelle du modèle → le suivant n'a aucune question à répondre ;
  - une copie du modèle « vidée » : chaque zone remplie par des libellés génériques, pour
    l'aperçu de la bibliothèque. Aucune donnée personnelle n'est conservée.
"""
from __future__ import annotations

from pathlib import Path

from .filler import fill

PLACEHOLDER_VIEW = {
    "anonymized": True, "nom_affiche": "[Initiales]", "titre": "[Titre du consultant]", "experience_annees": None,
    "disponibilite": "[Disponibilité]", "mobilite": "[Mobilité]", "resume": "[Synthèse du profil]",
    "competences": [{"label": "[Compétence]", "categorie": "langages", "niveau": 4},
                    {"label": "[Compétence]", "categorie": "outils", "niveau": 3}],
    "missions": [{"client": "[Client]", "dates": "MM/AAAA – MM/AAAA", "poste": "[Poste]", "contexte": "[Contexte]",
                  "realisations": ["[Réalisation]"], "environnement": "[Technologies]"}],
    "formations": [{"intitule": "[Diplôme]", "etablissement": "[École]", "annee": "[Année]"}],
    "certifications": [{"intitule": "[Certification]", "annee": ""}],
    "langues": [{"langue": "[Langue]", "niveau": "[Niveau]"}],
}


def shareable_decisions(spec: dict) -> dict:
    """Décisions réutilisables (clés stables) — jamais de texte d'exemple."""
    return {z["key"]: z["answer"] for z in spec["zones"] if z.get("status") == "confirmed" and z.get("answer")}


def blank_copy(template_path: str | Path, spec: dict, out_path: str | Path) -> Path:
    fill(template_path, spec, PLACEHOLDER_VIEW, out_path)
    return Path(out_path)
