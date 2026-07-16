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

### Se connecter en un clic

Le dashboard rassemble tout dans *Réglages org → Connexion à Claude* : le
point d'accès, la clé et les commandes prêtes à coller.

- **Claude Code** — ajoutez la marketplace publique puis installez le plugin :

  ```
  /plugin marketplace add ezeeFlop/claude-plugins
  /plugin install oriflux@sponge-theory
  ```

  À l'installation, renseignez l'URL de base (par défaut
  `https://api.oriflux.sponge-theory.dev`) et votre clé de lecture
  `ofx_read_…`. Déjà installé ? `/plugin marketplace update sponge-theory`
  d'abord.

- **Claude Desktop** — double-cliquez le bundle `.mcpb` (`mcp/mcpb/` du
  dépôt), ou ajoutez un connecteur personnalisé pointant sur `<base>/mcp`
  avec l'en-tête `Authorization: Bearer`.

- **Tout autre client MCP** — la configuration `mcpServers` brute :

  ```json
  {
    "mcpServers": {
      "oriflux": {
        "type": "http",
        "url": "https://api.oriflux.sponge-theory.dev/mcp",
        "headers": { "Authorization": "Bearer ofx_read_…" }
      }
    }
  }
  ```

Aucun secret n'est embarqué : l'URL et la clé restent les vôtres, saisies à
la configuration et envoyées uniquement à votre instance.
