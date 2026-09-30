/* Shared sidebar for every page of the Prediction Market Intelligence Hub.
   Each frontend includes: <script src="http://localhost:8080/js/nav.js" defer></script>
   If this script can't load, pages keep their plain header and still work. */
(function () {
  var HOST = "http://" + (location.hostname || "localhost");
  var ICON = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    watchlist: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    portfolio: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>',
    research: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    analyst: '<path d="M12 3v18M5 7h14"/><path d="M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>'
  };
  var PAGES = [
    { port: "8080", label: "Dashboard", icon: "dashboard" },
    { port: "5101", label: "Watchlist", icon: "watchlist" },
    { port: "5102", label: "Portfolio", icon: "portfolio" },
    { port: "5103", label: "Research", icon: "research" },
    { port: "5104", label: "AI Analyst", icon: "analyst" }
  ];
  var SERVICES = [
    { port: "8000", label: "AI-Mode" },
    { port: "8100", label: "MCP server" },
    { port: "8200", label: "RAG server" }
  ];

  function svg(name, size) {
    return '<svg viewBox="0 0 24 24" width="' + (size || 17) + '" height="' + (size || 17) +
      '" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICON[name] + "</svg>";
  }

  function build() {
    var here = location.port;
    var links = PAGES.map(function (p) {
      var active = p.port === here ? ' class="active" aria-current="page"' : "";
      return '<a href="' + HOST + ":" + p.port + '/"' + active + ">" + svg(p.icon) + p.label + "</a>";
    }).join("");
    var services = SERVICES.map(function (s) {
      return '<span data-port="' + s.port + '"><i class="dot"></i>' + s.label + "</span>";
    }).join("");

    var aside = document.createElement("aside");
    aside.className = "sidebar";
    aside.innerHTML =
      '<a class="brand" href="' + HOST + ':8080/">' + svg("analyst", 22) +
      "<span>Prediction Market<br>Intelligence Hub</span></a>" +
      '<nav aria-label="Features"><div class="nav-label">Menu</div>' + links + "</nav>" +
      '<div class="services" aria-label="Shared AI services">' + services + "</div>";
    document.body.insertBefore(aside, document.body.firstChild);
    document.body.classList.add("has-sidebar");
    checkServices(aside);
    setInterval(function () { checkServices(aside); }, 30000);
  }

  // Reachability only: no-cors requests resolve when the service answers and
  // reject when nothing is listening, without needing CORS on the services.
  function checkServices(aside) {
    SERVICES.forEach(function (s) {
      var el = aside.querySelector('[data-port="' + s.port + '"] .dot');
      var ctrl = "AbortController" in window ? new AbortController() : null;
      var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 3000);
      fetch(HOST + ":" + s.port + "/health", { mode: "no-cors", cache: "no-store", signal: ctrl && ctrl.signal })
        .then(function () { el.className = "dot up"; el.parentNode.title = s.label + " is running"; })
        .catch(function () { el.className = "dot down"; el.parentNode.title = s.label + " is not reachable"; })
        .then(function () { clearTimeout(timer); });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})();
