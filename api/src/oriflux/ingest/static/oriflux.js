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

  /* Web Vitals (§5.1): collected passively, reported once on page hide */
  try {
    var vitals = {};
    var nav = performance.getEntriesByType("navigation")[0];
    if (nav && nav.responseStart > 0) vitals.ttfb = nav.responseStart;
    var observe = function (type, handler, extra) {
      try {
        new PerformanceObserver(handler).observe(
          Object.assign({ type: type, buffered: true }, extra || {})
        );
      } catch (e) {}
    };
    observe("largest-contentful-paint", function (list) {
      var entries = list.getEntries();
      if (entries.length) vitals.lcp = entries[entries.length - 1].startTime;
    });
    var cls = 0;
    observe("layout-shift", function (list) {
      list.getEntries().forEach(function (entry) {
        if (!entry.hadRecentInput) cls += entry.value;
      });
      vitals.cls = cls;
    });
    var inp = 0;
    observe(
      "event",
      function (list) {
        list.getEntries().forEach(function (entry) {
          if (entry.duration > inp) inp = entry.duration;
        });
        if (inp) vitals.inp = inp;
      },
      { durationThreshold: 40 }
    );
    var reported = false;
    var report = function () {
      if (reported) return;
      reported = true;
      for (var name in vitals) {
        send({ type: "vital", name: name, value: vitals[name], url: w.location.href });
      }
    };
    d.addEventListener("visibilitychange", function () {
      if (d.visibilityState === "hidden") report();
    });
    w.addEventListener("pagehide", report);
  } catch (e) {}

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
