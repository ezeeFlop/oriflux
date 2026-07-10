# PRD — Oriflux
## Plateforme d'analytics unifiée pour l'écosystème Sponge Theory

| | |
|---|---|
| **Produit** | **Oriflux** — « l'origine des flux ». Nom sans collision produit/logiciel détectée (recherches web, juillet 2026) ; backups : Oriscope, SpongeMetrics. Dépôt INPI/EUIPO (classes 9 & 42) et réservation oriflux.com / .io / .ai à confirmer avant tout lancement public. |
| **Version du document** | 1.1 |
| **Date** | 10 juillet 2026 |
| **Auteur** | Christophe Verdier — Sponge Theory |
| **Statut** | Validé — décisions d'architecture verrouillées en session de revue du 10 juillet 2026 (marquées *[Décision 2026-07-10]* dans le texte) |
| **Positionnement** | Interne d'abord (dogfooding), architecture SaaS multi-tenant dès la V1 pour commercialisation ultérieure |

---

## 1. Vision & problème

### 1.1 Problème

Sponge Theory opère aujourd'hui un portefeuille de produits SaaS et d'applications hétérogènes : **AudiGEO.ai** (audit GEO & AI monitoring, multilingue FR/EN/ES), **ClipHaven** (capture et streaming vidéo — Web, WebOS TV, extensions navigateur), **Rayonne** (plateforme de stratégie marketing IA pour SaaS), **Spongram** (mémoire long terme / desktop Tauri + cloud), **NeoRAG** (plateforme RAG), **NeoKanban**, **NeoDicta** (macOS), **Choros**, ainsi que le site corporate **sponge-theory.ai** et les APIs **SPT Models**.

Chaque produit expose des fronts web, des APIs FastAPI, des apps desktop/mobiles et des extensions — mais **aucune vue unifiée n'existe** sur :

- Qui utilise quoi : visiteurs, comptes, tenants, consommateurs d'API ;
- D'où viennent les connexions : pays, région, ville, ASN, datacenter vs résidentiel ;
- Comment les produits sont utilisés : pages, événements produit, funnels d'activation, rétention ;
- La santé des APIs : volumétrie par endpoint et par consommateur, erreurs, latences ;
- L'impact business : signups, conversions, churn, corrélation trafic ↔ revenus (Stripe / Lemon Squeezy).

Aujourd'hui ces signaux sont éclatés (logs Swarm, Zeus pour l'infra, Stripe/Lemon Squeezy pour le billing, rien pour le comportement utilisateur), et l'ajout d'un outil tiers par produit multiplierait les coûts, les intégrations et les problèmes de conformité RGPD.

### 1.2 Vision

> **Un seul plan de contrôle analytics, self-hosted sur le cluster Sponge Theory, qui ingère le trafic web, les événements produit et les appels API de tous les produits, et restitue en temps réel l'origine géographique, l'usage et la santé de chaque service — sans cookies, conforme RGPD par défaut, et augmenté par l'IA.**

Oriflux suit la stratégie éprouvée des produits Sponge Theory : construit pour un usage interne d'abord, mais **multi-tenant, white-label ready et monétisable** dès la conception (Stripe / Lemon Squeezy), pour devenir à terme un produit commercial dont les produits Sponge Theory sont les clients zéro.

### 1.3 Pourquoi construire plutôt qu'acheter ?

L'étude du marché (§3) montre qu'aucune solution ne couvre à elle seule le triptyque **web analytics + product analytics + API analytics** en self-hosted léger :

- Les outils privacy-first (Plausible, Umami, Rybbit) couvrent le web mais pas les APIs ni la corrélation par consommateur ;
- PostHog couvre web + produit mais son self-hosting est lourd (ClickHouse + Kafka + Redis, 4 vCPU / 16 Go minimum, non recommandé au-delà de ~300k événements/mois en self-hosted) ;
- Les outils d'API analytics (Apitally, Moesif, Treblle) sont cloud-first, par produit, et ne parlent pas au web analytics.

De plus, Oriflux capitalise sur des briques déjà maîtrisées en interne : middleware FastAPI (pattern Zeus `/api/metrics`), SPT Models pour la couche IA, NeoRAG pour l'interrogation en langage naturel, et l'infrastructure Swarm existante. Le coût marginal d'infrastructure est quasi nul.

---

## 2. Objectifs & non-objectifs

### 2.1 Objectifs (V1 → V2)

1. **Couverture totale** : 100 % des produits Sponge Theory instrumentés (web + API) en moins de 30 minutes d'intégration par produit.
2. **Vue géographique de référence** : répartition des connexions par pays / région / ville / ASN, en temps réel et en historique, pour le web ET les APIs.
3. **Analytics produit** : événements custom, funnels, rétention, parcours utilisateurs, avec identification par compte/tenant.
4. **API analytics** : volumétrie, erreurs, latences (p50/p95/p99) par endpoint, par version, par clé API / consommateur.
5. **Privacy by design** : cookieless, pas de PII stockée par défaut, IP jamais persistée en clair, data residency UE → pas de bannière de consentement nécessaire en mode par défaut.
6. **Temps réel** : dashboard live (<5 s de latence d'ingestion à l'affichage).
7. **Alerting** : seuils et anomalies (trafic, erreurs, latence) vers email / Slack / webhook.
8. **Multi-tenancy** : organisations → projets → sources (site, app, API), RBAC, prêt pour des clients externes.
9. **IA native** : insights automatiques, détection d'anomalies et interrogation en langage naturel, propulsés par la couche d'inférence locale **SPT Models** (aucune donnée analytics envoyée à un LLM cloud par défaut).
10. **Interopérabilité agents IA** : Oriflux est lui-même consommable par des outils d'IA externes via un **serveur MCP** de premier rang (pattern `fastapi-mcp` déjà éprouvé chez Sponge Theory) — Claude, agents internes et clients MCP tiers peuvent interroger les analytics.

