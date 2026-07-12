# Privacy model

Oriflux is cookieless and consent-banner-free **by construction**, not by
configuration:

- **Unique visitor** = `hash(daily_salt, project, IP, user-agent)`. The
  salt is destroyed every day: linking two days is impossible — for us too.
- **IP**: resolved to country/region/city/ASN at ingestion, then discarded.
  Never written to the database, never logged.
- **No persistent identifier** in the browser: no cookie, no localStorage.
- **identify()** only accepts pseudonymous identifiers — emails and phone
  numbers are rejected at validation.
- **Accepted consequence**: retention and multi-day funnels only exist for
  identified users; anonymous funnels are bounded to a single session/day
  and labeled as such in the UI.
- **Residency**: 100% of the data stays in Europe; the AI layer (SPT
  Models) runs on the same infrastructure and only ever sees aggregates.
- **DNT / GPC** honored at ingestion.
