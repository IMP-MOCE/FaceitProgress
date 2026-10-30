// Клиент API: JWT в sessionStorage, ошибки problem+json → ApiError, тайм-аут 30 с (NFR03)

const BASE = "/api/v1";
const TOKEN_KEY = "fp.token";
const EMAIL_KEY = "fp.email";
export const REQUEST_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(status, problem = {}, retryAfter = null) {
    super(problem.detail || problem.title || `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
    this.code = typeof problem.type === "string" ? problem.type.split("/").pop() : null;
    this.detail = problem.detail || problem.title || "";
    this.retryAfter = retryAfter ? Number(retryAfter) : null;
  }
}

function storage() {
  // sessionStorage живёт до закрытия вкладки; в приватном режиме может быть недоступен
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

let memoryToken = null;
let memoryEmail = null;

export const session = {
  get token() {
    return storage()?.getItem(TOKEN_KEY) ?? memoryToken;
  },
  get email() {
    return storage()?.getItem(EMAIL_KEY) ?? memoryEmail;
  },
  save(token, email) {
    memoryToken = token;
    memoryEmail = email;
    try {
      storage()?.setItem(TOKEN_KEY, token);
      storage()?.setItem(EMAIL_KEY, email);
    } catch {
      // Хранилище переполнено или запрещено - сессия останется в памяти вкладки
    }
  },
  clear() {
    memoryToken = null;
    memoryEmail = null;
    try {
      storage()?.removeItem(TOKEN_KEY);
      storage()?.removeItem(EMAIL_KEY);
    } catch {
      // ничего не делаем
    }
  },
};

let unauthorizedHandler = () => {};

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

function buildUrl(path, query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query || {})) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return `${BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function request(method, path, { body, query, auth = true, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;

  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), REQUEST_TIMEOUT_MS);
  const abortFromCaller = () => timeout.abort();
  signal?.addEventListener("abort", abortFromCaller, { once: true });

  let response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: timeout.signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.signal.aborted) {
      throw new ApiError(0, {
        type: "/problems/timeout",
        title: "Сервер не ответил за 30 секунд",
        detail: "Источник данных отвечает медленно. Повторите запрос",
      });
    }
    throw new ApiError(0, {
      type: "/problems/network",
      title: "Нет связи с сервером",
      detail: "Проверьте подключение к сети и повторите запрос",
    });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  if (response.status === 204) return null;
  const type = response.headers.get("Content-Type") || "";
  const data = type.includes("json") ? await response.json().catch(() => null) : null;
  if (!response.ok) {
    const error = new ApiError(
      response.status,
      data || { title: response.statusText },
      response.headers.get("Retry-After"),
    );
    if (response.status === 401 && auth) {
      session.clear();
      unauthorizedHandler(error);
    }
    throw error;
  }
  return data;
}

const get = (path, query, signal) => request("GET", path, { query, signal });

export const api = {
  register: (email, password) => request("POST", "/auth/register", { body: { email, password }, auth: false }),
  login: (email, password) => request("POST", "/auth/login", { body: { email, password }, auth: false }),
  logout: () => request("POST", "/auth/logout"),
  me: (signal) => get("/users/me", null, signal),
  deleteMe: () => request("DELETE", "/users/me"),

  players: {
    list: (query, signal) => get("/players", query, signal),
    create: (body) => request("POST", "/players", { body }),
    get: (id, signal) => get(`/players/${id}`, null, signal),
    update: (id, body) => request("PATCH", `/players/${id}`, { body }),
    remove: (id) => request("DELETE", `/players/${id}`),
    sync: (id) => request("POST", `/players/${id}/sync`),
    matches: (id, query, signal) => get(`/players/${id}/matches`, query, signal),
    stats: (id, query, signal) => get(`/players/${id}/stats`, query, signal),
    compare: (id, query, signal) => get(`/players/${id}/compare`, query, signal),
    maps: (id, query, signal) => get(`/players/${id}/maps`, query, signal),
    insights: (id, signal) => get(`/players/${id}/insights`, null, signal),
  },

  goals: {
    list: (query, signal) => get("/goals", query, signal),
    create: (body) => request("POST", "/goals", { body }),
    get: (id, signal) => get(`/goals/${id}`, null, signal),
    update: (id, body) => request("PATCH", `/goals/${id}`, { body }),
    remove: (id) => request("DELETE", `/goals/${id}`),
    progress: (id, signal) => get(`/goals/${id}/progress`, null, signal),
  },
};