### 2.2 Non-objectifs (explicitement hors scope V1)

- **Monitoring infrastructure** (CPU, RAM, disques, containers) : c'est le rôle de **Zeus** — Oriflux consomme éventuellement ses données, ne les remplace pas.
- **Session replay** : reporté en V3 (coût stockage + complexité RGPD) ; l'état de l'art (PostHog, OpenReplay, Rybbit) le propose, on garde la porte ouverte.
- **A/B testing & feature flags** : hors scope, éventuel module V3+.
- **Log management généraliste** (type Loki/ELK) : Oriflux stocke des événements structurés, pas des logs bruts.
- **APM / distributed tracing complet** : on expose des hooks OpenTelemetry mais on ne réimplémente pas Jaeger/Tempo.

---

## 3. État de l'art & analyse concurrentielle (juillet 2026)

### 3.1 Web analytics privacy-first

| Solution | Licence | Stack | Points forts | Limites |
|---|---|---|---|---|
| **Plausible** | AGPL-3.0 | Elixir, PostgreSQL + ClickHouse | Simplicité, cookieless, léger | Peu d'analytics produit, pas d'API analytics |
| **Umami** | MIT | Node.js, PostgreSQL/MySQL | Très léger, funnels/rétention, self-host facile | Pas de géo fine ni d'API analytics |
| **Matomo** | GPL-3.0 | PHP, MySQL | Le plus complet (heatmaps, e-commerce), track record conformité (gouvernements) | Stack PHP datée, lourdeur, plugins payants |
| **Rybbit** | Open source (cloud dès 13 $/mois) | ClickHouse | Moderne : sessions, funnels, goals, rétention, Web Vitals, globe 3D temps réel, bot blocking | Jeune, pas d'API analytics |
| **OpenPanel** | AGPL-3.0 | ClickHouse | Web + product analytics unifiés, setup simple | Jeune, communauté réduite |
| **GoatCounter** | EUPL | Go, SQLite/PostgreSQL | Binaire unique, ultra-minimal | Trop minimal pour notre besoin |

### 3.2 Product analytics / all-in-one

| Solution | Licence | Points forts | Limites |
|---|---|---|---|
| **PostHog** | MIT (core) | Référence all-in-one : product analytics, session replay, flags, A/B, error tracking | Self-hosting lourd (ClickHouse+Kafka+Redis, 16 Go RAM min.) et non supporté à l'échelle (>300k evts/mois → cloud) |
| **OpenReplay** | AGPL-3.0 | Session replay web+mobile, co-browsing | Centré replay, pas de web analytics classique |
| **Mixpanel / Amplitude** | Propriétaire | Maturité fonctionnelle | Cloud US, coût, RGPD complexe — écartés |

### 3.3 API analytics & monitoring

| Solution | Modèle | Points forts | Limites |
|---|---|---|---|
| **Apitally** | SDK open source + cloud | Trafic/erreurs/latence par endpoint et par consommateur, uptime, alertes Slack/Teams, 22+ frameworks dont FastAPI, Express, NestJS ; agrégation côté client | Backend cloud propriétaire |
| **Moesif** | Propriétaire | Analytics API orientés business (monétisation) | Cloud, coûteux |
| **Treblle** | Propriétaire | DX, doc auto | Cloud only |

### 3.4 Enseignements pour Oriflux (état de l'art à intégrer)

