/** One alert event, as rendered on the portfolio home and the alerts
 *  screen: state dot, rule, metric-formatted value, firing state. */

import { useTranslation } from "react-i18next";
import { formatMetricValue } from "../lib/format";
import type { AlertEvent } from "../lib/api";

export default function AlertEventRow({ event }: { event: AlertEvent }) {
  const { t, i18n } = useTranslation();
  return (
    <>
      <span className={event.resolved_at ? "text-up" : "text-down"} aria-hidden>
        ●
      </span>
      <strong>{event.rule_name}</strong>
      <span className="text-ink-soft">{t(`metric.${event.metric}`)}</span>
      <span className="tnum font-semibold">{formatMetricValue(event.metric, event.value)}</span>
      <span className="ml-auto text-xs text-ink-soft">
        {event.resolved_at ? t("home.alertResolved") : t("home.alertFiring")} ·{" "}
        {new Date(event.fired_at).toLocaleString(i18n.language)}
      </span>
    </>
  );
}
