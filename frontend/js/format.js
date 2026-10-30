// Форматирование чисел и дат для русскоязычного интерфейса

export const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

const dateTime = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const dateOnly = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

export function fmtDateTime(iso) {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function fmtDate(iso) {
  return iso ? dateOnly.format(new Date(iso)) : "—";
}

export function fmtPeriod(from, to) {
  if (!from || !to) return "—";
  return `${fmtDate(from)} – ${fmtDate(to)}`;
}

function number(value, digits) {
  return value.toLocaleString("ru-RU", {
    minimumFractionDigits: digits.min,
    maximumFractionDigits: digits.max,
  });
}

export function fmtPct(value) {
  if (value === null || value === undefined) return "нет данных";
  return `${number(value, { min: 0, max: 1 })}%`;
}

export function fmtKd(value) {
  if (value === null || value === undefined) return "нет данных";
  return number(value, { min: 2, max: 2 });
}

export function fmtMetric(metric, value) {
  return metric === "win_rate" ? fmtPct(value) : fmtKd(value);
}

export const METRIC_LABELS = { win_rate: "Доля побед", kd: "K/D" };

/** Изменение словами и знаком: цвет в интерфейсе только дублирует текст (S05, крит. 6) */
export function describeChange(change, unit) {
  if (change === null || change === undefined) {
    return { text: "изменение не определено", direction: "none" };
  }
  const abs = Math.abs(change);
  const value = unit === "pp" ? `${number(abs, { min: 0, max: 2 })} п.п.` : number(abs, { min: 2, max: 2 });
  if (change > 0) return { text: `+${value} (рост)`, direction: "up" };
  if (change < 0) return { text: `−${value} (снижение)`, direction: "down" };
  return { text: "без изменений", direction: "flat" };
}

export function plural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function matchesWord(n) {
  return `${n} ${plural(n, "матч", "матча", "матчей")}`;
}

/** «из 21 матча», «из 20 матчей» */
export function matchesGenitive(n) {
  return `${n} ${plural(n, "матча", "матчей", "матчей")}`;
}

/** «по 21 матчу», «по 20 матчам» */
export function matchesDative(n) {
  return `${n} ${plural(n, "матчу", "матчам", "матчам")}`;
}

/** Значение input[type=date] → ISO 8601 с поясом браузера; границы периода включены */
export function dateInputToIso(value, endOfDay = false) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = endOfDay ? new Date(year, month - 1, day, 23, 59, 59, 999) : new Date(year, month - 1, day, 0, 0, 0, 0);
  return date.toISOString();
}

export function resultLabel(won) {
  if (won === true) return "Победа";
  if (won === false) return "Поражение";
  return "Нет данных";
}

export function matchKd(match) {
  if (match.kills === null || match.deaths === null) return "нет данных";
  if (match.deaths === 0) return `${match.kills}/0`;
  return fmtKd(match.kills / match.deaths);
}
