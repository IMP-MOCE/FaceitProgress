// Постановка цели: из рекомендации (S10 → S11) или вручную

import { api } from "../api.js";
import { h, nextId, replace } from "../dom.js";
import { fmtMetric, fmtPeriod, matchesWord, METRIC_LABELS } from "../format.js";
import { navigate } from "../router.js";
import { busy, errorState, field, notice, showFieldErrors, toast } from "../ui.js";

/**
 * @param {object} options
 * @param {object} options.player
 * @param {string[]} options.maps   карты с матчами игрока
 * @param {object} [options.preset] { metric, map, action, source }
 * @param {() => void} options.onClose
 */
export function goalForm({ player, maps, preset = {}, onClose }) {
  const titleId = nextId("goal-form");
  const metricName = nextId("metric");
  const metricInputs = ["win_rate", "kd"].map((value) =>
    h("input", {
      type: "radio",
      name: "metric",
      id: `${metricName}-${value}`,
      value,
      checked: (preset.metric || "win_rate") === value,
    }),
  );
  const mapSelect = h(
    "select",
    { id: nextId("goal-map"), name: "map" },
    h("option", { value: "", text: "Все карты" }),
    maps.map((m) => h("option", { value: m, text: m, selected: preset.map === m })),
  );
  const action = h("textarea", {
    id: nextId("goal-action"),
    name: "action",
    rows: "3",
    maxlength: "500",
    required: true,
    placeholder: "Например: пересмотреть 3 поражения на de_mirage и выписать повторяющиеся ситуации",
  });
  action.value = preset.action || "";
  const preview = h("div", { class: "goal-form__preview", "aria-live": "polite" });
  const replaceBox = h("div", { class: "goal-form__replace" });
  const status = h("div", { class: "form__status" });
  const submit = h("button", { class: "btn btn--primary", type: "submit", text: "Сохранить цель" });
  const cancel = h("button", { class: "btn btn--ghost", type: "button", text: "Отмена", on: { click: onClose } });

  const form = h(
    "form",
    { class: "card form goal-form", novalidate: true, "aria-labelledby": titleId },
    h("h2", { id: titleId, class: "card__title", text: "Новая цель" }),
    preset.source ? h("p", { class: "muted", text: `Основание: рекомендация ${preset.source}` }) : null,
    h(
      "fieldset",
      { class: "field" },
      h("legend", { class: "field__label", text: "Показатель для отслеживания" }),
      h(
        "div",
        { class: "radio-row" },
        metricInputs.map((input) =>
          h("label", { class: "radio", for: input.id }, input, h("span", { text: METRIC_LABELS[input.value] })),
        ),
      ),
    ),
    field({ label: "Карта", control: mapSelect }),
    field({ label: "Что вы будете делать", control: action }),
    preview,
    replaceBox,
    status,
    h("div", { class: "form__actions" }, submit, cancel),
  );

  const metric = () => metricInputs.find((i) => i.checked)?.value || "win_rate";

  // Перед сохранением показываем исходную точку: значение, число матчей, период (S11, крит. 2)
  let previewToken = 0;
  async function updatePreview() {
    const token = ++previewToken;
    replace(preview, notice("Считаем исходную точку…"));
    try {
      const stats = await api.players.stats(player.id, { map: mapSelect.value || null });
      if (token !== previewToken) return;
      const value = stats[metric()];
      const enough = stats.matches_count >= 20 && value.sample_size >= 20;
      replace(
        preview,
        h(
          "p",
          { class: ["notice", enough ? "notice--info" : "notice--warn"], "data-testid": "goal-baseline" },
          enough
            ? `Исходная точка: ${METRIC_LABELS[metric()]} ${fmtMetric(metric(), value.value)} по 20 матчам, ${fmtPeriod(stats.period_from, stats.period_to)}. После сохранения она не изменится.`
            : `Для цели нужно 20 матчей с полными данными по показателю; сейчас ${matchesWord(value.sample_size)}.`,
        ),
      );
    } catch {
      if (token === previewToken)
        replace(
          preview,
          notice("Не удалось рассчитать исходную точку — сервер проверит данные при сохранении", "warn"),
        );
    }
  }
  mapSelect.addEventListener("change", updatePreview);
  metricInputs.forEach((i) => i.addEventListener("change", updatePreview));
  updatePreview();

  let replaceActive = null;
  function offerReplace(activeId) {
    replaceActive = h("input", { type: "checkbox", id: nextId("replace"), name: "replace_active" });
    replace(
      replaceBox,
      h(
        "div",
        { class: "notice notice--warn" },
        h("p", {}, "У вас уже есть активная цель. ", h("a", { href: `#/goals/${activeId}`, text: "Открыть её" })),
        h(
          "label",
          { class: "checkbox", for: replaceActive.id },
          replaceActive,
          h("span", { text: "Заменить текущую цель: она уйдёт в архив, а исходная точка будет сохранена заново" }),
        ),
      ),
    );
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.replaceChildren();
    showFieldErrors(form, null);
    if (action.value.trim().length < 3) {
      status.append(notice("Опишите действие — хотя бы 3 символа", "warn"));
      action.focus();
      return;
    }
    const body = {
      player_id: player.id,
      metric: metric(),
      map: mapSelect.value || null,
      action: action.value.trim(),
      replace_active: Boolean(replaceActive?.checked),
    };
    try {
      const goal = await busy(submit, () => api.goals.create(body), "Сохраняем…");
      toast("Цель сохранена");
      navigate(`/goals/${goal.id}`);
    } catch (error) {
      if (error.status === 409 && error.problem?.active_goal_id) {
        offerReplace(error.problem.active_goal_id);
        status.append(notice("Отметьте замену и сохраните ещё раз, или закройте текущую цель", "warn"));
        replaceActive.focus();
        return;
      }
      if (!showFieldErrors(form, error)) status.append(errorState(error));
    }
  });

  setTimeout(() => action.focus(), 0);
  return form;
}
