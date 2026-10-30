import { api, session } from "../api.js";
import { h } from "../dom.js";
import { fmtDateTime } from "../format.js";
import { navigate } from "../router.js";
import { confirmButton, loadInto, toast } from "../ui.js";

export function accountView(main, { signal }) {
  const body = h("div");
  main.append(h("h1", { text: "Аккаунт" }), body);
  return loadInto(
    body,
    () => api.me(signal),
    (user) =>
      h(
        "div",
        { class: "card stack" },
        h(
          "dl",
          { class: "facts" },
          h("dt", { text: "Email" }),
          h("dd", { text: user.email }),
          h("dt", { text: "Зарегистрирован" }),
          h("dd", { text: fmtDateTime(user.created_at) }),
        ),
        h("p", {
          class: "muted",
          text: "Удаление аккаунта удаляет всех отслеживаемых игроков, их матчи и цели. Отменить действие нельзя.",
        }),
        confirmButton({
          label: "Удалить аккаунт",
          question: "Удалить аккаунт и все данные?",
          confirmLabel: "Да, удалить навсегда",
          onConfirm: async () => {
            await api.deleteMe();
            session.clear();
            toast("Аккаунт удалён");
            navigate("/register");
          },
        }),
      ),
    { signal },
  );
}
