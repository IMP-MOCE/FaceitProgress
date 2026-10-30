// Цели: список, исходная выборка и проверка динамики (S11, S12)

import { api } from "../api.js";
import { h, nextId, replace } from "../dom.js";
import { describeChange, fmtDateTime, fmtMetric, fmtPeriod, matchesWord, METRIC_LABELS } from "../format.js";
import { navigate, updateQuery } from "../router.js";
import {
  badge,
  busy,
  confirmButton,
  emptyState,
  errorState,
  field,
  loadInto,
  loading,
  matchesTable,
  notice,
  toast,
} from "../ui.js";

const STATUS_LABELS = { active: "Активна", completed: "Завершена", archived: "В архиве" };
const STATUS_KIND = { active: "accent", completed: "ok", archived: "neutral" };

export function goalsView(main, { params, signal }) {
  const status = ["active", "completed", "archived"].includes(params.get("status")) ? params.get("status") : "";
  const list = h("div");
  const select = h(
    "select",
    { id: "goals-status", name: "status" },
    h("option", { value: "", text: "Все" }),
    Object.entries(STATUS_LABELS).map(([value, label]) =>
      h("option", { value, text: label, selected: value === status }),
    ),
  );
  const load = () =>
    loadInto(list, () => api.goals.list({ status: select.value || null, limit: 100 }, signal), renderGoals, { signal });
  select.addEventListener("change", () => {
    updateQuery({ status: select.value || null });
    load();
  });
  main.append(
    h("div", { class: "page-head" }, h("h1", { text: "Цели" })),
    h(
      "p",
      { class: "muted" },
      "Одновременно активна одна цель. Её исходные 20 матчей сохраняются и не меняются при обновлении истории.",
    ),
    h(
      "div",
      { class: "card filters" },
      h("div", { class: "filters__row" }, field({ label: "Статус", control: select })),
    ),
    list,
  );
  return load();
}

function renderGoals(page) {
  if (page.total === 0) {
    return emptyState(
      "Целей пока нет",
      "Откройте игрока, перейдите в «Сводку и рекомендации» и нажмите «Сделать целью» — или поставьте цель вручную.",
      h("a", { class: "btn btn--secondary", href: "#/players", text: "К игрокам" }),
    );
  }
  return h(
    "ul",
    { class: "goal-list", role: "list" },
    page.items.map((goal) =>
      h(
        "li",
        { class: "card goal-card", "data-testid": "goal-card" },
        h(
          "p",
          { class: "goal-card__meta" },
          badge(STATUS_LABELS[goal.status], STATUS_KIND[goal.status]),
          badge(METRIC_LABELS[goal.metric]),
          goal.map ? badge(goal.map) : null,
        ),
        h("a", { class: "goal-card__action", href: `#/goals/${goal.id}`, text: goal.action }),
        h("p", {
          class: "muted",
          text: `Поставлена ${fmtDateTime(goal.started_at)} · исходно ${fmtMetric(goal.metric, goal.baseline.value)}`,
        }),
      ),
    ),
  );
}

export async function goalView(main, { args, signal }) {
  const id = Number(args[0]);
  replace(main, loading("Загружаем цель…"));
  let goal;
  let player;
  try {
    goal = await api.goals.get(id, signal);
    player = await api.players.get(goal.player_id, signal).catch(() => null);
  } catch (error) {
    if (signal.aborted || error.status === 401) return;
    replace(
      main,
      h("h1", { text: "Цель" }),
      errorState(error, {
        onRetry: () => goalView(main, { args, signal }),
        action: h("a", { class: "btn btn--ghost", href: "#/goals", text: "Ко всем целям" }),
      }),
    );
    return;
  }
  if (signal.aborted) return;
  const progressBox = h("div", { "data-testid": "goal-progress" });
  const ctx = { goal, player, progressBox, signal, main, args };
  replace(
    main,
    goalHeader(ctx),
    baselineSection(goal),
    h("h2", { class: "section-title", text: "Динамика" }),
    progressBox,
  );
  await loadProgress(ctx);
}