1. **ClickHouse est le standard de facto** du stockage analytics événementiel (Plausible, PostHog, Rybbit, OpenPanel) — colonne, compression, agrégats temps réel.
2. **Cookieless par hash journalier rotatif** (`hash(daily_salt, site_id, ip, user_agent)`) : le pattern Plausible/Umami, qui évite le consentement tout en comptant les visiteurs uniques.
3. **Agrégation côté SDK** pour les APIs (pattern Apitally) : les métriques sont pré-agrégées dans le middleware avant envoi → overhead quasi nul, pas de payload sensible en transit par défaut.
4. **Le temps réel est devenu un différenciateur d'expérience** (globe 3D Rybbit, live view Plausible) — attendu par les utilisateurs.
5. **La couche IA est le champ de bataille 2026** : insights automatiques, détection d'anomalies, requêtes en langage naturel ("pourquoi le trafic espagnol a-t-il chuté hier ?"). Aucun acteur open source ne le fait bien en self-hosted → **c'est le différenciateur Oriflux**, appuyé sur SPT Models + NeoRAG.
6. **Bot filtering** natif indispensable (une part croissante du trafic est constituée d'agents IA / crawlers LLM) — et leur *identification* est une opportunité : AudiGEO fait déjà du "Bot Analytics" pour les crawlers IA ; Oriflux doit distinguer humains / bots classiques / agents IA, ce qui a une valeur directe pour le positionnement GEO de Sponge Theory.

---

## 4. Personas & cas d'usage

### 4.1 Personas

- **P1 — Le fondateur-opérateur (Christophe, persona primaire V1)** : veut, chaque matin, une vue consolidée de tous les produits : trafic, signups, usage API, anomalies. Sur desktop et mobile.
- **P2 — Le développeur** : intègre le SDK en minutes, débogue une montée d'erreurs 5xx sur un endpoint, vérifie l'impact d'un déploiement.
- **P3 — Le marketeur / growth** (interne puis clients Rayonne) : campagnes UTM, funnels d'acquisition, géographie des visiteurs, rapports hebdo automatiques.
- **P4 — Le client SaaS externe (V2+)** : "Founder Early-Stage SaaS B2B" — le même persona cible que Rayonne, canaux LinkedIn et SEO/GEO ; veut remplacer Google Analytics + un outil d'API monitoring par une seule solution européenne self-hostable.

### 4.2 Cas d'usage clés

| # | Cas d'usage | Persona | Priorité |
|---|---|---|---|
| UC1 | Voir en temps réel les visiteurs actifs et leur origine géographique sur tous les produits | P1 | P0 |
| UC2 | Comparer le trafic / les signups par pays et par produit sur une période | P1, P3 | P0 |
| UC3 | Suivre la volumétrie et les erreurs d'une API par endpoint et par clé API | P2 | P0 |
| UC4 | Être alerté sur Slack quand le taux d'erreur 5xx d'AudiGEO dépasse 2 % sur 5 min | P1, P2 | P0 |
| UC5 | Construire un funnel signup → activation → paiement et voir où ça décroche, par pays | P3 | P1 |
| UC6 | Identifier la part de trafic bots / agents IA par produit | P1, P3 | P1 |
| UC7 | Poser une question en langage naturel : "quels produits progressent en Espagne ce mois-ci ?" | P1 | P1 |
| UC8 | Recevoir un digest hebdo automatique par produit (email) | P1, P3 | P1 |
| UC9 | Suivre l'usage d'un tenant précis (compte Rayonne, workspace NeoRAG) à travers web + API | P1, P2 | P1 |
| UC10 | Un client externe crée son organisation, ajoute son site, paie son abonnement | P4 | P2 (V2) |

---

## 5. Périmètre fonctionnel détaillé

### 5.1 Module Web Analytics (P0)

- **Collecte** : script JS < 2 Ko (`oriflux.js`), async, sans cookie, servi par le service d'ingestion lui-même à un chemin versionné (pas de npm en V1). *[Décision 2026-07-10]* **Endpoint central par défaut** (ex. `in.oriflux.sponge-theory.ai` — intégration = une balise script + clé API par source, c'est ce qui tient l'objectif « < 30 min par produit ») ; le proxy first-party `/of/*` (Traefik/NPM) devient une **option documentée**, déployée uniquement sur les surfaces où les adblockers pèsent réellement (sponge-theory.ai, pages marketing publiques AudiGEO/Rayonne — le trafic loggué des dashboards est identifié et quasi insensible à l'adblock). Le SDK accepte une option `endpoint` dès la V1 pour basculer un produit sur son proxy en une ligne. + endpoint HTTP direct pour apps Tauri/mobile/TV (ClipHaven WebOS, NeoDicta, Spongram desktop, Choros).
- **Métriques standard** : pages vues, visiteurs uniques (hash journalier rotatif, cf. §11), sessions, durée, taux de rebond, sources/référents, UTM, appareils, OS, navigateurs, langues, résolutions.
- **Géo** : résolution IP → pays / région / ville / ASN via base MMDB locale — *[Décision 2026-07-10]* **DB-IP Lite par défaut** (sans clé, CC-BY 4.0 avec attribution « IP Geolocation by DB-IP » dans le dashboard), MaxMind GeoLite2 en option pour qui a une clé ; mise à jour automatique mensuelle. L'IP est résolue à l'ingestion puis jetée — seules les dimensions géo sont stockées.
- **Temps réel** : visiteurs actifs (fenêtre 30 s), carte du monde live + globe, top pages/pays en direct.
- **Web Vitals** : LCP, CLS, INP, TTFB par page et par pays (état de l'art Rybbit).
- **Bot intelligence** (différenciateur, synergie AudiGEO) : classification du trafic en 3 familles — humains / bots classiques (moteurs, uptime) / **agents & crawlers IA** (GPTBot, ClaudeBot, PerplexityBot…), avec dashboard dédié « AI visibility » par produit. *[Décision 2026-07-10]* Phasage : en phase 1, classification par **règles UA uniquement**, mais la colonne `traffic_class` existe dès le premier événement ingéré (un backfill de classification serait misérable) ; heuristiques comportementales et dashboard « AI visibility » en phase 2. La liste de crawlers/agents IA est **unique et maintenue à un seul endroit**, seedée depuis celle d'AudiGEO (cf. §15.2).

### 5.2 Module Product Analytics (P0/P1)

- **Événements custom** : `oriflux.track('signup_completed', {plan: 'pro'})` — schéma libre + propriétés typées.
- **Identification** : `oriflux.identify(user_id, {tenant, plan})` — opt-in par produit, pseudonymisé (ID interne, jamais d'email en clair).
- **Funnels** (P1) : étapes séquentielles, conversion par étape, segmentation par pays/source/appareil. *[Décision 2026-07-10]* Les funnels **multi-jours** ne sont disponibles que pour les utilisateurs identifiés (`identify()`) ; les funnels anonymes sont limités à la même session/journée et **étiquetés comme tels dans l'UI** — conséquence directe du hash journalier rotatif (§9), assumée plutôt que contournée.
- **Rétention** (P1) : cohortes hebdo/mensuelles par événement d'activation. *[Décision 2026-07-10]* **Réservée aux utilisateurs identifiés** : la rétention anonyme inter-jours est mathématiquement impossible par conception (le sel journalier est détruit). C'est le compromis Plausible, pas le compromis PostHog — et c'est ce qui préserve « pas de bannière de consentement ».
- **Parcours** (P1) : sankey des chemins de navigation entrée → conversion/sortie.
- **Goals** : objectifs déclaratifs (événement ou page) avec suivi de conversion.

### 5.3 Module API Analytics (P0)

- **Collecte** : middleware SDK (Python/ASGI d'abord — tous les back-ends Sponge Theory sont FastAPI — puis Node/Express) qui **agrège côté client** par fenêtre de 60 s (pattern Apitally) : compteurs par (endpoint templaté, méthode, code statut, consommateur, **IP appelante**), histogrammes de latence, tailles de payload. Aucun corps de requête transmis par défaut. *[Décision 2026-07-10]* L'IP dans la clé d'agrégation est ce qui rend la dimension géo possible malgré la pré-agrégation (Apitally ne fait pas de géo — c'est notre ajout) : l'ingestion résout IP → pays/ASN puis **jette l'IP**, comme pour le web. Cardinalité bornée : ~2 000 clés distinctes par fenêtre ; au-delà, les nouvelles IP tombent dans un bucket `geo=unresolved` avec un compteur d'overflow explicite — les données restent honnêtes sur elles-mêmes.
- **Dimensions** : endpoint, version d'API, code statut, classe d'erreur, consommateur (clé API / tenant / user), **géo du client appelant**, user-agent SDK.
- **Vues** : volumétrie, taux d'erreur 4xx/5xx, latences p50/p95/p99, top consommateurs, adoption par endpoint, comparaison avant/après déploiement (annotations de release).
- **Request log opt-in** (P1) : échantillonnage configurable de requêtes complètes (headers/payload masqués par règles) pour investigation.
- **Uptime & heartbeats** (P1) : checks HTTP synthétiques internes (les produits tournent sur le même Swarm) + heartbeats Celery/workers — complémentaire de Zeus, orienté service public (status page par produit, P2).

### 5.4 Module Business / Revenus (P1)

- Connecteurs **Stripe** (ClipHaven, Rayonne) et **Lemon Squeezy** (Spongram) : webhooks → événements revenus (trial, subscription, churn, MRR par produit).
- Corrélation acquisition → activation → revenu par pays et par source, MRR consolidé multi-produits — la vue « portefeuille » qu'aucun outil du marché ne donne.

### 5.5 Alerting & rapports (P0/P1)

- **Règles à seuils** (P0) : métrique + condition + fenêtre (ex. « 5xx > 2 % sur 5 min sur audigeo_api ») → email, Slack, webhook générique, ntfy.
- **Détection d'anomalies** (P1) : baseline saisonnière (jour de semaine/heure) calculée par job, écarts significatifs signalés sans configuration (« trafic ES −62 % vs attendu »).
- **Digests programmés** (P1) : rapport hebdo/mensuel par produit ou consolidé, généré par la couche IA (§6), envoyé par email (Resend, comme ClipHaven).

---

## 6. Couche IA — propulsée par SPT Models (P1, différenciateur clé)

Toute l'IA d'Oriflux s'appuie sur la couche d'inférence locale **SPT Models** (chat, embeddings, rerank) : **aucune donnée analytics ne sort de l'infrastructure** pour produire les insights — argument commercial majeur face à PostHog/Amplitude qui poussent l'IA cloud.

| Capacité | Description | Modèles SPT |
|---|---|---|
| **Ask Oriflux** (NL query) | Question en langage naturel → émission d'un **objet de requête typé** validé par le registre métriques/dimensions (§8.3 — le même contrat que le dashboard et le MCP ; les hallucinations meurent à la validation de schéma, jamais de SQL brut généré) → réponse chiffrée + graphique + explication. Ex. : « quels produits progressent en Espagne ce mois-ci ? » | chat |
| **Insights automatiques** | Job quotidien qui scanne tendances, ruptures, corrélations (déploiement ↔ latence, campagne ↔ signups) et publie un fil d'insights priorisés par impact | chat + stats classiques |
| **Digests narratifs** | Rédaction des rapports hebdo : synthèse, faits marquants, recommandations, dans la langue de l'utilisateur (FR/EN/ES, pattern AudiGEO) | chat |
| **Anomalies expliquées** | Quand une alerte part, l'IA joint un diagnostic : dimensions contributrices (pays, endpoint, consommateur), événements corrélés, releases annotées | chat |
| **Classification de trafic** | Affinage de la détection bots/agents IA au-delà des règles UA (heuristiques comportementales) | embed + rerank |
| **Segments sémantiques** | Recherche de pages/événements par similarité (« tout ce qui touche au checkout ») | embed |

Garde-fous : l'IA ne voit que des agrégats (jamais d'identifiants), chaque réponse cite les chiffres sources et la requête exécutée (auditabilité), budget d'inférence configurable par organisation.

---

## 7. Intégrations & interopérabilité agents IA

### 7.1 Serveur MCP natif (P0)

Oriflux expose un **serveur MCP** (HTTP streamable, auth par clé API scoppée en lecture seule par défaut), construit sur le pattern `fastapi-mcp` déjà utilisé chez Sponge Theory. Outils exposés :

- `list_projects`, `get_overview(project, period)` — synthèse trafic/erreurs/latence ;
- `query_metrics(metric, dimensions, filters, period)` — requêtes structurées (même DSL que Ask Oriflux) ;
- `get_geo_breakdown(project, level, period)` — répartition pays/région/ville ;
- `get_api_health(project, period)` — endpoints, erreurs, latences, consommateurs ;
- `get_insights(project)`, `get_alerts(status)` — fil d'insights IA et alertes ;
- `annotate(project, text, timestamp)` — poser une annotation (release, campagne) depuis un agent.

Cas d'usage : Claude/Cowork interroge Oriflux en session (« montre-moi la santé d'AudiGEO »), les agents de Rayonne consomment les données d'acquisition, Spongram enrichit sa mémoire avec les faits d'usage.

