# Islamic RAG

Prototype de bibliothèque islamique documentaire assistée par IA.

## Principes

- Le LLM n'est jamais une source.
- Toute affirmation juridique doit être traçable vers un texte du corpus.
- Le texte source original est immuable.
- Toute normalisation est stockée séparément.
- En l'absence de sources suffisantes, le système doit le dire explicitement.
- Français et arabe sont des langues de première classe.

## Stack V0

- FastAPI
- PostgreSQL
- Qdrant
- Docker Compose

## Démarrage local

### 1. Configuration

Sous PowerShell :

```powershell
Copy-Item .env.example .env
```

### 2. Démarrer

```powershell
docker compose up --build
```

### 3. Appliquer les migrations

```powershell
docker compose exec api python -m app.cli.migrate
```

### 4. Vérifier

Dans un second terminal :

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health/dependencies
```

Documentation API :

http://localhost:8000/docs

Qdrant :

http://localhost:6333/dashboard

## Recherche documentaire V2

Le moteur public actuel reste déterministe et lexical : il renvoie des passages sourcés, pas une réponse générée.

Exemple :

```powershell
Invoke-RestMethod "http://localhost:8000/search?q=الصلاة%20في%20السفر&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5"
```

Chaque résultat expose notamment le texte original, le volume/page, la hiérarchie de section, son statut explicite ou inféré, la version OpenITI, le hash du chunk, le statut qualité et la provenance bibliographique disponible.

`deterministic_lexical_v2` recherche à la fois dans le texte normalisé et dans une projection normalisée de la hiérarchie de section. Les deux projections disposent d'index PostgreSQL `pg_trgm` séparés (migrations `002` et `003`). Cette couche reste purement lexicale : elle n'est pas présentée comme du BM25 ni comme de la recherche sémantique.

Contrat détaillé : `docs/search-api.md`.

## Évaluation du retrieval

Le projet possède maintenant plusieurs jeux d'évaluation séparant développement et holdout :

- `evals/retrieval_bidayat_v1.json` : smoke suite historique de 6 cas ;
- `evals/retrieval_bidayat_baseline_v2.json` : baseline de développement de 51 cas ;
- `evals/retrieval_bidayat_holdout_v1.json` : holdout indépendant figé avant son premier résultat ;
- `evals/retrieval_terminology_expansion_dev_v1.json` : petit dataset de développement volontairement contaminé par le diagnostic de terminologie.

Lancer un résumé de la baseline lexicale :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever lexical --summary-only
```

Afficher seulement les cas qui ratent leur rang cible :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever lexical --failures-only
```

Chaque exécution vérifie d'abord que les sections attendues existent réellement dans le corpus, puis renvoie notamment Hit@1, Hit@3, Hit@k, pass-rate strict, MRR, Precision@k, métriques par type de requête/difficulté, latence informative, SHA-256 du benchmark et empreinte du corpus.

La baseline de développement n'est pas conçue pour afficher artificiellement 100 %. Elle sert à mesurer objectivement les changements de retrieval. Le holdout ne doit pas être réutilisé pour régler les hyperparamètres d'un nouveau composant.

Méthodologie et options de seuils : `docs/retrieval-evaluation.md`.

## Semantic retrieval expérimental

Une couche dense locale est maintenant disponible pour **comparaison**, sans remplacer automatiquement `/search`.

Modèle par défaut :

```text
intfloat/multilingual-e5-large
```

La première exécution nécessite de reconstruire l'image API car FastEmbed/Qdrant Client sont de nouvelles dépendances :

```powershell
docker compose up -d --build api
docker compose exec api python -m app.cli.migrate
```

Construire ensuite le Qdrant dense index dérivé :

```powershell
docker compose exec api python -m app.cli.index_semantic
```

Puis comparer exactement le même benchmark :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever semantic --summary-only

docker compose exec api python -m app.cli.evaluate_retrieval --retriever hybrid --summary-only
```

