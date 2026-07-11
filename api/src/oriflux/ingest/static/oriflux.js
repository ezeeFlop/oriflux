/*! oriflux.js v1 — cookieless web analytics for the Sponge Theory ecosystem.
 * No cookies, no storage, no fingerprinting: the server derives everything
 * else (daily-rotating visitor hash, geo, UA) and honors DNT/GPC.
 * Usage: <script defer src="https://in.oriflux.sponge-theory.dev/v1/oriflux.js"
 *                data-key="ofx_ing_…" [data-endpoint="https://my.site/of"]></script>
 * Product analytics (§5.2): window.oriflux.track(name, props) and
 * window.oriflux.identify(userId, traits) — the user id lives in page
 * memory only; the server binds it to the session (nothing persisted here).
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
  var uid = "";

  function send(body) {
    try {
      w.fetch(endpoint, {
        method: "POST",
        keepalive: true,
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + key
        },
        body: JSON.stringify(body)
      })["catch"](function () {});
    } catch (e) {
      /* never impact the host page */
    }
  }

  function page() {
    var url = w.location.href;
    if (url === last) return;
    last = url;
    send({
      type: "pageview",
      url: url,
      referrer: d.referrer || "",
      props: { resolution: w.screen.width + "x" + w.screen.height }
    });
  }

  w.oriflux = {
    track: function (name, props) {
      var body = { type: "event", name: name, url: w.location.href, props: props || {} };
      if (uid) body.user_id = uid;
      send(body);
    },
    identify: function (userId, traits) {
      uid = String(userId || "");
      if (uid) send({ type: "identify", user_id: uid, traits: traits || {} });
    }
  };

  /* SPA navigations: history API + back/forward */
  try {
    var push = w.history.pushState;
    w.history.pushState = function () {
      push.apply(w.history, arguments);
      page();
    };
    w.addEventListener("popstate", page);
  } catch (e) {}

  if (d.visibilityState === "hidden" && d.prerendering) {
    d.addEventListener("prerenderingchange", page, { once: true });
  } else {
    page();
  }
})(window, document);
