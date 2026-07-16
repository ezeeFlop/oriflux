# Autoalojamiento

Oriflux se instala en tu propia máquina en minutos: imágenes públicas
multi-arch (amd64 + arm64) en GHCR y un `docker-compose.yml` legible — sin
`install.sh | sh`. El servidor tiene licencia AGPL-3.0 — lo que despliegas es
[código que puedes leer](https://github.com/ezeeFlop/oriflux).

## Requisitos

- Docker Engine ≥ 24 con el plugin Compose.
- Una máquina con **~4 vCPU / 8 GB de RAM recomendados, ClickHouse incluido** —
  es el dimensionamiento honesto para un uso cómodo. Los cuatro servicios de
  Oriflux caben en < 2 vCPU / 4 GB; ClickHouse se lleva el resto y en reposo
  ronda 1 GB. Por debajo (2 vCPU / 4 GB en total), funciona para volúmenes
  pequeños.
- ~10 GB de disco para empezar (ClickHouse comprime los eventos de forma
  agresiva; cuenta con del orden de 1 GB por cada 10M de eventos).
- Un cliente OAuth de Google (gratuito) para el inicio de sesión del panel —
  ver más abajo.

## Instalación

```bash
mkdir oriflux && cd oriflux
curl -fsSLO https://raw.githubusercontent.com/ezeeFlop/oriflux/main/deploy/self-host/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/ezeeFlop/oriflux/main/deploy/self-host/.env.example -o .env
# Edita .env: tres secretos obligatorios (openssl rand -hex 32),
# tu client id de Google, el correo del propietario y tus proyectos.
docker compose up -d
```

Cada servicio incluye un healthcheck; `docker compose ps` debería mostrar todo
`healthy` (ClickHouse tarda ~30 s en el primer arranque).

## Bootstrap — tu primera organización

```bash
docker compose exec api python -m oriflux.bootstrap
```

El comando es **idempotente** (seguro de reejecutar). Crea tu organización,
tus proyectos con sus fuentes web + API, imprime las claves de ingestión y de
lectura **una única vez** y luego la URL del panel. Guarda esas claves: el
servidor solo conserva una huella sha256.

## Inicio de sesión del panel

El panel se autentica con Google Sign-In. Crea un cliente OAuth («Aplicación
web») en
[console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials),
añade la URL de tu panel a los orígenes de JavaScript autorizados y define
`ORIFLUX_GOOGLE_CLIENT_ID` en `.env`. La cuenta de Google que coincide con
`ORIFLUX_BOOTSTRAP_OWNER_EMAIL` es la propietaria de la organización.

## Proxy inverso y TLS

El archivo compose expone dos puertos HTTP: `8080` (panel, que hace de proxy
de `/api` por sí mismo) y `8100` (ingestión — el destino del fragmento y de
los SDK). Pon tu proxy inverso con TLS por delante, por ejemplo con Caddy:

```
analytics.example.com {
    reverse_proxy localhost:8080
}
in.example.com {
    reverse_proxy localhost:8100
}
```

El fragmento a pegar en tus sitios pasa entonces a ser:

```html
<script defer src="https://in.example.com/v1/oriflux.js" data-key="ofx_ing_…"></script>
```

(`oriflux.js` acepta `data-endpoint` si prefieres servir el script y recibir
los eventos en hosts distintos.)

## Copias de seguridad

- **PostgreSQL** (metadatos: organizaciones, claves, reglas de alerta): un
  `pg_dump` diario basta — la base de datos es diminuta.
- **ClickHouse** (los eventos): usa
  [clickhouse-backup](https://github.com/Altinity/clickhouse-backup) hacia un
  destino S3/MinIO. Es exactamente la configuración de nuestro stack de
  producción (`create_remote` diario, 14 copias remotas conservadas).
- **Redis** es solo un búfer: AOF `everysec` ya está activado; en el peor de
  los casos se pierde un segundo de eventos en vuelo ante una caída.

## Actualización

Las imágenes están etiquetadas por versión **y** con `latest`. En producción,
fija una versión en `.env` (`ORIFLUX_TAG=0.1.0`) y actualiza de forma
deliberada:

```bash
# 1. haz una copia de seguridad (ver arriba)
# 2. sube ORIFLUX_TAG en .env, luego:
docker compose pull && docker compose up -d
```

Las migraciones de esquema se ejecutan automáticamente al arrancar el servicio
`api`. Lee las notas de la versión antes de cualquier salto de versión mayor.

## Retención de datos

Valores por defecto: **13 meses de eventos en bruto** (TTL de ClickHouse,
particiones mensuales) y **5 años de agregados**. Las direcciones IP nunca se
persisten — se resuelven a geografía en la ingestión y luego se descartan.
