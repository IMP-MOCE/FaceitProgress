import { api, onUnauthorized, session } from "./api.js";
import { navigate, parseHash, route, startRouter } from "./router.js";
import { toast } from "./ui.js";
import { accountView } from "./views/account.js";
import { loginView, registerView } from "./views/auth.js";
import { goalView, goalsView } from "./views/goals.js";
import { playerView } from "./views/player.js";
import { playersView } from "./views/players.js";

route(/^\/login$/, loginView, { auth: false });
route(/^\/register$/, registerView, { auth: false });
route(/^\/players$/, playersView, { nav: "players" });
route(/^\/players\/(\d+)$/, playerView, { nav: "players" });
route(/^\/goals$/, goalsView, { nav: "goals" });
route(/^\/goals\/(\d+)$/, goalView, { nav: "goals" });
route(/^\/account$/, accountView, { nav: "account" });

// Истёкший или отозванный токен: возврат на вход с сохранением адреса
onUnauthorized(() => {
  const { path } = parseHash();
  if (!/^\/(login|register)/.test(path)) {
    navigate(`/login?next=${encodeURIComponent(path)}&reason=expired`);
  }
});

document.querySelector("[data-action=logout]")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await api.logout();
  } catch {
    // Даже если сервер недоступен, локальная сессия завершается
  } finally {
    button.disabled = false;
    session.clear();
    toast("Вы вышли из аккаунта");
    navigate("/login");
  }
});

startRouter();