### 7.2 Autres intégrations

- **API REST publique** (P0) : tout ce que fait le dashboard passe par l'API (dogfooding), OpenAPI/Swagger, versionnée `/api/v1`.
- **Webhooks sortants** (P1) : alertes, insights, seuils → Slack, ntfy, endpoints custom.
- **OpenTelemetry** (P2) : réception OTLP/HTTP pour les événements et métriques applicatives, afin de ne pas enfermer les produits dans le SDK propriétaire.
- **Zeus** (P1) : lecture des métriques infra via son API FastAPI native (`/api/metrics`) pour corréler usage ↔ ressources — conformément à la décision d'architecture existante (pas de Prometheus).
- **Exports** (P1) : CSV/Parquet par requête, dumps programmés vers MinIO (S3), connecteur Metabase/Superset via ClickHouse en lecture seule.

---

## 8. Architecture technique

### 8.1 Principes

1. **Stack maison** : FastAPI (Python 3.11+, Pydantic v2, SQLAlchemy 2 async, UV), React 18 + TypeScript + React Query + Tailwind, Celery + Redis, PostgreSQL 16 (métadonnées) — alignée sur tous les produits existants.
2. **ClickHouse pour les événements** : nouveau composant dans le cluster, standard de l'état de l'art (Plausible, PostHog, Rybbit). Un seul nœud suffit largement en V1 (volumétrie estimée < 5 M événements/mois tous produits confondus), réplication possible plus tard.
3. **Léger par conception** : cible < 2 vCPU / 4 Go RAM au repos pour l'ensemble de la stack (vs 16 Go PostHog) — c'est un argument produit pour la commercialisation self-hosted.
4. **Déploiement Swarm/Portainer** : stack `oriflux.yml`, `deploy-portainer.sh`, builds multi-arch (pattern cliphaven/neokanban), Traefik/NPM en frontal, healthcheck `/healthz`.

