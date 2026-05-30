const TOKEN_KEY = "dara_token";

// Восстанавливаем токен при загрузке модуля — переживает F5/перезагрузку.
let token = (() => { try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; } })();

export function setToken(t) {
  token = t || null;
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch (_) {}
}
export function getToken() { return token; }

// id разговора с агентом (память диалога в рамках сессии)
const CONV_KEY = "dara_conv";
export function getConv() { try { return localStorage.getItem(CONV_KEY) || null; } catch (_) { return null; } }
export function setConv(id) {
  try { id ? localStorage.setItem(CONV_KEY, id) : localStorage.removeItem(CONV_KEY); } catch (_) {}
}

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts = { ...opts, body: JSON.stringify(opts.json) };
    delete opts.json;
  }
  let res;
  try {
    res = await fetch(path, { ...opts, headers });
  } catch (_) {
    throw new Error("Нет связи с сервером. Проверьте подключение.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

export const fmt = (n) =>
  Math.round(Number(n || 0)).toLocaleString("ru-RU") + " ₸";

export const STATUS = {
  new:               ["Новая",                "c-blue"],
  shipped:           ["Отгружен",             "c-amber"],
  receiving:         ["Приёмка",              "c-amber"],
  accepted:          ["Принято",              "c-green"],
  discrepancy:       ["Расхождение",          "c-red"],
  act_created:       ["Акт сформирован",      "c-red"],
  invoice_corrected: ["Счёт скорректирован",  "c-green"],
  closed:            ["Закрыта",              "c-gray"],
  cancelled:         ["Отменена",             "c-gray"],
};
