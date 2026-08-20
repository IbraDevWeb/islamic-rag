# Architecture V0

## Règle centrale

Le système est un moteur documentaire. Le modèle de langage ne constitue jamais une
source et ne doit jamais fabriquer une position juridique.

## Flux cible

Question FR/AR
→ compréhension / expansion terminologique
→ retrieval arabe hybride
→ diversification par école / auteur
→ validation des sources
→ regroupement des positions
→ synthèse
→ références vérifiées
→ traduction à la demande

## Composants

### PostgreSQL

Métadonnées structurées :

- auteurs ;
- ouvrages ;
- versions ;
- écoles ;
- genres ;
- provenance ;
- licences ;
- annotations éditoriales ;
- relations entre auteurs / ouvrages / écoles.

### Qdrant

Index de recherche :

- chunks ;
- vecteurs denses ;
- vecteurs sparse/lexicaux ;
- filtres de métadonnées ;
- recherche hybride.

### FastAPI

- API publique ;
- orchestration retrieval ;
- validation des citations ;
- future couche LLM ;
- future administration.

## Invariants de provenance

1. `text_original` n'est jamais modifié.
2. `text_normalized` est dérivé et reproductible.
3. Une citation doit pointer vers un chunk existant.
4. Une synthèse juridique sans source est invalide.
5. Une traduction IA doit être identifiée comme telle.
6. Une source rejetée pour qualité ne participe pas au retrieval.
