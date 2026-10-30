// Страница игрока: обзор и история (S02–S06), сравнение (S07), карты (S08), сводка (S09–S10)

import { api } from "../api.js";
import { h, nextId, replace } from "../dom.js";
import {
  dateInputToIso,
  describeChange,
  fmtDate,
  fmtDateTime,
  fmtKd,
  fmtPct,
  fmtPeriod,
  matchesDative,
  matchesGenitive,
  matchesWord,
  METRIC_LABELS,
  timeZone,
} from "../format.js";
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
  metricCard,
  notice,
  toast,
} from "../ui.js";
import { goalForm } from "./goal-form.js";

const PAGE = 20;
const TABS = [
  { id: "overview", label: "Обзор и история" },
  { id: "compare", label: "Сравнение 20/20" },
  { id: "maps", label: "Карты" },
  { id: "insights", label: "Сводка и рекомендации" },
];

export async function playerView(main, { args, params, signal }) {
  const id = Number(args[0]);
  replace(main, loading("Загружаем профиль…"));
  let player;
  try {
    player = await api.players.get(id, signal);
  } catch (error) {
    if (signal.aborted || error.status === 401) return;
    replace(
      main,
      h("h1", { text: "Игрок" }),
      errorState(error, {
        onRetry: () => playerView(main, { args, params, signal }),
        action: h("a", { class: "btn btn--ghost", href: "#/players", text: "К списку игроков" }),
      }),
    );
    return;
  }
  if (signal.aborted) return;

  const state = {
    player,
    maps: [],
    signal,
    tab: TABS.some((t) => t.id === params.get("tab")) ? params.get("tab") : "overview",
    filters: {
      map: params.get("map") || "",
      from: params.get("from") || "",
      to: params.get("to") || "",
      page: Math.max(0, Number(params.get("page")) || 0),
    },
  };
  // Список карт нужен фильтрам и форме цели; страница не ждёт его загрузки
  const mapsReady = api.players
    .maps(id, {}, signal)
    .then((result) => {
      state.maps = result.items.map((item) => item.map);
    })
    .catch(() => {});

  const header = h("div");
  const goalSlot = h("div");
  const panel = h("div", { class: "tabpanel", role: "tabpanel", id: "player-tabpanel", tabindex: "0" });
  const tabs = tabList(state, panel, mapsReady);

  state.openGoalForm = async (preset = {}) => {
    await mapsReady;
    replace(goalSlot, goalForm({ player: state.player, maps: state.maps, preset, onClose: () => replace(goalSlot) }));
    goalSlot.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  state.renderHeader = () => replace(header, playerHeader(state));
  state.reloadTab = () => showTab(state, panel, mapsReady);

  state.renderHeader();
  replace(main, header, goalSlot, tabs, panel);
  await showTab(state, panel, mapsReady);
}

function playerHeader(state) {
  const { player } = state;
  const syncStatus = h("div", { class: "player-head__status", "aria-live": "polite" });
  const syncButton = h("button", { class: "btn btn--secondary", type: "button", text: "Обновить из FACEIT" });
  syncButton.addEventListener("click", async () => {
    syncStatus.replaceChildren();
    try {
      state.player = await busy(syncButton, () => api.players.sync(player.id), "Обновляем…");
      toast("Данные обновлены");
      state.renderHeader();
      state.reloadTab();
    } catch (error) {
      if (error.status === 401) return;
      // Сбой источника не превращается в нулевую статистику: показаны сохранённые данные (NFR06)
      syncStatus.append(
        errorState(error, {
          onRetry: () => syncButton.click(),
        }),
        notice(`Показаны сохранённые данные от ${fmtDateTime(player.synced_at)}`, "warn"),
      );
    }
  });

  return h(
    "section",
    { class: "player-head card", "aria-labelledby": "player-name" },
    h(
      "div",
      { class: "player-head__top" },
      h(
        "div",
        {},
        h("p", { class: "eyebrow" }, h("a", { href: "#/players", text: "← Игроки" })),
        h("h1", { id: "player-name", class: "player-head__name", text: player.nickname }),
        h(
          "p",
          { class: "player-head__meta" },
          player.elo !== null ? badge(`ELO ${player.elo}`, "accent") : badge("ELO: нет данных"),
          player.skill_level !== null ? badge(`Уровень ${player.skill_level}`) : null,
          player.country ? badge(player.country.toUpperCase()) : null,
          player.faceit_url
            ? h("a", {
                href: player.faceit_url,
                target: "_blank",
                rel: "noopener noreferrer",
                text: "Профиль на FACEIT ↗",
              })
            : null,
        ),
      ),
      h(
        "div",
        { class: "player-head__actions" },
        syncButton,
        h("button", {
          class: "btn btn--primary",
          type: "button",
          text: "Поставить цель",
          on: { click: () => state.openGoalForm() },
        }),
      ),
    ),
    h(
      "p",
      { class: "player-head__fresh", "data-testid": "synced-at" },
      player.synced_at ? `Данные обновлены: ${fmtDateTime(player.synced_at)}` : "Данные ещё не загружались",
    ),
    player.history_complete
      ? null
      : notice(
          player.coverage_from
            ? `Загружены последние матчи начиная с ${fmtDate(player.coverage_from)}; более ранняя история недоступна (FACEIT отдаёт до 100 последних матчей)`
            : "История загружена не полностью",
          "info",
        ),
    syncStatus,
    noteEditor(state),
    h(
      "div",
      { class: "player-head__danger" },
      confirmButton({
        label: "Удалить игрока",
        question: "Удалить игрока, его матчи и цели?",
        confirmLabel: "Удалить",
        onConfirm: async () => {
          await api.players.remove(player.id);
          toast(`Игрок ${player.nickname} удалён`);
          navigate("/players");
        },
      }),
    ),
  );
}

function noteEditor(state) {
  const box = h("div", { class: "note" });
  const show = () => {
    replace(
      box,
      h("p", { class: "note__text" }, h("span", { class: "muted", text: "Заметка: " }), state.player.note || "нет"),
      h("button", { class: "btn btn--ghost btn--small", type: "button", text: "Изменить", on: { click: edit } }),
    );
  };
  const edit = () => {
    const input = h("input", { id: nextId("note"), type: "text", maxlength: "500", value: state.player.note || "" });
    const status = h("div");
    const save = async (value) => {
      try {
        state.player = await api.players.update(state.player.id, { note: value });
        toast("Заметка сохранена");
        show();
      } catch (error) {
        replace(status, errorState(error));
      }
    };
    const form = h(
      "form",
      {
        class: "note__form",
        on: {
          submit: (e) => {
            e.preventDefault();
            save(input.value.trim() || null);
          },
        },
      },
      field({ label: "Заметка", control: input }),
      h(
        "div",
        { class: "form__actions" },
        h("button", { class: "btn btn--secondary btn--small", type: "submit", text: "Сохранить" }),
        h("button", {
          class: "btn btn--ghost btn--small",
          type: "button",
          text: "Очистить",
          on: { click: () => save(null) },
        }),
        h("button", { class: "btn btn--ghost btn--small", type: "button", text: "Отмена", on: { click: show } }),
      ),
      status,
    );
    replace(box, form);
    input.focus();
  };
  show();
  return box;
}

function tabList(state, panel, mapsReady) {
  const buttons = TABS.map((tab) =>
    h("button", {
      class: "tab",
      type: "button",
      role: "tab",
      id: `tab-${tab.id}`,
      "aria-controls": panel.id,
      "aria-selected": String(tab.id === state.tab),
      tabindex: tab.id === state.tab ? "0" : "-1",
      text: tab.label,
    }),
  );
  const select = (index) => {
    state.tab = TABS[index].id;
    buttons.forEach((b, i) => {
      b.setAttribute("aria-selected", String(i === index));
      b.tabIndex = i === index ? 0 : -1;
    });
    updateQuery({ tab: state.tab === "overview" ? null : state.tab });
    showTab(state, panel, mapsReady);
  };
  buttons.forEach((button, index) => {
    button.addEventListener("click", () => select(index));
    // Стрелки переключают вкладки, как предписывает шаблон WAI-ARIA Tabs
    button.addEventListener("keydown", (event) => {
      const delta = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!delta) return;
      event.preventDefault();
      const next = (index + delta + buttons.length) % buttons.length;
      buttons[next].focus();
      select(next);
    });
  });
  return h("div", { class: "tabs", role: "tablist", "aria-label": "Разделы игрока" }, buttons);
}