Le mode `hybrid` combine `deterministic_lexical_v2` et le dense retriever par Reciprocal Rank Fusion, sans additionner des scores de nature différente. L'index Qdrant est accompagné d'un manifeste PostgreSQL qui vérifie modèle, dimension, schéma, fingerprint des chunks et nombre de points avant toute évaluation sémantique/hybride.

Détails : `docs/semantic-retrieval.md`.

## Tuning du retrieval hybride

Les poids lexical/sémantique peuvent être comparés automatiquement sans reconstruire les 1 538 embeddings documentaires :

```powershell
docker compose exec api python -m app.cli.tune_hybrid
```

Le profil Hybrid Retrieval V1 issu du tuning est `12,5 % lexical / 87,5 % semantic`. Le holdout indépendant a toutefois montré que le semantic seul égalait ce profil en qualité principale avec une latence plus faible ; le moteur hybride reste donc expérimental plutôt que d'être promu automatiquement.

Détails : `docs/hybrid-tuning.md` et `docs/holdout-v1-results.md`.

## Expansion terminologique contrôlée

Les échecs de candidate recall dus à des terminologies différentes peuvent être traités par un registre d'alias de retrieval versionné. Exemple actuellement validé :

```text
المضاربة <-> القراض
```

L'expansion ne modifie jamais les livres et n'est pas une source religieuse. Elle produit seulement plusieurs formulations de recherche dont les classements sont fusionnés.

Retrievers disponibles :

```text
lexical-expanded
semantic-expanded
hybrid-expanded
```

Détails : `docs/query-expansion.md`.

## Reranking multilingue expérimental

Le pipeline peut prendre les 20 meilleurs candidats de `semantic-expanded`, les réhydrater depuis PostgreSQL, puis les reclasser avec un cross-encoder multilingue.

Reranker V1 :

```text
Alibaba-NLP/gte-multilingual-reranker-base
via onnx-community/gte-multilingual-reranker-base
quantized ONNX ~341 MB
```

Le premier benchmark local a montré que cette V1 ne mérite pas d'être promue : sur la baseline de développement de 51 cas, elle conserve 50/51 passes strictes mais fait baisser Hit@1 de 98,04 % à 94,12 %, baisse le MRR et fait passer la latence médiane locale d'environ 62 ms à environ 5,28 s.

Le backend `reranked` reste disponible pour les expériences, mais il n'est pas le chemin de retrieval préféré.

Détails : `docs/reranking.md` et `docs/reranker-v1-results.md`.

## Evidence retrieval expérimental

La couche suivante expose maintenant des **preuves documentaires hydratées depuis PostgreSQL** sans génération de réponse.

Pipeline préféré expérimental :

```text
question
  -> expansion terminologique contrôlée
  -> semantic E5 dans Qdrant
  -> ids de chunks classés
  -> réhydratation PostgreSQL
  -> texte original + citations + hashes
```

Qdrant n'est donc jamais utilisé comme copie authoritative du texte. Si un id de chunk dérivé ne peut pas être retrouvé dans PostgreSQL, la requête échoue explicitement.

Exemple :

```powershell
Invoke-RestMethod "http://localhost:8000/evidence?q=المضاربة&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5"
```

La réponse contient `generated_answer: null`. Cette route prépare le futur étage de synthèse : un LLM pourra plus tard recevoir uniquement ces preuves hydratées et citées, jamais des payloads Qdrant pris comme sources.

Le moteur public `/search` reste lexical et inchangé.

Détails : `docs/evidence-retrieval.md`.

## Tests

```powershell
docker compose exec api pytest -q
```

Les tests backend sont également exécutés par GitHub Actions sur `main` et sur les pull requests.

## Arrêt

```powershell
docker compose down
```

Pour supprimer aussi les données locales :

```powershell
docker compose down -v
```

**Attention :** `docker compose down -v` supprime les volumes PostgreSQL/Qdrant locaux ainsi que le cache du modèle. Ne pas l'utiliser lorsqu'il faut conserver le corpus ingéré ou éviter de retélécharger les modèles.
