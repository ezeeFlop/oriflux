---
description: Show an Oriflux traffic + API overview for a project over a period.
argument-hint: [project] [period]
---

Give the user a headline analytics overview for a project — `$ARGUMENTS`.

1. Resolve the project: if the slug is ambiguous or missing, call `list_projects`
   and pick the match (or ask if there are several). Interpret any period hint
   (e.g. "last 7 days", "this month"); default to the last 7 days if unspecified.
2. Call `get_overview` for that project and period. If the user is really asking
   about API traffic (requests, error rates, latency), call `get_api_health`
   instead or in addition.
3. Present the key numbers clearly (visitors as visit-days, pageviews, sessions,
   bounce rate, session duration, API requests, error rates, p95). Only report
   figures Oriflux returned; do not invent or extrapolate.
