const routes = new Set(["home", "dashboard", "workspace", "profile", "message", "admin"]);

function routeFromLocation() {
  const hashRoute = window.location.hash.slice(1);
  if (routes.has(hashRoute)) return hashRoute;
  if (new URLSearchParams(window.location.search).get("view") === "dashboard") return "dashboard";
  return "home";
}

export function createRouter(onNavigate) {
  function navigate(route, replace = false) {
    if (!routes.has(route)) throw new Error(`Unknown view: ${route}`);
    const url = new URL(window.location.href);
    url.hash = route;
    if (replace) {
      window.history.replaceState(null, "", url);
    } else if (window.location.hash !== `#${route}`) {
      window.history.pushState(null, "", url);
    }
    onNavigate(route);
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-route]");
    if (!link) return;
    event.preventDefault();
    navigate(link.dataset.route);
  });

  window.addEventListener("popstate", () => onNavigate(routeFromLocation()));
  return { navigate, initialRoute: routeFromLocation };
}
