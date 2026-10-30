// Общие компоненты состояний: загрузка, ошибка, пусто, предупреждения, подтверждение

import { h, replace } from "./dom.js";
import { fmtDateTime, matchKd, resultLabel } from "./format.js";

export function announce(message) {
  const live = document.getElementById("live");
  if (!live) return;
  live.textContent = "";
  // Пауза нужна, чтобы экранный диктор заметил повтор того же текста
  setTimeout(() => {
    live.textContent = message;
  }, 50);
}

export function toast(message, kind = "success") {
  const region = document.getElementById("toasts");
  if (!region) return;
  const item = h("div", { class: ["toast", `toast--${kind}`], text: message });
  region.append(item);
  setTimeout(() => item.remove(), 4000);
}

export function loading(text = "Загрузка…") {
  return h(
    "div",
    { class: "state state--loading", role: "status", "aria-live": "polite" },
    h("span", { class: "spinner", "aria-hidden": "true" }),
    h("span", { text }),
  );
}

const ERROR_TITLES = {
  0: "Нет связи с сервером",
  400: "Некорректный запрос",
  401: "Требуется вход",
  403: "Нет доступа",
  404: "Не найдено",
  409: "Конфликт",
  422: "Проверьте данные",
  429: "Слишком много попыток",
  500: "Ошибка сервера",
  503: "Источник данных FACEIT временно недоступен",
};

// Для ошибок предметной области заголовок берётся из ответа сервера
const DOMAIN_CODES = new Set([
  "invalid-credentials",
  "faceit-player-not-found",
  "insufficient-data",
  "too-many-requests",
  "source-unavailable",
]);

export function errorTitle(error) {
  if (error?.code === "timeout") return "Сервер долго не отвечает";
  if (DOMAIN_CODES.has(error?.code) && error.problem?.title) return error.problem.title;
  return ERROR_TITLES[error?.status] || "Что-то пошло не так";
}

export function errorText(error) {
  if (!error) return "";
  if (error.status === 429 && error.retryAfter) {
    return `${error.detail || "Подождите"}. Повторить можно через ${error.retryAfter} с`;
  }
  if (error.status === 500) return "Попробуйте повторить запрос позже";
  const text = error.detail || error.message || "";
  return text === errorTitle(error) ? "" : text;
}

/** Блок ошибки; кнопка «Повторить», если передан onRetry */
export function errorState(error, { onRetry, action } = {}) {
  return h(
    "div",
    { class: "state state--error", role: "alert", "data-status": error?.status ?? "" },
    h("p", { class: "state__title", text: errorTitle(error) }),
    errorText(error) ? h("p", { class: "state__text", text: errorText(error) }) : null,
    h(
      "div",
      { class: "state__actions" },
      onRetry
        ? h("button", { class: "btn btn--secondary", type: "button", on: { click: onRetry } }, "Повторить")
        : null,
      action || null,
    ),
  );
}

export function emptyState(title, text, action = null) {
  return h(
    "div",
    { class: "state state--empty" },
    h("p", { class: "state__title", text: title }),
    text ? h("p", { class: "state__text", text }) : null,
    action ? h("div", { class: "state__actions" }, action) : null,
  );
}

export function notice(text, kind = "info") {
  return h("p", { class: ["notice", `notice--${kind}`], role: kind === "warn" ? "note" : null }, text);
}

/** Загружает данные в контейнер с состояниями загрузки и ошибки */
export async function loadInto(container, loader, render, { signal, loadingText } = {}) {
  replace(container, loading(loadingText));
  container.setAttribute("aria-busy", "true");
  try {
    const data = await loader();
    if (signal?.aborted) return;
    replace(container, render(data));
  } catch (error) {
    if (signal?.aborted || error?.name === "AbortError") return;
    if (error?.status === 401) return; // обработчик сессии уже перевёл на вход
    replace(
      container,
      errorState(error, { onRetry: () => loadInto(container, loader, render, { signal, loadingText }) }),
    );
  } finally {
    container.removeAttribute("aria-busy");
  }
}

/** Блокирует кнопку на время запроса */
export async function busy(button, task, busyText = "Подождите…") {
  const label = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = busyText;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = label;
  }
}

