// Маршрутизация по hash: #/players/1?tab=compare. Переход отменяет запросы прошлой страницы

import { session } from "./api.js";

const routes = [];
let controller = null;

export function route(pattern, view, { auth = true, nav = null } = {}) {
  routes.push({ pattern, view, auth, nav });
}

export function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/players";
  const [path, query = ""] = raw.split("?");
  return { path, params: new URLSearchParams(query) };
}

export function navigate(path) {
  if (window.location.hash === `#${path}`) {
    render();
  } else {
    window.location.hash = path;
  }
}

/** Меняет query текущего адреса без перерисовки страницы (вкладки, фильтры) */
export function updateQuery(values) {
  const { path, params } = parseHash();
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined || value === "") params.delete(key);
    else params.set(key, value);
  }
  const qs = params.toString();
  history.replaceState(null, "", `#${path}${qs ? `?${qs}` : ""}`);
}

function setActiveNav(name) {
  const nav = document.querySelector(".app-nav");
  if (!nav) return;
  nav.hidden = !session.token;
  for (const link of nav.querySelectorAll("[data-nav]")) {
    if (link.dataset.nav === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

export async function render() {
  controller?.abort();
  controller = new AbortController();
  const { signal } = controller;
  const { path, params } = parseHash();
  const main = document.getElementById("main");

  for (const entry of routes) {
    const match = path.match(entry.pattern);
    if (!match) continue;
    if (entry.auth && !session.token) {
      navigate(`/login?next=${encodeURIComponent(path)}`);
      return;
    }
    if (!entry.auth && session.token && /^\/(login|register)/.test(path)) {
      navigate("/players");
      return;
    }
    setActiveNav(entry.nav);
    main.replaceChildren();
    await entry.view(main, { args: match.slice(1), params, signal });
    // Фокус на заголовок: экранный диктор сообщает о смене страницы
    if (!signal.aborted) {
      const heading = main.querySelector("h1");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
        document.title = `${heading.textContent} · FACEIT Progress`;
      }
    }
    return;
  }
  navigate("/players");
}

export function startRouter() {
  window.addEventListener("hashchange", render);
  render();
}
