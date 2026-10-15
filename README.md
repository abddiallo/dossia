# Dossia — V2

Génération de dossiers de compétences **fidèles au modèle Word de chaque ESN**, à partir d'un profil saisi une seule fois.
Parcours express : on dépose le modèle (ou on transfère l'e-mail de l'ESN), le dossier revient prêt.

## Les 5 différenciateurs, et où ils sont dans le code

| # | Promesse | Code |
|---|---|---|
| **D1** | **Zéro effort** : dépôt unique avec tri automatique, dépôt et réponse par e-mail, au plus une question, assistant en langage courant | `routes/drops.py`, `services/inbound.py`, `services/emailer.py`, `engine/classify.py`, `engine/assistant.py` |
| **D2** | **Fidélité Word** : on réutilise les paragraphes, tableaux et runs du modèle (clonage XML), puis un test automatique compare le résultat à l'original. Gère aussi les modèles « formulaire » (libellés, tableaux libellé/valeur, grilles de compétences avec niveaux ou jauges, en-têtes) | `engine/analyzer.py`, `engine/formscan.py`, `engine/filler.py`, `engine/formfill.py`, `engine/fidelity.py` |
| **D3** | **Zéro invention** : chaque texte du dossier est rattaché à un élément du profil ; une reformulation IA qui ajoute une compétence ou un chiffre est rejetée | `engine/adapter.py` (`verify`, `validate_rephrase`) |
| **D4** | **Effet réseau** : un modèle validé une fois est reconnu sans question pour tous les utilisateurs (décisions partagées + copie vidée, sans données personnelles) | `engine/library.py`, `SharedTemplate`, `pipeline.contribute_to_library` |
| **D5** | **Profils tech / industrie** : référentiel de technos, normes (DO-178C, ISO 26262…) et secteurs ; Qt5 / Qt 5.15 / QtQuick regroupés | `engine/skills.py` |

## Le parcours (V2)

Quatre onglets : **Accueil**, **Mon profil**, **Dossiers**, **Modèles**. Les maquettes validées sont dans `docs/maquettes-v2/`.

