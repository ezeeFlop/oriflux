/*! oriflux.js v1 — cookieless web analytics for the Sponge Theory ecosystem.
 * No cookies, no storage, no fingerprinting: the server derives everything
 * else (daily-rotating visitor hash, geo, UA) and honors DNT/GPC.
 * Usage: <script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
 *                data-key="ofx_ing_…" [data-endpoint="https://my.site/of"]></script>
 * Fire-and-forget by design: this script must never break or slow the host page.
 */
(function (w, d) {
  var s = d.currentScript;
  if (!s || !w.fetch) return;
  var key = s.getAttribute("data-key");
  if (!key) return;
  var endpoint =
    (s.getAttribute("data-endpoint") || "https://in.oriflux.sponge-theory.dev")
      .replace(/\/+$/, "") + "/api/v1/events";
  var last;

  function track() {
    var url = w.location.href;
    if (url === last) return;
    last = url;
    try {
      w.fetch(endpoint, {
        method: "POST",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + key
        },
        body: JSON.stringify({
          type: "pageview",
          url: url,
          referrer: d.referrer || "",
          props: { resolution: w.screen.width + "x" + w.screen.height }
        })
      })["catch"](function () {});
    } catch (e) {
      /* never impact the host page */
    }
  }

  /* SPA navigations: history API + back/forward */
  try {
    var push = w.history.pushState;
    w.history.pushState = function () {
      push.apply(w.history, arguments);
      track();
    };
    w.addEventListener("popstate", track);
  } catch (e) {}

  if (d.visibilityState === "hidden" && d.prerendering) {
    d.addEventListener("prerenderingchange", track, { once: true });
  } else {
    track();
  }
})(window, document);
