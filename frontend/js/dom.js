// Построение DOM без innerHTML: пользовательские данные попадают только в textContent

const PROPS = new Set(["value", "checked", "disabled", "selected", "hidden", "id", "type", "name"]);

/**
 * h("button", { class: "btn", on: { click } }, "Текст")
 * Атрибуты aria-*, data-*, for, href и прочие задаются как атрибуты.
 */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = Array.isArray(value) ? value.filter(Boolean).join(" ") : value;
    else if (key === "text") el.textContent = String(value);
    else if (key === "on") {
      for (const [event, handler] of Object.entries(value)) el.addEventListener(event, handler);
    } else if (PROPS.has(key)) el[key] = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function replace(parent, ...children) {
  parent.replaceChildren();
  return append(parent, children);
}

let uid = 0;
export function nextId(prefix = "id") {
  uid += 1;
  return `${prefix}-${uid}`;
}
