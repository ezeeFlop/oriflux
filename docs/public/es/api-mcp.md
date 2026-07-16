# API REST y MCP

Todo lo que hace el panel pasa por `/api/v1` — no hay API privada. Dos
superficies de lectura:

## REST — el contrato de consulta tipado

`POST /api/v1/query` con un objeto tipado:

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

Las métricas y dimensiones se validan contra un registro mantenido a mano —
nunca SQL libre. Autenticación: una clave de lectura de la organización
(`ofx_read_…`, cabecera `Authorization: Bearer`).

## MCP — para tus agentes

El servidor MCP (de solo lectura) se expone en `/mcp` con las mismas claves de
lectura: consultas tipadas, embudos, retención, insights, alertas,
anotaciones. Consulta `docs/mcp.md` en el repositorio para el detalle
herramienta por herramienta.
