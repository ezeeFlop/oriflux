---
description: List the Oriflux projects (products) visible to your read key.
---

List the user's Oriflux projects using the `list_projects` MCP tool. Present a
compact table: project name, slug, and any identifying detail the tool returns.
If the user passes an argument, treat it as a name filter and only show matching
projects. This is read-only — do not query metrics or change anything.