async function showTab(state, panel, mapsReady) {
  panel.setAttribute("aria-labelledby", `tab-${state.tab}`);
  replace(panel, loading());
  if (state.tab !== "insights") await mapsReady;
  if (state.signal.aborted) return;
  const views = { overview: overviewTab, compare: compareTab, maps: mapsTab, insights: insightsTab };
  replace(panel, views[state.tab](state));
}

function mapOptions(state, selected) {
  return [
    h("option", { value: "", text: "Все карты" }),
    state.maps.map((m) => h("option", { value: m, text: m, selected: m === selected })),
  ];
}

// --- Обзор и история (S02, S03, S04, S06) ---------------------------------------

function overviewTab(state) {
  const { player, filters, signal } = state;
  const mapSelect = h("select", { id: "filter-map", name: "map" }, mapOptions(state, filters.map));
  const from = h("input", { id: "filter-from", name: "from", type: "date", value: filters.from });
  const to = h("input", { id: "filter-to", name: "to", type: "date", value: filters.to });
  const formStatus = h("div", { class: "form__status" });
  const statsBox = h("div", { class: "overview" });
  const historyBox = h("div", { class: "history" });

  const query = () => ({
    map: filters.map || null,
    date_from: dateInputToIso(filters.from),
    date_to: dateInputToIso(filters.to, true),
  });
  const persist = () =>
    updateQuery({ map: filters.map, from: filters.from, to: filters.to, page: filters.page || null });

  const reset = () => {
    Object.assign(filters, { map: "", from: "", to: "", page: 0 });
    mapSelect.value = "";
    from.value = "";
    to.value = "";
    formStatus.replaceChildren();
    persist();
    load();
  };

  const loadHistory = () =>
    loadInto(
      historyBox,
      () => api.players.matches(player.id, { ...query(), limit: PAGE, offset: filters.page * PAGE }, signal),
      (page) => renderHistory(page),
      { signal, loadingText: "Загружаем матчи…" },
    );

  // Обзор и список строятся по одному и тому же набору фильтров (S04, критерий 1)
  const load = () => {
    loadInto(
      statsBox,
      () => api.players.stats(player.id, query(), signal),
      (stats) => renderStats(state, stats, reset),
      {
        signal,
        loadingText: "Считаем показатели…",
      },
    );
    loadHistory();
  };

  const renderHistory = (page) => {
    if (page.total === 0) return emptyState("Матчей не найдено", "Под выбранные фильтры не подошёл ни один матч.");
    const first = page.offset + 1;
    const last = page.offset + page.items.length;
    const pager = h(
      "nav",
      { class: "pager", "aria-label": "Страницы истории матчей" },
      h("span", { class: "pager__info", text: `Матчи ${first}–${last} из ${page.total}` }),
      page.offset > 0
        ? h("button", {
            class: "btn btn--ghost",
            type: "button",
            text: "← Новее",
            on: {
              click: () => {
                filters.page -= 1;
                persist();
                loadHistory();
              },
            },
          })
        : null,
      last < page.total
        ? h("button", {
            class: "btn btn--ghost",
            type: "button",
            text: "Старее →",
            on: {
              click: () => {
                filters.page += 1;
                persist();
                loadHistory();
              },
            },
          })
        : null,
    );
    return h(
      "div",
      {},
      page.partial_coverage
        ? notice("Период выходит за пределы загруженной истории: список может быть неполным", "warn")
        : null,
      matchesTable(page.items, { caption: "История матчей" }),
      pager,
    );
  };

  const form = h(
    "form",
    {
      class: "filters card",
      "aria-label": "Фильтры матчей",
      on: {
        submit: (event) => {
          event.preventDefault();
          formStatus.replaceChildren();
          if (from.value && to.value && from.value > to.value) {
            formStatus.append(notice("Дата «с» не может быть позже даты «по»", "warn"));
            from.focus();
            return;
          }
          Object.assign(filters, { map: mapSelect.value, from: from.value, to: to.value, page: 0 });
          persist();
          load();
        },
      },
    },
    h(
      "div",
      { class: "filters__row" },
      field({ label: "Карта", control: mapSelect }),
      field({ label: "С даты", control: from }),
      field({ label: "По дату", control: to }),
      h(
        "div",
        { class: "filters__actions" },
        h("button", { class: "btn btn--primary", type: "submit", text: "Применить" }),
        h("button", { class: "btn btn--ghost", type: "button", text: "Сбросить", on: { click: reset } }),
      ),
    ),
    h("p", { class: "field__hint", text: `Границы периода включены. Даты в часовом поясе браузера: ${timeZone}` }),
    formStatus,
  );

  load();
  return h(
    "div",
    { class: "stack" },
    form,
    statsBox,
    h("h2", { class: "section-title", text: "История матчей" }),
    historyBox,
  );
}

