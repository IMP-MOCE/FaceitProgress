import { api, session } from "../api.js";
import { h } from "../dom.js";
import { navigate } from "../router.js";
import { busy, errorState, field, notice, showFieldErrors } from "../ui.js";

function safeNext(params) {
  const next = params.get("next") || "/players";
  // Только внутренние адреса приложения: защита от открытого редиректа
  return /^\/[a-z0-9/?=&_-]*$/i.test(next) && !next.startsWith("//") ? next : "/players";
}

function authForm({ title, submitLabel, passwordHint, autocomplete, onSubmit, footer, intro }) {
  const email = h("input", {
    id: "auth-email",
    name: "email",
    type: "email",
    required: true,
    autocomplete: "email",
    inputmode: "email",
  });
  const password = h("input", {
    id: "auth-password",
    name: "password",
    type: "password",
    required: true,
    autocomplete,
    minlength: autocomplete === "new-password" ? "8" : null,
    maxlength: "128",
  });
  const status = h("div", { class: "form__status" });
  const submit = h("button", { class: "btn btn--primary btn--block", type: "submit", text: submitLabel });
  const form = h(
    "form",
    { class: "form card", novalidate: true },
    field({ label: "Email", control: email }),
    field({ label: "Пароль", control: password, hint: passwordHint }),
    status,
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.replaceChildren();
    showFieldErrors(form, null);
    if (!email.value.trim() || !password.value) {
      status.append(notice("Введите email и пароль", "warn"));
      (email.value.trim() ? password : email).focus();
      return;
    }
    try {
      await busy(submit, () => onSubmit(email.value.trim(), password.value), "Подождите…");
    } catch (error) {
      if (!showFieldErrors(form, error)) status.append(errorState(error));
    }
  });
  return h(
    "section",
    { class: "auth" },
    h("h1", { class: "auth__title", text: title }),
    intro,
    form,
    h("p", { class: "auth__footer" }, footer),
  );
}

async function signIn(email, password, params) {
  const token = await api.login(email, password);
  session.save(token.access_token, email.toLowerCase());
  navigate(safeNext(params));
}

export function loginView(main, { params }) {
  const intro =
    params.get("reason") === "expired"
      ? notice("Сессия завершена или истекла. Войдите снова — вернём вас на ту же страницу", "warn")
      : h("p", { class: "auth__lead", text: "Аналитика ваших матчей CS2 на FACEIT: обзор, сравнение выборок и цели." });
  main.append(
    authForm({
      title: "Вход",
      submitLabel: "Войти",
      autocomplete: "current-password",
      intro,
      onSubmit: (email, password) => signIn(email, password, params),
      footer: [
        "Нет аккаунта? ",
        h("a", { href: `#/register?next=${encodeURIComponent(safeNext(params))}`, text: "Зарегистрироваться" }),
      ],
    }),
  );
}

export function registerView(main, { params }) {
  main.append(
    authForm({
      title: "Регистрация",
      submitLabel: "Создать аккаунт",
      autocomplete: "new-password",
      passwordHint: "От 8 до 128 символов. Длинная фраза надёжнее сложного короткого пароля",
      intro: h("p", { class: "auth__lead", text: "Аккаунт хранит отслеживаемых игроков и цели." }),
      onSubmit: async (email, password) => {
        await api.register(email, password);
        await signIn(email, password, params);
      },
      footer: ["Уже есть аккаунт? ", h("a", { href: "#/login", text: "Войти" })],
    }),
  );
}
