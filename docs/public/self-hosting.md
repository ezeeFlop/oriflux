# Auto-hébergement

Oriflux s'installe chez vous en quelques minutes : des images publiques
multi-arch (amd64 + arm64) sur GHCR, un `docker-compose.yml` lisible, pas de
`install.sh | sh`. Le serveur est sous licence AGPL-3.0 — le code que vous
déployez est [celui que vous pouvez lire](https://github.com/ezeeFlop/oriflux).

## Prérequis

- Docker Engine ≥ 24 avec le plugin Compose.
- Une machine **~4 vCPU / 8 Go de RAM recommandés, ClickHouse compris** —
  c'est le dimensionnement honnête pour un usage confortable. Les quatre
  services Oriflux eux-mêmes tiennent dans < 2 vCPU / 4 Go ; ClickHouse
  prend le reste et démarre à ~1 Go au repos. En dessous (2 vCPU / 4 Go
  tout compris), ça fonctionne pour de petits volumes.
- ~10 Go de disque pour démarrer (les événements ClickHouse sont très
  compressés ; comptez l'ordre de 1 Go pour 10 M d'événements).
- Un client OAuth Google (gratuit) pour la connexion au tableau de bord —
  voir ci-dessous.

## Installation

```bash
mkdir oriflux && cd oriflux
curl -fsSLO https://raw.githubusercontent.com/ezeeFlop/oriflux/main/deploy/self-host/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/ezeeFlop/oriflux/main/deploy/self-host/.env.example -o .env
# Éditez .env : trois secrets obligatoires (openssl rand -hex 32),
# votre client id Google, l'email propriétaire et vos projets.
docker compose up -d
```

Tous les services exposent un healthcheck ; `docker compose ps` doit montrer
tout le monde `healthy` (ClickHouse met ~30 s au premier démarrage).

## Bootstrap — votre première organisation

```bash
docker compose exec api python -m oriflux.bootstrap
```

La commande est **idempotente** (relançable sans risque). Elle crée votre
organisation, vos projets avec leurs sources web + API, et imprime **une
seule fois** les clés d'ingestion et de lecture, puis l'URL du tableau de
bord. Stockez ces clés : le serveur n'en conserve qu'une empreinte sha256.

## Connexion au tableau de bord

Le tableau de bord s'authentifie via Google Sign-In. Créez un client OAuth
(« Web application ») sur
[console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials),
ajoutez l'URL de votre tableau de bord aux origines JavaScript autorisées,
et renseignez `ORIFLUX_GOOGLE_CLIENT_ID` dans `.env`. Le compte Google
correspondant à `ORIFLUX_BOOTSTRAP_OWNER_EMAIL` est propriétaire de
l'organisation.

## Reverse proxy & TLS

Le compose expose deux ports HTTP : `8080` (tableau de bord, qui proxifie
lui-même `/api`) et `8100` (ingestion — la cible du snippet et des SDK).
Mettez votre reverse proxy TLS devant, par exemple avec Caddy :

```
analytics.example.com {
    reverse_proxy localhost:8080
}
in.example.com {
    reverse_proxy localhost:8100
}
```

Le snippet à coller sur vos sites devient alors :

```html
<script defer src="https://in.example.com/v1/oriflux.js" data-key="ofx_ing_…"></script>
```

(`oriflux.js` accepte `data-endpoint` si vous préférez servir le script et
recevoir les événements sur des hôtes différents.)

## Sauvegardes

- **PostgreSQL** (métadonnées : orgs, clés, règles d'alerte) : `pg_dump`
  quotidien suffit — la base est minuscule.
- **ClickHouse** (les événements) : utilisez
  [clickhouse-backup](https://github.com/Altinity/clickhouse-backup) vers un
  stockage S3/MinIO. C'est le montage exact de notre stack de production
  (sauvegarde quotidienne `create_remote`, 14 rétentions distantes).
- **Redis** n'est qu'un tampon : AOF `everysec` est déjà activé ; au pire,
  une seconde d'événements en vol est perdue lors d'un crash.

## Mise à jour

Les images sont taguées par version **et** `latest`. En production, épinglez
une version dans `.env` (`ORIFLUX_TAG=0.1.0`) et mettez à jour délibérément :

```bash
# 1. sauvegardez (voir ci-dessus)
# 2. changez ORIFLUX_TAG dans .env, puis :
docker compose pull && docker compose up -d
```

Les migrations de schéma s'exécutent automatiquement au démarrage du service
`api`. Consultez les notes de version avant tout saut de version majeure.

## Rétention des données

Par défaut : **13 mois d'événements bruts** (TTL ClickHouse, partitions
mensuelles) et **5 ans d'agrégats**. Les adresses IP ne sont jamais
persistées — résolues en géographie à l'ingestion, puis jetées.