function renderStats(state, stats, reset) {
  const resetButton = h("button", {
    class: "btn btn--secondary",
    type: "button",
    text: "Сбросить фильтры",
    on: { click: reset },
  });
  const filtered = Boolean(stats.filters.map || stats.filters.date_from || stats.filters.date_to);
  if (stats.matches_available === 0) {
    // Пустая выборка: показатели предыдущего отбора не остаются на экране (S04, крит. 3)
    return emptyState(
      stats.message || "Матчей нет",
      filtered ? "Измените или сбросьте фильтры." : "",
      filtered ? resetButton : null,
    );
  }
  const wr = stats.win_rate;
  const kd = stats.kd;
  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "metrics" },
      metricCard({
        label: "Матчей в обзоре",
        value: String(stats.matches_count),
        detail: `последние из ${matchesGenitive(stats.matches_available)} под фильтром`,
        testId: "metric-matches",
      }),
      metricCard({
        label: "Доля побед",
        value: fmtPct(wr.value),
        detail: `${wr.numerator} из ${matchesGenitive(wr.denominator)} с известным результатом`,
        note: wr.note,
        testId: "metric-win-rate",
      }),
      metricCard({
        label: "K/D",
        value: fmtKd(kd.value),
        detail: `${kd.numerator} убийств / ${kd.denominator} смертей · по ${matchesDative(kd.sample_size)}`,
        note: kd.note,
        testId: "metric-kd",
      }),
      metricCard({
        label: "Текущий ELO",
        value: state.player.elo !== null ? String(state.player.elo) : "нет данных",
        detail: "исторический график не входит в учебную версию",
      }),
    ),
    h(
      "p",
      { class: "muted" },
      `Период обзора: ${fmtPeriod(stats.period_from, stats.period_to)} · формулы версии ${stats.formula_version}`,
    ),
    stats.message ? notice(stats.message, "info") : null,
    stats.partial_coverage
      ? notice("Выбранный период начинается раньше загруженной истории: показатели посчитаны не по всем матчам", "warn")
      : null,
    h(
      "details",
      { class: "hint" },
      h("summary", { text: "Как считаются показатели" }),
      h(
        "ul",
        {},
        h("li", { text: "Доля побед = победы / матчи с известным результатом × 100%." }),
        h("li", { text: "K/D = сумма убийств / сумма смертей по матчам, где известны оба значения." }),
        h("li", { text: "Отсутствующее значение не считается нулём: матч просто не входит в выборку показателя." }),
        h("li", { text: "При нуле смертей K/D не определён — показаны исходные числа." }),
      ),
    ),
  );
}