/** Встроенное подтверждение вместо window.confirm */
export function confirmButton({ label, question, confirmLabel, onConfirm, danger = true }) {
  const wrapper = h("span", { class: "confirm" });
  const trigger = h("button", {
    class: ["btn", danger ? "btn--danger-ghost" : "btn--secondary"],
    type: "button",
    text: label,
  });
  const showTrigger = () => {
    replace(wrapper, trigger);
    trigger.focus();
  };
  trigger.addEventListener("click", () => {
    const yes = h("button", {
      class: ["btn", danger ? "btn--danger" : "btn--primary"],
      type: "button",
      text: confirmLabel,
    });
    const no = h("button", { class: "btn btn--ghost", type: "button", text: "Отмена", on: { click: showTrigger } });
    yes.addEventListener("click", () =>
      busy(yes, onConfirm).catch((error) => {
        toast(`${errorTitle(error)}. ${errorText(error)}`.trim(), "error");
        showTrigger();
      }),
    );
    replace(wrapper, h("span", { class: "confirm__question", text: question }), yes, no);
    no.focus();
  });
  wrapper.append(trigger);
  return wrapper;
}

/** Ошибки валидации 422 подсвечиваются у соответствующих полей формы */
export function showFieldErrors(form, error) {
  form.querySelectorAll(".field__error").forEach((el) => el.remove());
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  const errors = error?.problem?.errors || [];
  let shown = false;
  for (const item of errors) {
    const name = item.loc?.[item.loc.length - 1];
    const input = name ? form.elements.namedItem(String(name)) : null;
    if (!(input instanceof HTMLElement)) continue;
    input.setAttribute("aria-invalid", "true");
    const message = h("p", { class: "field__error", id: `${input.id}-error`, text: validationText(item) });
    input.setAttribute("aria-describedby", message.id);
    input.closest(".field")?.append(message);
    shown = true;
  }
  return shown;
}

function validationText(item) {
  const type = item.type || "";
  if (type.includes("too_short") || type.includes("string_too_short")) return "Слишком короткое значение";
  if (type.includes("too_long")) return "Слишком длинное значение";
  if (type.includes("email") || type === "value_error") return "Некорректный email";
  if (type.includes("pattern")) return "Недопустимые символы";
  return item.msg || "Некорректное значение";
}

export function badge(text, kind = "neutral") {
  return h("span", { class: ["badge", `badge--${kind}`], text });
}

/** Таблица матчей; на узком экране превращается в карточки (S05, крит. 3) */
export function matchesTable(matches, { highlight = [], caption } = {}) {
  const marked = new Set(highlight);
  const row = (m) =>
    h(
      "tr",
      { class: marked.has(m.faceit_match_id) ? "is-highlight" : null },
      h("td", { "data-label": "Дата" }, fmtDateTime(m.finished_at)),
      h("td", { "data-label": "Карта" }, m.map || "нет данных"),
      h(
        "td",
        { "data-label": "Результат" },
        h("span", {
          class: ["result", m.won === true ? "result--win" : m.won === false ? "result--loss" : "result--unknown"],
          text: resultLabel(m.won),
        }),
      ),
      h("td", { "data-label": "Убийства" }, m.kills ?? "—"),
      h("td", { "data-label": "Смерти" }, m.deaths ?? "—"),
      h("td", { "data-label": "K/D" }, matchKd(m)),
      marked.size ? h("td", { "data-label": "Разбор" }, marked.has(m.faceit_match_id) ? "начать с него" : "") : null,
    );
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "table table--matches" },
      caption ? h("caption", { class: "visually-hidden", text: caption }) : null,
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          ["Дата", "Карта", "Результат", "Убийства", "Смерти", "K/D"].map((t) => h("th", { scope: "col", text: t })),
          marked.size ? h("th", { scope: "col", text: "Разбор" }) : null,
        ),
      ),
      h("tbody", {}, matches.map(row)),
    ),
  );
}

/** Карточка показателя с числителем, знаменателем и размером выборки (S02, S06) */
export function metricCard({ label, value, detail, note, testId }) {
  return h(
    "div",
    { class: "metric", "data-testid": testId || null },
    h("p", { class: "metric__label", text: label }),
    h("p", { class: "metric__value", text: value }),
    detail ? h("p", { class: "metric__detail", text: detail }) : null,
    note ? h("p", { class: "metric__note", text: note }) : null,
  );
}

export function field({ label, control, hint }) {
  const hintEl = hint ? h("p", { class: "field__hint", id: `${control.id}-hint`, text: hint }) : null;
  if (hintEl) control.setAttribute("aria-describedby", hintEl.id);
  return h(
    "div",
    { class: "field" },
    h("label", { class: "field__label", for: control.id, text: label }),
    control,
    hintEl,
  );
}
