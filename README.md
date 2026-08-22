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

### 3. Vérifier

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

Contrat détaillé : `docs/search-api.md`.

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
