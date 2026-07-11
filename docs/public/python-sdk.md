# oriflux-sdk — analytics API pour Python

`pip install oriflux-sdk` (PyPI, licence MIT).

```python
from oriflux_sdk import OrifluxMiddleware

app.add_middleware(
    OrifluxMiddleware,
    api_key="ofx_ing_…",          # clé d'ingestion de la source API
    endpoint="https://in.oriflux.sponge-theory.dev",  # défaut
)
```

## Garanties

- **Zéro impact hôte** : agrégation en mémoire par fenêtres de 60 s
  (pattern Apitally), envoi fire-and-forget avec circuit breaker — une
  panne d'Oriflux ou un `429` de quota ne remonte jamais dans votre app.
- **< 1 ms** de surcoût par requête, mémoire bornée (~2 000 clés
  d'agrégation par fenêtre, débordement dans un bucket `geo=unresolved`).
- **Vie privée** : l'IP de l'appelant fait partie de la clé d'agrégation,
  est résolue en pays/ASN à l'ingestion puis jetée — elle n'est jamais
  persistée.

## Ce que vous obtenez

Volumes, latences (p50/p95/p99), taux d'erreurs 4xx/5xx, endpoints,
consommateurs, géographie des appelants — par minute.