### 8.2 Vue d'ensemble

```
   Produits SPT / clients
┌─────────────────────────────┐
│ oriflux.js (web, <2Ko)      │──┐
│ SDK ASGI FastAPI (agrégé)   │──┤   HTTPS (first-party proxy /of/*)
│ SDK Node/Express            │──┤
│ Apps Tauri/TV (HTTP direct) │──┘
└─────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────┐
│  oriflux_ingest (FastAPI, stateless, scalable)           │
│  validation Pydantic → enrichissement (GeoLite2, UA,     │
│  bot-classif) → hash visiteur → buffer Redis Streams     │
└──────────────────────────────────────────────────────────┘
              │ micro-batches (1-5 s)
              ▼
┌───────────────────┐   ┌────────────────────────────────┐
│  ClickHouse       │   │  PostgreSQL 16                 │
│  events, api_agg, │   │  orgs, users, projets, règles  │
│  sessions (TTL,   │   │  d'alerte, annotations,        │
│  agrégats matér.) │   │  connecteurs, billing          │
└───────────────────┘   └────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────┐
│  oriflux_api (FastAPI) : REST /api/v1 + WebSocket live   │
│  + serveur MCP (fastapi-mcp) + moteur DSL de requêtes    │
├──────────────────────────────────────────────────────────┤
│  oriflux_workers (Celery) : anomalies, insights IA (SPT  │
│  Models), digests (Resend), webhooks Stripe/LS, GeoIP    │
│  refresh, uptime checks, exports MinIO                   │
├──────────────────────────────────────────────────────────┤
│  oriflux_web (React/TS) : dashboard temps réel           │
└──────────────────────────────────────────────────────────┘
```

### 8.3 Choix structurants

