# API REST & MCP

Tout ce que fait le dashboard passe par `/api/v1` — il n'y a pas d'API
privée. Deux surfaces de lecture :

## REST — le contrat de requêtes typé

`POST /api/v1/query` avec un objet typé :

```json
{
  "metric": "visitors",
  "dimensions": ["country"],
  "filters": [{"dimension": "project_id", "op": "eq", "value": "…"}],
  "granularity": "day",
  "period": {"start": "2026-06-01T00:00:00Z", "end": "2026-07-01T00:00:00Z"},
  "compare_to": "previous_period"
}
```

Métriques et dimensions sont validées contre un registre maintenu à la
main — jamais de SQL libre. Authentification : clé de lecture org
(`ofx_read_…`, en-tête `Authorization: Bearer`).

## MCP — pour vos agents

Le serveur MCP (lecture seule) est exposé sur `/mcp` avec les mêmes clés de
lecture : requêtes typées, funnels, rétention, insights, alertes,
annotations. Voir `docs/mcp.md` du dépôt pour le détail des outils.