// --- Сравнение 20/20 (S07) ------------------------------------------------------

function compareTab(state) {
  const { player, signal } = state;
  const mapSelect = h("select", { id: "compare-map", name: "map" }, mapOptions(state, state.filters.map));
  const box = h("div");
  const load = () =>
    loadInto(
      box,
      () => api.players.compare(player.id, { map: mapSelect.value || null }, signal),
      (data) => renderCompare(state, data),
      {
        signal,
        loadingText: "Сравниваем выборки…",
      },
    );
  mapSelect.addEventListener("change", load);
  load();
  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "card filters" },
      h(
        "div",
        { class: "filters__row" },
        field({ label: "Карта (применяется до разбиения на группы)", control: mapSelect }),
      ),
    ),
    box,
  );
}

function groupCard(title, group) {
  return h(
    "div",
    { class: "card compare__group" },
    h("h3", { class: "card__title", text: title }),
    h("p", {
      class: "muted",
      text: `${fmtPeriod(group.period_from, group.period_to)} · ${matchesWord(group.matches_count)}`,
    }),
    h(
      "dl",
      { class: "facts" },
      h("dt", { text: "Доля побед" }),
      h("dd", {
        text: `${fmtPct(group.win_rate.value)} (${group.win_rate.numerator} из ${group.win_rate.denominator})`,
      }),
      h("dt", { text: "K/D" }),
      h("dd", { text: `${fmtKd(group.kd.value)} (по ${matchesDative(group.kd.sample_size)})` }),
    ),
  );
}

