export const $ = (id) => document.getElementById(id);
export const pretty = (value) => JSON.stringify(value, null, 2);
export const clone = (value) => structuredClone(value);

export function el(tag, content, attrs = {}) {
  const node = document.createElement(tag);
  Object.assign(node, attrs);
  if (typeof content === "string" || typeof content === "number") node.textContent = content;
  else if (content) node.append(...content.filter((child) => child != null));
  return node;
}

export function button(label, callback, attrs = {}) {
  const node = el("button", label, { type: "button", ...attrs });
  node.addEventListener("click", callback);
  return node;
}

export function select(items, value, callback) {
  const node = el("select", items.map((item) => {
    const [key, label] = Array.isArray(item) ? item : [item, item];
    return el("option", label, { value: key });
  }));
  node.value = String(value ?? "");
  if (callback) node.addEventListener("change", () => callback(node.value));
  return node;
}

export function field(label, input) {
  return el("label", [el("span", label), input], { className: "field" });
}

export function input(value, attrs = {}) {
  return el("input", null, { value: value ?? "", ...attrs });
}

export function number(value, min, max) {
  return input(value, { type: "number", min, max, step: 1, required: true });
}

export function checkbox(value = false) {
  return input("", { type: "checkbox", checked: value });
}

export function textarea(value, rows = 5) {
  return el("textarea", null, { value: pretty(value), rows, spellcheck: false });
}

export function hex(bytes) {
  return "#" + Array.from(bytes, (v) => v.toString(16).padStart(2, "0")).join("");
}

export function rgb(value) {
  return Array.from(value.slice(1).match(/../g), (v) => Number.parseInt(v, 16));
}

export function message(error) {
  try {
    const diagnostics = JSON.parse(String(error));
    return diagnostics.map((d) => d.path ? `${d.path} — ${d.message}` : d.message).join("\n");
  } catch {
    return error?.message ?? String(error);
  }
}

export function details(title, ...children) {
  return el("fieldset", [el("legend", title), ...children]);
}

export function download(bytes, name, type = "application/octet-stream") {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const link = el("a", null, { href: url, download: name });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
