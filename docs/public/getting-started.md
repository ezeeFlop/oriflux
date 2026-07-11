# Démarrage en 30 minutes

Oriflux unifie web analytics, product analytics et API analytics — sans
cookie, sans bannière de consentement, hébergé en Europe.

## 1. Créez votre organisation

Connectez-vous avec Google sur votre instance Oriflux : le parcours de
bienvenue crée votre organisation, votre premier projet et sa source, puis
vous remet votre clé d'ingestion (affichée une seule fois) et le snippet
prêt à coller. L'écran surveille l'arrivée de votre premier événement.

## 2. Site web — une balise script

```html
<script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
        data-key="ofx_ing_…"></script>
```

> Le snippet exact, avec votre clé, est généré par l'interface (Réglages →
> Projets → votre source → « Émettre une clé d'ingestion »).

## 3. API Python — un middleware

```python
from oriflux_sdk import OrifluxMiddleware

app.add_middleware(OrifluxMiddleware, api_key="ofx_ing_…")  # FastAPI / Starlette / tout ASGI
```

`pip install oriflux-sdk`. Agrégation côté client par fenêtres de 60 s,
< 1 ms par requête, fire-and-forget : une panne d'Oriflux (ou un quota
dépassé) n'impacte jamais votre application.

## 4. Vérifiez

Ouvrez votre projet dans le dashboard : la vue Live montre vos visiteurs en
temps réel ; la vue Web/API se remplit en quelques secondes.