function changeLine(label, change) {
  if (!change.complete) {
    return h(
      "li",
      { class: "change change--none" },
      h("strong", { text: `${label}: ` }),
      "данные есть не во всех 20 матчах каждой группы — значения показаны с фактическим покрытием, вывод о динамике не делается",
    );
  }
  const described = describeChange(change.change, change.unit);
  return h(
    "li",
    { class: ["change", `change--${described.direction}`] },
    h("span", {
      class: "change__arrow",
      "aria-hidden": "true",
      text: { up: "▲", down: "▼", flat: "■", none: "•" }[described.direction],
    }),
    h("strong", { text: `${label}: ` }),
    described.text,
  );
}

function renderCompare(state, data) {
  if (data.status === "insufficient_data") {
    return emptyState(
      "Недостаточно матчей для сравнения",
      data.message,
      h("button", {
        class: "btn btn--secondary",
        type: "button",
        text: "Перейти к обзору",
        on: { click: () => document.getElementById("tab-overview")?.click() },
      }),
    );
  }
  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "compare" },
      groupCard("Последние 20 матчей", data.recent),
      groupCard("Предыдущие 20 матчей", data.previous),
    ),
    h(
      "div",
      { class: "card" },
      h("h3", { class: "card__title", text: "Изменение" }),
      h(
        "ul",
        { class: "changes", "data-testid": "compare-changes" },
        changeLine("Доля побед", data.win_rate),
        changeLine("K/D", data.kd),
      ),
      h("p", {
        class: "muted",
        text: "Доля побед сравнивается в процентных пунктах, K/D — абсолютной разницей. Группы не пересекаются.",
      }),
    ),
  );
}

// --- Карты (S08) ----------------------------------------------------------------

function mapsTab(state) {
  const box = h("div");
  loadInto(box, () => api.players.maps(state.player.id, {}, state.signal), renderMaps, { signal: state.signal });
  return box;
}

function renderMaps(data) {
  if (data.items.length === 0)
    return emptyState("Нет матчей с известной картой", "Обновите данные игрока или дождитесь новых матчей.");
  const rows = data.items.map((item) =>
    h(
      "tr",
      {},
      h("th", { scope: "row", "data-label": "Карта", text: item.map }),
      h("td", { "data-label": "Матчей", text: String(item.matches) }),
      h(
        "td",
        { "data-label": "Доля побед" },
        `${fmtPct(item.win_rate.value)} (${item.win_rate.numerator} из ${item.win_rate.denominator})`,
      ),
      h("td", { "data-label": "K/D" }, `${fmtKd(item.kd.value)} (по ${item.kd.sample_size})`),
      h(
        "td",
        { "data-label": "Выборка" },
        item.enough_data ? badge("достаточно", "ok") : badge(`меньше ${data.min_matches} матчей`, "warn"),
      ),
    ),
  );
  return h(
    "div",
    { class: "stack" },
    h(
      "p",
      { class: "muted" },
      `По ${matchesDative(data.matches_total)} загруженной истории. Выводы по карте делаются только при ${data.min_matches}+ матчах с известным результатом.`,
    ),
    data.unknown_map_matches ? notice(`Матчей без данных о карте: ${data.unknown_map_matches}`, "info") : null,
    h(
      "div",
      { class: "table-wrap" },
      h(
        "table",
        { class: "table table--maps" },
        h("caption", { class: "visually-hidden", text: "Результаты по картам" }),
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            ["Карта", "Матчей", "Доля побед", "K/D", "Выборка"].map((t) => h("th", { scope: "col", text: t })),
          ),
        ),
        h("tbody", {}, rows),
      ),
    ),
  );
}

