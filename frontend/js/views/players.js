import { api } from "../api.js";
import { h, replace } from "../dom.js";
import { fmtDateTime } from "../format.js";
import { navigate } from "../router.js";
import { busy, confirmButton, emptyState, errorState, field, loadInto, notice, toast } from "../ui.js";

const PAGE = 20;
const DEMO_HINT =
  "Без ключа FACEIT доступны демо-профили: demo_player, patchy_player (пропуски данных), " +
  "newbie_player (меньше 20 матчей), no_cs2_player (нет матчей CS2). Ник source_down имитирует сбой FACEIT.";

export function playersView(main, { params, signal }) {
  const list = h("div", { class: "players" });
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  main.append(
    h("div", { class: "page-head" }, h("h1", { text: "Игроки" })),
    addPlayerForm(),
    h("h2", { class: "section-title", text: "Отслеживаемые профили" }),
    list,
  );
  return loadInto(
    list,
    () => api.players.list({ limit: PAGE, offset }, signal),
    (page) => renderList(page, offset),
    {
      signal,
    },
  );
}

function addPlayerForm() {
  const query = h("input", {
    id: "player-query",
    name: "query",
    type: "text",
    autocomplete: "off",
    spellcheck: "false",
    maxlength: "255",
    placeholder: "s1mple или https://www.faceit.com/ru/players/…",
  });
  const note = h("input", {
    id: "player-note",
    name: "note",
    type: "text",
    maxlength: "500",
    placeholder: "Например: мой основной аккаунт",
  });
  const submit = h("button", { class: "btn btn--primary", type: "submit", text: "Найти и добавить" });
  const status = h("div", { class: "form__status", "aria-live": "polite" });

  const form = h(
    "form",
    { class: "card form form--inline", novalidate: true, "aria-labelledby": "add-player-title" },
    h("h2", { id: "add-player-title", class: "card__title", text: "Добавить игрока" }),
    h(
      "div",
      { class: "form__row" },
      field({ label: "Ник или ссылка на профиль FACEIT", control: query }),
      field({ label: "Заметка (необязательно)", control: note }),
    ),
    h("div", { class: "form__actions" }, submit),
    status,
    h("details", { class: "hint" }, h("summary", { text: "Демо-профили" }), h("p", { text: DEMO_HINT })),
  );

  const run = async () => {
    status.replaceChildren();
    const value = query.value.trim();
    // Пустой ввод не запускает поиск (S01, критерий 2)
    if (!value) {
      status.append(notice("Введите ник или ссылку на профиль FACEIT", "warn"));
      query.setAttribute("aria-invalid", "true");
      query.focus();
      return;
    }
    query.removeAttribute("aria-invalid");
    try {
      const player = await busy(
        submit,
        () => api.players.create({ query: value, note: note.value.trim() || null }),
        "Ищем на FACEIT…",
      );
      toast(`Игрок ${player.nickname} добавлен`);
      navigate(`/players/${player.id}`);
    } catch (error) {
      status.append(addError(error, run));
      if (error.status === 404 || error.status === 422) query.focus();
    }
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run();
  });
  return form;
}

function addError(error, retry) {
  // «Не найден» и «источник недоступен» выглядят по-разному (S01, критерии 3–4)
  if (error.status === 404) {
    return h(
      "div",
      { class: "state state--error", role: "alert", "data-status": "404" },
      h("p", { class: "state__title", text: "Игрок не найден" }),
      h("p", { class: "state__text", text: `${error.detail}. Проверьте ник или ссылку и измените запрос` }),
    );
  }
  if (error.status === 503 || error.status === 0) return errorState(error, { onRetry: retry });
  if (error.status === 409)
    return errorState(error, { action: h("a", { class: "btn btn--ghost", href: "#/players", text: "К списку" }) });
  return errorState(error);
}

function renderList(page, offset) {
  if (page.total === 0) {
    return emptyState(
      "Вы пока не отслеживаете игроков",
      "Введите ник или ссылку на профиль FACEIT в форме выше — сервис загрузит историю матчей CS2.",
    );
  }
  const items = h("ul", { class: "player-list", role: "list" }, page.items.map(playerCard));
  const from = offset + 1;
  const to = offset + page.items.length;
  const pager = h(
    "nav",
    { class: "pager", "aria-label": "Страницы списка игроков" },
    h("span", { class: "pager__info", text: `${from}–${to} из ${page.total}` }),
    offset > 0
      ? h("a", { class: "btn btn--ghost", href: `#/players?offset=${Math.max(0, offset - PAGE)}`, text: "← Назад" })
      : null,
    to < page.total
      ? h("a", { class: "btn btn--ghost", href: `#/players?offset=${offset + PAGE}`, text: "Далее →" })
      : null,
  );
  return h("div", {}, items, page.total > PAGE ? pager : null);
}

function playerCard(player) {
  const card = h(
    "li",
    { class: "player-card card", "data-testid": "player-card" },
    h(
      "div",
      { class: "player-card__main" },
      h("a", { class: "player-card__name", href: `#/players/${player.id}`, text: player.nickname }),
      h(
        "p",
        { class: "player-card__meta" },
        player.elo !== null ? `ELO ${player.elo}` : "ELO: нет данных",
        player.skill_level !== null ? ` · уровень ${player.skill_level}` : "",
      ),
      h("p", {
        class: "player-card__meta muted",
        text: player.synced_at ? `Обновлено ${fmtDateTime(player.synced_at)}` : "Ещё не обновлялся",
      }),
      player.note ? h("p", { class: "player-card__note", text: player.note }) : null,
    ),
    h(
      "div",
      { class: "player-card__actions" },
      h("a", { class: "btn btn--secondary", href: `#/players/${player.id}`, text: "Открыть" }),
      confirmButton({
        label: "Удалить",
        question: `Удалить ${player.nickname} вместе с матчами и целями?`,
        confirmLabel: "Удалить",
        onConfirm: async () => {
          await api.players.remove(player.id);
          toast(`Игрок ${player.nickname} удалён`);
          const list = card.parentElement;
          card.remove();
          if (list && list.children.length === 0) {
            replace(list.parentElement, emptyState("Вы пока не отслеживаете игроков", "Добавьте игрока в форме выше."));
          }
        },
      }),
    ),
  );
  return card;
}
