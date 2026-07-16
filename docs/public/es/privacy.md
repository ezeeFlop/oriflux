# Modelo de privacidad

Oriflux es sin cookies y sin banner de consentimiento **por construcción**, no
por configuración:

- **Visitante único** = `hash(daily_salt, project, IP, user-agent)`. La sal se
  destruye cada día: vincular dos días es imposible — también para nosotros.
- **IP**: se resuelve a país/región/ciudad/ASN en la ingestión y luego se
  descarta. Nunca se escribe en la base de datos, nunca se registra en logs.
- **Sin identificador persistente** en el navegador: sin cookie, sin
  localStorage.
- **identify()** solo acepta identificadores seudónimos — los correos y
  teléfonos se rechazan en la validación.
- **Consecuencia asumida**: la retención y los embudos multi-día solo existen
  para usuarios identificados; los embudos anónimos se limitan a una sola
  sesión/día y se etiquetan como tales en la interfaz.
- **Residencia**: el 100 % de los datos permanece en Europa; la capa de IA
  (SPT Models) se ejecuta en la misma infraestructura y solo ve agregados.
- **DNT / GPC** respetados en la ingestión.
