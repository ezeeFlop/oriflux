# oriflux.js — collecte web

Script < 2 Ko gzippé, servi par le service d'ingestion à un chemin
versionné. Sans cookie, sans localStorage d'identifiant : le visiteur
unique est un hash journalier (voir [privacy](privacy.md)).

## Intégration

```html
<script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
        data-key="ofx_ing_…"></script>
```

## Attributs

| Attribut | Rôle |
|---|---|
| `data-key` | **Requis.** Clé d'ingestion de la source (émise par l'UI, affichée une fois). |
| `data-endpoint` | Optionnel. Endpoint d'ingestion alternatif — utilisé pour le proxy first-party `/of/*` sur les surfaces marketing. |

## Ce qui est collecté

Pages vues (URL, référent, UTM), Web Vitals, événements custom
(`window.oriflux.track(name, props)`), identification pseudonyme
(`window.oriflux.identify(pseudoId)` — tout identifiant ressemblant à un
email ou un téléphone est rejeté à la validation).

DNT et GPC sont honorés : la requête reçoit `{"tracked": false}`.
