# oriflux-sdk — analítica de API para Python

`pip install oriflux-sdk` (PyPI, licencia MIT).

```python
from oriflux_sdk import OrifluxMiddleware

app.add_middleware(
    OrifluxMiddleware,
    api_key="ofx_ing_…",          # la clave de ingestión de la fuente API
    endpoint="https://in.oriflux.sponge-theory.dev",  # por defecto
)
```

## Garantías

- **Cero impacto en el host**: agregación en memoria en ventanas de 60 s (el
  patrón Apitally), entrega fire-and-forget con un circuit breaker — una caída
  de Oriflux o una cuota `429` nunca aparecen en tu app.
- **< 1 ms** de sobrecoste por petición, memoria acotada (~2000 claves de
  agregación por ventana, con desbordamiento a un bucket `geo=unresolved`).
- **Privacidad**: la IP de quien llama forma parte de la clave de agregación,
  se resuelve a país/ASN en la ingestión y luego se descarta — nunca se
  persiste.

## Qué obtienes

Volúmenes, latencias (p50/p95/p99), tasas de error 4xx/5xx, endpoints,
consumidores, geografía de quien llama — por minuto.