// --- Сводка и рекомендации (S09, S10) --------------------------------------------

function insightsTab(state) {
  const box = h("div");
  loadInto(
    box,
    () => api.players.insights(state.player.id, state.signal),
    (data) => renderInsights(state, data),
    {
      signal: state.signal,
      loadingText: "Применяем правила…",
    },
  );
  return box;
}

function renderInsights(state, data) {
  const footer = h(
    "p",
    { class: "muted" },
    `Правила версии ${data.rules_version}: A01 — снижение доли побед на 15+ п.п., A02 — снижение K/D на 0,15+, A03 — карта с долей побед до 40% при 10+ матчах. Сервис описывает наблюдения и не утверждает причину поражений.`,
  );
  if (data.status !== "ready") {
    const title =
      data.status === "insufficient_data" ? "Недостаточно данных для сводки" : "Выраженных сигналов не найдено";
    const text =
      data.status === "insufficient_data"
        ? "Нужно 40 матчей для сравнения или 10+ матчей на одной карте. Обычный обзор остаётся доступен."
        : data.message;
    return h("div", { class: "stack" }, emptyState(title, text), footer);
  }
  return h(
    "div",
    { class: "stack" },
    h(
      "ol",
      { class: "insights", role: "list" },
      data.items.map((i) => insightCard(state, i)),
    ),
    footer,
  );
}

function insightCard(state, insight) {
  const evidenceId = nextId("evidence");
  const evidence = h("div", { id: evidenceId, hidden: true });
  const toggle = h("button", {
    class: "btn btn--ghost",
    type: "button",
    "aria-expanded": "false",
    "aria-controls": evidenceId,
    text: `Показать матчи основания (${insight.evidence.length})`,
  });
  toggle.addEventListener("click", () => {
    const open = evidence.hidden;
    evidence.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Скрыть матчи основания" : `Показать матчи основания (${insight.evidence.length})`;
    if (open && !evidence.childElementCount) {
      evidence.append(
        matchesTable(insight.evidence, {
          highlight: insight.review_match_ids,
          caption: `Матчи основания ${insight.rule_id}`,
        }),
      );
    }
  });
  const values =
    insight.before !== null
      ? `${METRIC_LABELS[insight.metric]}: ${formatValue(insight.metric, insight.before)} → ${formatValue(insight.metric, insight.after)} · ${describeChange(insight.change, insight.unit).text}`
      : `${METRIC_LABELS[insight.metric]}: ${formatValue(insight.metric, insight.after)}`;
  return h(
    "li",
    { class: "insight card", "data-testid": "insight", "data-rule": insight.rule_id },
    h("p", { class: "insight__rule" }, badge(insight.rule_id, "accent"), insight.map ? badge(insight.map) : null),
    h("h3", { class: "insight__title", text: insight.title }),
    h("p", {
      class: "muted",
      text: `${values} · ${fmtPeriod(insight.period_from, insight.period_to)} · выборка ${matchesWord(insight.sample_size)}`,
    }),
    h("p", { class: "insight__limit" }, h("strong", { text: "Ограничение: " }), insight.limitation),
    h("p", { class: "insight__action" }, h("strong", { text: "Что сделать: " }), insight.action),
    h(
      "div",
      { class: "insight__actions" },
      h("button", {
        class: "btn btn--primary",
        type: "button",
        text: "Сделать целью",
        on: {
          click: () =>
            state.openGoalForm({
              metric: insight.metric,
              map: insight.map,
              action: insight.action,
              source: insight.rule_id,
            }),
        },
      }),
      toggle,
    ),
    evidence,
  );
}

function formatValue(metric, value) {
  return metric === "win_rate" ? fmtPct(value) : fmtKd(value);
}