| Décision | Choix | Justification |
|---|---|---|
| Store événements | ClickHouse (MergeTree + vues matérialisées + TTL), **dès le jour 1** *[Décision 2026-07-10]* | Standard du domaine, agrégats temps réel, compression ~10×. Le modèle de données exploite des fonctionnalités natives CH (t-digest, vues matérialisées, TTL, `ALTER DELETE`) — un « DSL indépendant du store » serait une fiction. Ops : mono-nœud, version LTS épinglée, `clickhouse-backup` → MinIO dès le jour 1 |
| Bus d'ingestion | Redis Streams (déjà dans le cluster) | Pas de Kafka : simplicité, volumétrie interne le permet — c'est précisément la lourdeur qu'on reproche à PostHog |
| Garanties d'ingestion *[Décision 2026-07-10]* | **At-least-once + inserts idempotents** : UUID assigné à chaque événement à l'ingestion, consumer group Redis Streams, `XACK` seulement après commit ClickHouse, dédup à l'insert sur l'UUID ; Redis en AOF `everysec` | Aucun mode de défaillance ne corrompt silencieusement les compteurs par double-insert ; la fenêtre de perte ≤ 1 s sur crash Redis est acceptée et documentée (bruit pour de l'analytics). Les SDK restent fire-and-forget : la perte au premier saut est inhérente au modèle |
| Moteur de requêtes *[Décision 2026-07-10]* | **Objet de requête typé** (Pydantic : `metric, dimensions, filters, granularity, period, compare_to`) validé par un **registre métriques/dimensions** maintenu à la main (nom → fragment SQL vérifié + combinaisons autorisées) — pas de langage générique | Contrat **unique** pour dashboard, REST, MCP et Ask Oriflux. Discipline : aucun endpoint dashboard n'a de SQL bespoke hors registre, sinon la parité MCP/Ask-Oriflux meurt en silence. Surfaces non-DSL explicitement listées (live view) |
| Géolocalisation *[Décision 2026-07-10]* | **DB-IP Lite** (country+city+ASN), local, par défaut ; MaxMind GeoLite2 en option (`ORIFLUX_GEOIP_PROVIDER=maxmind`) | Gratuit, offline, RGPD-friendly (résolution à la volée, IP jetée). Même format MMDB (lecteur inchangé), **sans clé ni compte**, CC-BY 4.0 redistribuable avec attribution — supprime le risque EULA MaxMind (cf. §14) |
| Auth dashboard | JWT + OAuth Google (pattern ClipHaven) ; SSO/Clerk optionnel V2 | Réutilisation de briques éprouvées |
| Temps réel UI | **Polling 10 s en V1** (requêtes registry) ; WebSocket + globe en phase 3 *[Décision 2026-07-10]* | La cible < 5 s d'ingestion reste ; c'est l'*affichage* qui relaxe — indistinguable du WebSocket pour un dashboard consulté par une personne |
| Multi-tenancy | `org_id` partout, isolation par row-level + clés API scoppées | Prêt pour SaaS sans refonte |
| IA | SPT Models exclusivement (chat/embed/rerank) | Souveraineté des données, coût marginal nul, cohérence écosystème |
| Dépôt & distribution *[Décision 2026-07-10]* | **Monorepo privé** : `api/` (un package Python, 3 entrypoints ingest/api/workers), `web/`, `sdk/js/`, `sdk/python/`, `deploy/`. `oriflux.js` servi par l'ingestion (pas de npm en V1) ; **SDK Python publié sur PyPI public en MIT** (`oriflux-sdk`) | Modèles Pydantic partagés entre services ; un SDK *client* MIT ne fuit aucune valeur serveur (norme du secteur, cf. Apitally) et ne préjuge pas de la licence serveur (AGPL vs FSL, décision reportée phase 4) |
| Nommage interne | stack `spt-oriflux`, services `oriflux_{ingest,api,workers,web,clickhouse}` | Conventions cluster existantes |

### 8.4 Modèle de données (simplifié)

**ClickHouse — `events`** : `timestamp, org_id, project_id, source_type (web|app|api), event_name, visitor_hash, session_id, user_pseudo_id?, tenant_id?, url_path, referrer, utm_*, country, region, city, asn, device, os, browser, locale, traffic_class (human|bot|ai_agent), props (JSON)` — partition mensuelle, TTL brut 13 mois (configurable), agrégats conservés 5 ans.

**ClickHouse — `api_minutely`** : `timestamp_min, org_id, project_id, endpoint, method, status_class, status_code, consumer_id, country, count, error_count, latency_histogram (t-digest), bytes_in/out` — TTL brut 13 mois, roll-up horaire/journalier au-delà.

**PostgreSQL** : `organizations, users, memberships (RBAC owner/admin/viewer), projects, sources, api_keys (ingest & read scopes), alert_rules, alert_events, annotations, insights, connectors (stripe|lemonsqueezy|zeus), report_schedules, billing_*`.

---

## 9. Privacy, sécurité & conformité (P0)

- **Cookieless par défaut** : visiteur unique = `hash(sel_journalier, project_id, ip, user_agent)` ; le sel est détruit chaque jour → pas de suivi inter-jours ni inter-sites, pas de bannière de consentement requise en mode par défaut (pattern Plausible/Umami). *À valider avec la CNIL / exemption de consentement au cas par cas — Oriflux fournit la documentation DPA/registre de traitement type.* Conséquence assumée *[Décision 2026-07-10]* : rétention et funnels multi-jours réservés aux utilisateurs identifiés (§5.2) — on ne réintroduit **pas** d'identifiant persistant anonyme (localStorage), qui tuerait le différenciateur.
- **IP jamais persistée** : résolution géo + ASN à l'ingestion, puis destruction. Option « IP tronquée conservée 24 h » pour l'anti-abus, off par défaut.
- **Mode identifié opt-in** : `identify()` n'accepte que des IDs pseudonymes ; PII (emails) refusée par validation à l'ingestion.
- **Data residency** : 100 % cluster Sponge Theory (UE/France). Aucun sous-traitant hors UE pour la télémétrie ; IA locale (SPT Models).
- **Sécurité** : durcissement pattern Rayonne — protection SSRF sur les connecteurs/webhooks, RBAC, chiffrement Fernet des tokens de connecteurs, rate limiting à l'ingestion (par clé et par IP), CORS strict, audit log des accès admin. Webhooks entrants (Stripe/LS) idempotents dès la V1 (leçon de l'audit Rayonne).
- **DNT/GPC respectés** ; droit à l'effacement : purge par `user_pseudo_id`/`tenant_id` (ClickHouse `ALTER DELETE` asynchrone).

