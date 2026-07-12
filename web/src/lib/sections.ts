/** Project sections of the target IA (issue #44). The single source for
 *  both the shell navigation and the route table — every section now has
 *  its shipped view (the overview, #68, was the last one). */

export const PROJECT_SECTIONS = [
  { key: "overview", path: "overview" },
  { key: "web", path: "web" },
  { key: "api", path: "api" },
  { key: "live", path: "live" },
  { key: "product", path: "product" },
  { key: "goals", path: "goals" },
  { key: "alerts", path: "alerts" },
  { key: "annotations", path: "annotations" },
  { key: "projectSettings", path: "settings" },
] as const;

export type SectionKey = (typeof PROJECT_SECTIONS)[number]["key"] | "orgSettings";
