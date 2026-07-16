# Primeros pasos en 30 minutos

Oriflux unifica la analítica web, la analítica de producto y la analítica de
API — sin cookies, sin banner de consentimiento, alojado en Europa.

## 1. Crea tu organización

Inicia sesión con Google en tu instancia de Oriflux: el flujo de bienvenida
crea tu organización, tu primer proyecto y su fuente, y luego te entrega tu
clave de ingestión (mostrada una única vez) y el fragmento listo para pegar.
La pantalla espera a que llegue tu primer evento.

## 2. Sitio web — una etiqueta de script

```html
<script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
        data-key="ofx_ing_…"></script>
```

> El fragmento exacto, con tu clave, lo genera la interfaz (Configuración →
> Proyectos → tu fuente → «Emitir una clave de ingestión»).

## 3. API en Python — un middleware

```python
from oriflux_sdk import OrifluxMiddleware

app.add_middleware(OrifluxMiddleware, api_key="ofx_ing_…")  # FastAPI / Starlette / cualquier ASGI
```

`pip install oriflux-sdk`. Agregación en el cliente en ventanas de 60 s,
< 1 ms por petición, fire-and-forget: una caída de Oriflux (o una cuota
superada) nunca afecta a tu aplicación.

## 4. Verifica

Abre tu proyecto en el panel: la vista Live muestra tus visitantes en tiempo
real; las vistas Web/API se llenan en segundos.