---

## 10. Expérience utilisateur (dashboard)

- **Home « Portefeuille »** (unique sur le marché) : tuiles par produit — visiteurs live, tendance 7 j, taux d'erreur API, MRR — triées par anomalie ; le fil d'insights IA en colonne droite.
- **Vue produit** : onglets Web / Produit / API / Revenus / Insights, période comparable (vs période précédente, vs année précédente).
- **Vue Géo** : carte choroplèthe monde → drill-down région/ville, tableau ASN/opérateurs, filtre par classe de trafic (humain/bot/agent IA), export.
- **Live** : globe temps réel des connexions tous produits (wow effect démo, pattern Rybbit).
- **Ask Oriflux** : barre de commande (⌘K) — questions NL, navigation, création d'alertes (« alerte-moi si les 5xx de NeoRAG dépassent 1 % »).
- **Multilingue FR/EN/ES** dès la V1 (i18n pattern AudiGEO — pas de plan_status non traduit cette fois 😉), thème sombre/clair, responsive mobile (P1 : PWA).
- **Partage** : dashboards publics par lien signé (P1), embed iframe (P2).

---

## 11. Exigences non fonctionnelles

| Exigence | Cible V1 |
|---|---|
| Latence ingestion → visible | < 5 s (p95) à l'ingestion ; affichage par polling 10 s en V1 (WebSocket en phase 3) |
| Débit ingestion | 500 evts/s soutenus (≈ 40 M/jour) sur 1 nœud — marge ×100 vs besoin interne |
| Latence requêtes dashboard | < 500 ms (p95) sur 13 mois de données |
| Overhead SDK API | < 1 ms par requête (agrégation en mémoire, flush async 60 s) |
| Poids script web | < 2 Ko gzippé |
| Disponibilité | 99,5 % (aligné infra mono-cluster) ; l'indisponibilité d'Oriflux ne doit JAMAIS impacter les produits (SDK fire-and-forget, timeouts courts, circuit breaker) |
| Empreinte au repos | < 2 vCPU / 4 Go RAM (hors ClickHouse : +1 vCPU / 2 Go) |
| Rétention | Brut 13 mois, agrégats 5 ans (configurables par org) |
| Sauvegardes | ClickHouse backup quotidien → MinIO + PG backup dédié avec alerte d'échec (leçon audit Rayonne) |

---

## 12. Roadmap

### Phase 1 — MVP interne (6-8 semaines)
Ingestion web + API (at-least-once, dédup UUID), géo pays/région/ville, dashboard par produit + home portefeuille, live view par **polling 10 s**, alertes à seuils (Slack/email), SDK JS servi par l'ingestion + SDK ASGI FastAPI (PyPI, MIT), moteur de requêtes typé + registre, serveur MCP lecture seule, auth JWT/OAuth, RBAC multi-tenant, **i18n FR/EN** (scaffolding dès le jour 1, ES en phase 2), classification bots **UA-only** (colonne `traffic_class` dès J1), déploiement Swarm. **Instrumentation : sponge-theory.ai, AudiGEO, NeoRAG en premier.** *[Décision 2026-07-10 : WebSocket, locale ES et heuristiques bots sont explicitement sortis de la phase 1 — le périmètre P0 d'origine ne tenait pas en 6-8 semaines solo.]*

### Phase 2 — Profondeur produit (4-6 semaines)
Événements custom + identify, funnels (multi-jours = identifiés uniquement, §5.2), rétention (identifiés uniquement), goals, bot/AI-agent intelligence (heuristiques + dashboard « AI visibility »), locale ES, Web Vitals, connecteurs Stripe/Lemon Squeezy, annotations de releases, digests email, anomalies automatiques, SDK Node/Express, intégration Zeus, exports MinIO/CSV.

### Phase 3 — Couche IA complète (4 semaines)
Ask Oriflux (NL→objet de requête typé), fil d'insights quotidien, alertes expliquées, digests narratifs multilingues, MCP enrichi (annotations, alertes), WebSocket temps réel + globe live, dashboards publics. Rebranchement d'AudiGEO comme consommateur de la classification de trafic Oriflux (§15.2).

