# oriflux.js — recolección web

Un script de menos de 2 KB comprimido, servido por el servicio de ingestión
en una ruta versionada. Sin cookie, sin identificador en localStorage: el
visitante único es un hash diario (ver [privacidad](privacy.md)).

## Integración

```html
<script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
        data-key="ofx_ing_…"></script>
```

## Atributos

| Atributo | Función |
|---|---|
| `data-key` | **Obligatorio.** La clave de ingestión de la fuente (emitida por la interfaz, mostrada una vez). |
| `data-endpoint` | Opcional. Endpoint de ingestión alternativo — usado para el proxy first-party `/of/*` en superficies de marketing. |

## Qué se recolecta

Páginas vistas (URL, referente, UTM), Web Vitals, eventos personalizados
(`window.oriflux.track(name, props)`), identificación seudónima
(`window.oriflux.identify(pseudoId)` — cualquier identificador que parezca un
correo o un teléfono se rechaza en la validación).

Se respetan DNT y GPC: la petición recibe `{"tracked": false}`.
