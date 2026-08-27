# Athar Frontend

Interface web Next.js pour Islamic RAG.

## Démarrage avec Docker Compose

Depuis la racine du projet :

```powershell
docker compose up -d --build frontend
```

Puis ouvrir :

```text
http://localhost:3000
```

Le frontend ne contacte pas directement FastAPI depuis le navigateur. Les appels passent par la route serveur Next.js `/api/research`, qui dialogue avec `http://api:8000` dans le réseau Docker.

## Modes

- **Réponse sourcée** : appelle `/generate-synthesis`, affiche le brouillon, la validation structurelle, la vérification de soutien des citations et les passages sources.
- **Preuves seulement** : appelle `/evidence-bundle` sans générer de réponse.

Le corpus actuellement présenté dans l'interface est `Bidāyat al-Mujtahid` (`0595IbnRushdHafid.BidayatMujtahid`).
