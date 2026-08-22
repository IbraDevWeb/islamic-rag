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

Le projet possède maintenant deux niveaux d'évaluation :

- `evals/retrieval_bidayat_v1.json` : smoke suite historique de 6 cas ;
- `evals/retrieval_bidayat_baseline_v2.json` : baseline exigeante par défaut de 51 cas couvrant structure, clitiques arabes, morphologie, changements d'ordre des mots, requêtes larges et discrimination entre thèmes proches.

Lancer un résumé de la baseline lexicale :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever lexical --summary-only
```

Afficher seulement les cas qui ratent leur rang cible :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --retriever lexical --failures-only
```

Chaque exécution vérifie d'abord que les sections attendues existent réellement dans le corpus, puis renvoie notamment Hit@1, Hit@3, Hit@k, pass-rate strict, MRR, Precision@k, métriques par type de requête/difficulté, latence informative, SHA-256 du benchmark et empreinte du corpus.

La baseline exigeante n'est pas conçue pour afficher artificiellement 100 %. Elle sert à figer le niveau réel d'un moteur puis à mesurer objectivement ses successeurs.

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

**Attention :** `docker compose down -v` supprime les volumes PostgreSQL/Qdrant locaux ainsi que le cache du modèle. Ne pas l'utiliser lorsqu'il faut conserver le corpus ingéré ou éviter de retélécharger les embeddings.