### Phase 4 — Commercialisation (à cadencer selon traction)
Onboarding self-serve, billing (Stripe), plans & quotas (appliqués dès le schéma en V1 — leçon Rayonne : pas de quotas jamais enforcés), landing multilingue, docs publiques, image Docker one-command + licence (open-core AGPL-3.0 ou source-available type FSL — décision à prendre), status pages publiques, SSO.

---

## 13. Métriques de succès

- **Interne (fin phase 2)** : 100 % des produits instrumentés ; ≥ 1 décision produit/semaine appuyée sur Oriflux ; temps de détection d'un incident API < 5 min (vs découverte manuelle aujourd'hui) ; 0 impact mesurable sur les latences des produits.
- **Produit (fin phase 3)** : ≥ 70 % des questions analytics posées via Ask Oriflux/MCP obtiennent une réponse exploitable sans requête manuelle.
- **Commercial (phase 4)** : 10 organisations externes actives en 3 mois ; coût d'infrastructure < 10 €/org/mois ; NPS ≥ 40.

## 14. Risques & mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| ClickHouse = nouvelle brique à opérer | Moyen | Mono-nœud simple, version LTS épinglée, `clickhouse-backup` → MinIO dès le jour 1, TTL agressifs. *[Décision 2026-07-10]* Le fallback « démarrer dans PG puis migrer » est **abandonné** : le schéma exploite des fonctionnalités natives CH, et une migration à chaud sur un système en production serait plus risquée qu'apprendre l'ops CH sur une base vide |
| Adblockers bloquent la collecte web | Moyen | Endpoint central par défaut ; proxy first-party ciblé sur les surfaces marketing (§5.1), option `endpoint` dans le SDK, nom de script neutre |
| GeoLite2 : clé MaxMind requise, EULA interdit la redistribution | Faible | *[Décision 2026-07-10]* **Résolu** : DB-IP Lite par défaut (sans clé, CC-BY 4.0 redistribuable avec attribution, même format MMDB) ; MaxMind reste une option pour qui apporte sa clé |
| Dérive de scope (APM, replay, flags…) | Élevé | Non-objectifs §2.2 fermes ; Zeus garde l'infra ; replay ≥ V3 |
| Qualité NL→requête (hallucinations) | Moyen | DSL contraint + validation de schéma, jamais de SQL généré librement, chiffres toujours issus du moteur, requête affichée |
| Conformité consentement (zones grises CNIL) | Moyen | Mode par défaut ultra-conservateur, doc juridique fournie, options par pays |
| Marque : collision tardive sur « Oriflux » | Faible | Recherche INPI/EUIPO + dépôt classes 9/42 avant lancement public ; backups Oriscope/SpongeMetrics |
| Solo founder : bande passante | Élevé | Phases courtes livrables, MVP volontairement resserré, réutilisation maximale des patterns existants |

## 15. Questions ouvertes

1. Licence pour la version publique : AGPL-3.0 (crédibilité open source, protège du SaaS-jacking) vs FSL/BUSL (protection commerciale) ? *Décision volontairement reportée en phase 4. Déjà acté [2026-07-10] : le SDK Python client est MIT sur PyPI public dès la V1 — seul le serveur est concerné par cette question.*
2. ~~Faut-il migrer le « Bot Analytics » d'AudiGEO vers Oriflux (source unique) ou garder les deux et synchroniser ?~~ **Résolu [2026-07-10] — ni migration, ni duplication : inversion de dépendance.** Oriflux devient la source de vérité de la classification de trafic pour les **propriétés Sponge Theory** (liste crawlers/agents IA unique, seedée depuis celle d'AudiGEO) ; AudiGEO garde son produit Bot Analytics orienté clients et devient **consommateur** d'Oriflux via API/MCP en phase 3+. D'ici là, coexistence délibérée et alignée. Les sites clients AudiGEO non instrumentés par Oriflux restent dans AudiGEO en permanence.
3. Status pages publiques par produit : dans Oriflux ou produit séparé ultérieur ?
4. Politique de rétention par défaut pour les futurs clients (13 mois est-il le bon standard ?) ;
5. Nom définitif : valider Oriflux après recherche d'antériorité INPI/EUIPO formelle.

---

*Document généré le 10 juillet 2026. Sources marché : voir annexe A.*

## Annexe A — Sources de l'étude de marché

- OpenPanel — Self-Hosted Web Analytics 2026 : https://openpanel.dev/articles/self-hosted-web-analytics
- PostHog — Best open source analytics tools : https://posthog.com/blog/best-open-source-analytics-tools
- Rybbit — site officiel (features, pricing) : https://rybbit.com/
- Apitally — API monitoring & analytics : https://apitally.io/ et https://github.com/apitally/apitally-py
- Moesif — Comparison of Open Source API Analytics Tools : https://www.moesif.com/blog/technical/api-analytics/Comparison-of-Open-Source-API-Analytics-and-Monitoring-Tools/
- Haloy — Umami vs Plausible vs Rybbit : https://haloy.dev/blog/self-hosted-analytics-compared
- Databuddy — Best Open Source GA Alternatives 2026 : https://www.databuddy.cc/blog/best-open-source-google-analytics-alternatives-2026
