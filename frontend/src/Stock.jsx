import React, { useEffect, useState } from "react";
import { api, fmt } from "./api.js";
import { IconRefresh } from "./icons.jsx";
import { Spinner, ErrBanner, EmptyState } from "./ui.jsx";

export default function Stock() {
  const [rows,    setRows]    = useState([]);
  const [err,     setErr]     = useState("");
  const [loading, setLoading] = useState(true);
  const [q,       setQ]       = useState("");
  const [bc,      setBc]      = useState("");   // поиск по штрихкоду
  const [stk,     setStk]     = useState("");   // "", "positive", "zero"

  function load() {
    setLoading(true); setErr("");
    api("/api/v1/stock")
      .then(setRows)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  const filtered = rows.filter(r => {
    if (q && !r.name.toLowerCase().includes(q.toLowerCase())) return false;
    if (bc && !(r.barcode || "").includes(bc)) return false;
    const qty = Number(r.quantity);
    if (stk === "positive" && !(qty > 0)) return false;
    if (stk === "zero" && qty > 0) return false;
    return true;
  });

  return (
    <>
      <div className="page-hd"><h2>Остатки</h2></div>

      <div className="filter-card">
        <div className="filter-title">Фильтр</div>
        <div className="filter-grid">
          <div>
            <div className="form-label">Штрихкод</div>
            <input className="input" placeholder="Введите штрихкод" value={bc} onChange={e => setBc(e.target.value)} />
          </div>
          <div>
            <div className="form-label">Наименование</div>
            <input className="input" placeholder="Введите наименование" value={q} onChange={e => setQ(e.target.value)} />
          </div>
          <div>
            <div className="form-label">Остаток</div>
            <select className="input" value={stk} onChange={e => setStk(e.target.value)}>
              <option value="">Все</option>
              <option value="positive">Есть в наличии</option>
              <option value="zero">Нет в наличии</option>
            </select>
          </div>
        </div>
        <div className="filter-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => { setQ(""); setBc(""); setStk(""); }}>Сбросить</button>
        </div>
      </div>

      <ErrBanner message={err} onRetry={load} />

      <div className="table-card">
        <div className="table-toolbar">
          <button className="btn btn-ghost btn-sm" onClick={load}><IconRefresh /> Обновить</button>
        </div>
        {loading ? <Spinner /> : (
          <table>
            <thead>
              <tr>
                <th>Наименование</th>
                <th>Штрихкод</th>
                <th className="num">Остаток</th>
                <th className="num">Цена (сред.)</th>
                <th className="num">Стоимость</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => {
                const qty = Number(r.quantity);
                const price = Number(r.price || 0);
                return (
                  <tr key={r.product_id}>
                    <td className="td-main">{r.name}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 13 }}>{r.barcode || "—"}</td>
                    <td className="num" style={{ fontWeight: 700, color: qty > 0 ? "var(--primary)" : "var(--danger)" }}>
                      {qty.toLocaleString("ru-RU")}
                    </td>
                    <td className="num" title={r.last_price != null ? `Последняя цена: ${fmt(r.last_price)}` : ""}>
                      {price > 0 ? fmt(price) : "—"}
                    </td>
                    <td className="num">{price > 0 ? fmt(qty * price) : "—"}</td>
                    <td>
                      <span className={"chip " + (qty > 0 ? "c-green" : "c-red")}>
                        {qty > 0 ? "В наличии" : "Нет"}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && !err && (
                <EmptyState title="Остатков нет" desc="Данные появятся после приёмки товаров" />
              )}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
