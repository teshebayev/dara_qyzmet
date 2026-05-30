// Тонкий клиент к бэкенду. Токен хранится в памяти модуля.
let token = null;

export function setToken(t) {
  token = t;
}

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts = { ...opts, body: JSON.stringify(opts.json) };
    delete opts.json;
  }
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}

export const fmt = (n) =>
  Math.round(Number(n || 0)).toLocaleString("ru-RU") + " ₸";

export const STATUS = {
  new: ["Новая", "c-blue"],
  shipped: ["Отгружен", "c-amber"],
  receiving: ["Приёмка", "c-amber"],
  accepted: ["Принято", "c-green"],
  discrepancy: ["Расхождение", "c-red"],
  act_created: ["Акт сформирован", "c-red"],
  invoice_corrected: ["Счёт скорректирован", "c-green"],
  closed: ["Закрыта", "c-gray"],
  cancelled: ["Отменена", "c-gray"],
};