1. **Mon profil** : on dépose son CV (ou l'export PDF LinkedIn, ou on remplit à la main). On modifie directement dans la page,
   avec enregistrement automatique. Les points déduits à vérifier sont en orange. « Dites-le simplement » accepte une phrase
   (« disponible à partir du 1er décembre », « ajoute Docker », « anglais C1 »).
2. **Nouveau dossier**, en 3 étapes :
   - **L'offre** (facultative) : texte surligné en jaune pour ce qui est dans le profil, en pointillés pour ce qui manque.
     « Je l'ai » ajoute une compétence au profil, éventuellement dans une mission. Rien n'est ajouté sans l'utilisateur.
   - **Le modèle** : galerie des modèles d'ESN avec aperçu, ou dépôt d'un nouveau .docx.
   - **Le dossier** : aperçu avec les adaptations surlignées (sur l'aperçu seulement), nombre de pages, anonymisation,
     adaptation à l'offre, missions incluses, demandes en langage courant, téléchargement Word ou PDF.
3. **Modèles** : chaque modèle montre ses pages d'origine, un essai avec votre profil, et au plus une ou deux questions.

## Démarrage rapide (Docker)

```bash
cp .env.example .env          # mettre au minimum SECRET_KEY ; ANTHROPIC_API_KEY est optionnelle
docker compose up --build
```

Ouvrir **http://localhost:8080**. En `DEV_MODE=true`, le lien de connexion s'affiche directement à l'écran et les e-mails
sont écrits dans le volume `data` (`/data/outbox/*.eml`) au lieu d'être envoyés.

**Sans clé d'IA**, tout fonctionne en mode heuristique : extraction du CV par analyse des sections, adaptation par
réordonnancement (compétences et réalisations pertinentes d'abord), assistant par règles. **Avec une clé**, l'extraction
est plus robuste et les textes sont reformulés pour la fiche de poste, toujours sous le contrôle de `validate_rephrase`.

## Développement sans Docker

```bash
# backend (Python 3.11+, LibreOffice et poppler-utils installés)
cd backend && pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://dossia:dossia@localhost:5432/dossia   # Postgres requis (JSONB)
uvicorn app.main:app --reload            # sans REDIS_URL, les tâches tournent dans un thread

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxy /api → :8000)
```

## Tests

```bash
cd backend && pytest -q tests/          # ou : python tests/test_engine.py
```

22 tests sur le moteur (dont la correspondance offre/profil, « Dites-le simplement » et l'aperçu surligné), avec 5 structures de modèles générées par `tests/fixtures/make_fixtures.py` :
dossier rempli d'un autre consultant, missions en lignes de tableau, modèle vide à placeholders, modèle « complexe »
(zone de texte flottante, liste alignée avec des espaces, section inconnue) et modèle « formulaire » (bandeaux en
tableau, libellés « Nom : », tableau libellé/valeur, grille de compétences avec niveaux, un tableau par mission,
TRIGRAMME dans l'en-tête).

Pour tester aussi de **vrais modèles d'ESN** (non fournis dans le dépôt) :
```bash
DOSSIA_REAL_TEMPLATES=/chemin/vers/modeles pytest -q tests/
```

Diagnostic d'un modèle précis :
```bash
python -m app.cli analyse "modele.docx" --cv mon_cv.pdf
```

Les tests vérifient notamment qu'aucune donnée de
l'ancien consultant ne subsiste, que la mise en forme est conservée, que la limite de pages est respectée et que
l'assistant refuse d'ajouter ce qui n'est pas dans le profil.

## Architecture

```
frontend (React + Vite) ──/api──▶ backend (FastAPI) ──▶ PostgreSQL
                                     │   ▲
                       Redis + RQ ◀──┘   └── webhook e-mail entrant (Postmark / Brevo / Mailgun)
                          │
                       worker(s) : extraction CV · analyse modèle · génération (LibreOffice → PDF, aperçus)
```

```
backend/app/
  engine/        moteur pur (sans base de données), entièrement testé
    analyzer.py    modèle .docx → zones (identité, synthèse, compétences, missions répétables…)
    filler.py      remplissage fidèle par clonage des éléments du modèle
    adapter.py     profil + fiche de poste → contenu tracé (segments, stats d'origine, question unique)
    generate.py    orchestration + respect de la limite de pages + contrôle de fidélité
    cv_extract.py  CV (PDF/Word/texte) → profil ; différences entre deux CV
    assistant.py   « raccourcis la synthèse et enlève Python » → modifications
    match.py       offre ↔ profil : compétences présentes / absentes et leur position dans le texte
    highlight.py   copie surlignée du dossier pour l'aperçu « Montrer les adaptations »
    profile_assistant.py  « Dites-le simplement » sur le profil
    skills.py      référentiel compétences / normes / secteurs
    library.py     bibliothèque partagée (copie vidée, décisions réutilisables)
  services/      pipeline (base + moteur), e-mail entrant / sortant
  routes/        API REST (/api/v1)
frontend/src/    parcours express (Accueil, Dossier prêt) + écrans avancés (Profil, Modèles, Sources, Historique)
docs/maquettes/  maquettes des écrans validées
```

### Parcours d'un dossier

1. **Dépôt** (`POST /api/v1/drops` ou e-mail) : chaque fichier est classé (CV, modèle, fiche de poste).
2. **CV** → extraction ; le premier CV crée le profil sans confirmation, les suivants proposent seulement les nouveautés.
3. **Modèle** → analyse. Si la bibliothèque partagée le connaît déjà, ses décisions s'appliquent : zéro question.
   Sinon, au plus quelques questions (écran « modèle complexe »). Un test automatique compare ensuite le rendu à l'original.
4. **Génération** dès que le modèle et le profil sont prêts : adaptation tracée, remplissage, PDF, aperçus.
   Si le dossier dépasse la limite de pages, la règle du modèle s'applique (missions récentes, descriptions raccourcies
   ou page supplémentaire).
5. **Une question au plus** (ex. « la synthèse met l'énergie en avant, ça vous va ? »), puis téléchargement.
   Par e-mail, la réponse part automatiquement avec le .docx et le .pdf ; on modifie en répondant à l'e-mail.

## Brancher l'e-mail entrant

1. Créer un domaine de réception (ex. `depot.dossia.fr`) chez Postmark, Brevo ou Mailgun, avec un MX vers le fournisseur.
2. Webhook : `POST https://<votre-domaine>/api/v1/webhooks/inbound-email` avec l'en-tête
   `X-Webhook-Secret: <INBOUND_WEBHOOK_SECRET>` (ou `?secret=` dans l'URL).
3. Le format attendu est celui de Postmark (`services/inbound.py`). Pour un autre fournisseur, adapter la lecture des champs.
4. Sécurité : seules l'adresse du compte et les adresses ajoutées dans Paramètres peuvent déposer, avec SPF/DKIM valides.

## Mise en production : ce qui reste à faire

- **Migrations** : les tables sont créées au démarrage (`init_db`) et les colonnes ajoutées en V2 par `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. Passer à Alembic avant la prochaine évolution du schéma.
- **Stockage** : disque local dans la V1. Remplacer `storage.py` par un stockage objet chiffré hébergé en UE.
- **Paiement** : les offres et le quota gratuit (`FREE_DOSSIERS_PER_MONTH`) sont en place, pas le paiement (Stripe à brancher).
- **Purge RGPD** : planifier `python -m app.maintenance` chaque nuit.
- **Version anglaise** des dossiers et **intégration Boond** : prévues en V2.
- **Valider sur de vrais modèles** : l'analyseur est testé sur 4 structures représentatives. Avant le lancement, le faire
  tourner sur 15 à 20 vrais modèles d'ESN et ajuster les heuristiques (`analyzer.py`) sur les cas qui échouent.
