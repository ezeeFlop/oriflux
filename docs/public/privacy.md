# Modèle de vie privée

Oriflux est cookieless et sans bannière de consentement **par
construction**, pas par configuration :

- **Visiteur unique** = `hash(sel_du_jour, projet, IP, user-agent)`. Le sel
  est détruit chaque jour : recouper deux journées est impossible, pour
  nous aussi.
- **IP** : résolue en pays/région/ville/ASN à l'ingestion, puis jetée.
  Jamais écrite en base, jamais loggée.
- **Aucun identifiant persistant** côté navigateur : ni cookie, ni
  localStorage.
- **identify()** n'accepte que des identifiants pseudonymes — les emails et
  téléphones sont rejetés à la validation.
- **Conséquence assumée** : la rétention et les funnels multi-jours
  n'existent que pour les utilisateurs identifiés ; les funnels anonymes
  sont bornés à une session/journée et libellés comme tels dans l'UI.
- **Résidence** : 100 % des données en Europe ; la couche IA (SPT Models)
  tourne sur la même infrastructure et ne voit que des agrégats.
- **DNT / GPC** honorés à l'ingestion.