function goalHeader(ctx) {
  const { goal, player } = ctx;
  const actionText = h("p", { class: "goal-head__action", text: goal.action });
  const status = h("div", { class: "form__status" });

  const editAction = () => {
    const input = h("textarea", { id: nextId("action"), rows: "3", maxlength: "500" });
    input.value = goal.action;
    const save = h("button", { class: "btn btn--secondary btn--small", type: "submit", text: "Сохранить" });
    const form = h(
      "form",
      {},
      field({ label: "Действие", control: input }),
      h(
        "div",
        { class: "form__actions" },
        save,
        h("button", {
          class: "btn btn--ghost btn--small",
          type: "button",
          text: "Отмена",
          on: { click: () => form.replaceWith(actionText) },
        }),
      ),
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const updated = await busy(save, () => api.goals.update(goal.id, { action: input.value.trim() }));
        goal.action = updated.action;
        actionText.textContent = updated.action;
        form.replaceWith(actionText);
        toast("Действие обновлено");
      } catch (error) {
        replace(status, errorState(error));
      }
    });
    actionText.replaceWith(form);
    input.focus();
  };

  const close = (newStatus, label) =>
    h("button", {
      class: "btn btn--secondary",
      type: "button",
      text: label,
      on: {
        click: async (event) => {
          try {
            await busy(event.currentTarget, () => api.goals.update(goal.id, { status: newStatus }));
            toast(newStatus === "completed" ? "Цель завершена" : "Цель перенесена в архив");
            goalView(ctx.main, { args: ctx.args, signal: ctx.signal });
          } catch (error) {
            replace(status, errorState(error));
          }
        },
      },
    });

  return h(
    "section",
    { class: "card goal-head", "aria-labelledby": "goal-title" },
    h("p", { class: "eyebrow" }, h("a", { href: "#/goals", text: "← Цели" })),
    h("h1", { id: "goal-title", text: `Цель: ${METRIC_LABELS[goal.metric]}${goal.map ? ` на ${goal.map}` : ""}` }),
    h(
      "p",
      { class: "goal-card__meta" },
      badge(STATUS_LABELS[goal.status], STATUS_KIND[goal.status]),
      player ? h("a", { href: `#/players/${player.id}`, text: `Игрок ${player.nickname}` }) : null,
      h("span", {
        class: "muted",
        text: `поставлена ${fmtDateTime(goal.started_at)} · формулы v${goal.formula_version}`,
      }),
    ),
    actionText,
    h(
      "div",
      { class: "form__actions" },
      h("button", { class: "btn btn--ghost", type: "button", text: "Изменить действие", on: { click: editAction } }),
      goal.status === "active" ? close("completed", "Завершить") : null,
      goal.status === "active" ? close("archived", "В архив") : null,
      confirmButton({
        label: "Удалить",
        question: "Удалить цель вместе со снимками?",
        confirmLabel: "Удалить",
        onConfirm: async () => {
          await api.goals.remove(goal.id);
          toast("Цель удалена");
          navigate("/goals");
        },
      }),
    ),
    status,
    h("p", {
      class: "muted",
      text: "Изменение показателя — наблюдение, а не обещание роста ELO и не доказательство эффекта тренировки.",
    }),
  );
}

function baselineSection(goal) {
  const matches = [...goal.baseline_matches].reverse();
  const period = matches.length ? fmtPeriod(matches[matches.length - 1].finished_at, matches[0].finished_at) : "—";
  return h(
    "section",
    { class: "card", "aria-labelledby": "baseline-title" },
    h("h2", { id: "baseline-title", class: "card__title", text: "Исходная точка" }),
    h("p", { class: "big-value", "data-testid": "goal-baseline-value" }, fmtMetric(goal.metric, goal.baseline.value)),
    h(
      "p",
      { class: "muted" },
      `${goal.baseline.numerator} / ${goal.baseline.denominator} · ${matchesWord(goal.baseline.sample_size)} · ${period}`,
    ),
    h(
      "details",
      { class: "hint" },
      h("summary", { text: `Состав исходной выборки (${matches.length})` }),
      matchesTable(matches, { caption: "Исходная выборка цели" }),
    ),
  );
}

