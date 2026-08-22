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

## Recherche documentaire V1

Le premier moteur de retrieval est déterministe et lexical : il renvoie des passages sourcés, pas une réponse générée.

Exemple :

```powershell
Invoke-RestMethod "http://localhost:8000/search?q=الصلاة%20في%20السفر&work_uri=0595IbnRushdHafid.BidayatMujtahid&limit=5"
```

Chaque résultat expose notamment le texte original, le volume/page, la hiérarchie de section, son statut explicite ou inféré, la version OpenITI, le hash du chunk, le statut qualité et la provenance bibliographique disponible.

La recherche lexicale est accélérée par un index PostgreSQL `pg_trgm` créé par la migration `002_lexical_trigram_index` ; cette optimisation n'est pas présentée comme du BM25 ni comme de la recherche sémantique.

Contrat détaillé : `docs/search-api.md`.

## Évaluation du retrieval

Une petite suite de régression versionnée permet de mesurer la recherche avant d'ajouter embeddings et synthèse LLM :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval
```

Pour échouer si une requête de référence ne retrouve plus la bonne section dans son top-k :

```powershell
docker compose exec api python -m app.cli.evaluate_retrieval --fail-under-hit-rate 1.0
```

Méthodologie : `docs/retrieval-evaluation.md`.

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

**Attention :** `docker compose down -v` supprime les volumes PostgreSQL/Qdrant locaux. Ne pas l'utiliser lorsqu'il faut conserver le corpus ingéré.