async function loadProgress(ctx) {
  const { goal, progressBox, signal } = ctx;
  return loadInto(
    progressBox,
    () => api.goals.progress(goal.id, signal),
    (progress) => renderProgress(ctx, progress),
    {
      signal,
      loadingText: "Проверяем матчи после постановки цели…",
    },
  );
}

function syncAndReload(ctx) {
  const button = h("button", { class: "btn btn--secondary", type: "button", text: "Обновить данные игрока" });
  button.addEventListener("click", async () => {
    try {
      await busy(button, () => api.players.sync(ctx.goal.player_id), "Обновляем…");
      toast("История обновлена");
      loadProgress(ctx);
    } catch (error) {
      button.after(errorState(error));
    }
  });
  return button;
}

function progressBar(share) {
  const bar = h("span", { class: "progress__bar" });
  // Ширина задаётся через CSSOM: inline-атрибут style запрещён политикой CSP
  bar.style.width = `${Math.min(100, Math.round(share * 100))}%`;
  return bar;
}

function renderProgress(ctx, progress) {
  const { goal } = ctx;
  if (progress.status === "collecting") {
    return h(
      "div",
      { class: "card stack" },
      h("p", { class: "state__title", text: progress.message }),
      h(
        "div",
        {
          class: "progress",
          role: "progressbar",
          "aria-valuemin": "0",
          "aria-valuemax": String(progress.required),
          "aria-valuenow": String(progress.collected),
          "aria-label": "Набрано матчей после постановки цели",
        },
        progressBar(progress.collected / progress.required),
      ),
      h("p", {
        class: "muted",
        text: "Сравнение появится, когда после постановки цели будет сыграно 20 матчей в её контексте.",
      }),
      syncAndReload(ctx),
    );
  }
  if (progress.status === "incomplete_data") {
    return h(
      "div",
      { class: "card stack" },
      notice(progress.message, "warn"),
      h("p", {
        text: `Матчи без данных: ${progress.missing_match_ids.join(", ")}. Более поздние матчи вместо них не подставляются.`,
      }),
    );
  }
  if (progress.status === "unrecoverable") {
    return h(
      "div",
      { class: "card stack" },
      notice(progress.message, "warn"),
      goal.status === "active"
        ? confirmButton({
            label: "Заменить цель с новой исходной точкой",
            question: "Текущая цель уйдёт в архив, исходная точка будет взята по последним 20 матчам.",
            confirmLabel: "Заменить",
            danger: false,
            onConfirm: async () => {
              const created = await api.goals.create({
                player_id: goal.player_id,
                metric: goal.metric,
                map: goal.map,
                action: goal.action,
                replace_active: true,
              });
              toast("Цель заменена");
              navigate(`/goals/${created.id}`);
            },
          })
        : null,
    );
  }
  const change = describeChange(progress.change, progress.change_unit);
  // Ухудшение и отсутствие изменений показаны так же явно, как рост (S12, крит. 6)
  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "card" },
      h(
        "div",
        { class: "progress-result" },
        h(
          "div",
          {},
          h("p", { class: "metric__label", text: "Было" }),
          h("p", { class: "big-value", text: fmtMetric(goal.metric, progress.baseline.value) }),
        ),
        h("p", { class: "progress-result__arrow", "aria-hidden": "true", text: "→" }),
        h(
          "div",
          {},
          h("p", { class: "metric__label", text: "Стало" }),
          h("p", { class: "big-value", text: fmtMetric(goal.metric, progress.followup.value) }),
        ),
      ),
      h(
        "p",
        { class: ["change", `change--${change.direction}`], "data-testid": "goal-change" },
        h("strong", { text: "Изменение: " }),
        change.text,
      ),
      h("p", { class: "muted", text: progress.message }),
    ),
    h(
      "details",
      { class: "hint" },
      h("summary", { text: `Матчи после постановки цели (${progress.followup_matches.length})` }),
      matchesTable(progress.followup_matches, { caption: "Новая выборка" }),
    ),
  );
}
