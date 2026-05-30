import React, { useEffect, useState } from "react";
import { api, STATUS, fmt } from "./api.js";
import { IconRefresh, IconPlus, IconArrow } from "./icons.jsx";
import { Spinner, ErrBanner, EmptyState } from "./ui.jsx";
import CreateOrder from "./CreateOrder.jsx";

export default function Orders({ onAccept }) {
  const [orders,   setOrders]   = useState([]);
  const [err,      setErr]      = useState("");
  const [loading,  setLoading]  = useState(true);
  const [creating, setCreating] = useState(false);
  const [detail,   setDetail]   = useState(null);
  const [fStatus,  setFStatus]  = useState("");
  const [fFrom,    setFFrom]     = useState("");
  const [fTo,      setFTo]       = useState("");

  function load() {
    setLoading(true); setErr("");
    api("/api/v1/orders")
      .then(setOrders)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function openDetail(id) {
    try { setDetail(await api(`/api/v1/orders/${id}`)); }
    catch (e) { setErr(e.message); }
  }

  const shown = orders.filter(o => {
    if (fStatus && o.status !== fStatus) return false;
    const d = (o.created_at || "").slice(0, 10);
    if (fFrom && d < fFrom) return false;
    if (fTo && d > fTo) return false;
    return true;
  });

  return (
    <>
      <div className="page-hd"><h2>Заявки</h2></div>

      <div className="filter-card">
        <div className="filter-title">Фильтр</div>
        <div className="filter-grid">
          <div>
            <div className="form-label">Статус</div>
            <select className="input" value={fStatus} onChange={e => setFStatus(e.target.value)}>
              <option value="">Все статусы</option>
              {Object.entries(STATUS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </div>
          <div>
            <div className="form-label">Дата от</div>
            <input className="input" type="date" value={fFrom} onChange={e => setFFrom(e.target.value)} />
          </div>
          <div>
            <div className="form-label">Дата до</div>
            <input className="input" type="date" value={fTo} onChange={e => setFTo(e.target.value)} />
          </div>
        </div>
        <div className="filter-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => { setFStatus(""); setFFrom(""); setFTo(""); }}>Сбросить</button>
        </div>
      </div>

      <ErrBanner message={err} onRetry={load} />

      <div className="table-card">
        <div className="table-toolbar">
          <button className="btn btn-ghost btn-sm" onClick={load}><IconRefresh /> Обновить</button>
          <button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>
            <IconPlus /> Создать заявку
          </button>
        </div>
        {loading ? <Spinner /> : (
          <table>
            <thead>
              <tr>
                <th>№ Заявки</th><th>Дата</th><th>Позиций</th><th>Статус</th>
                <th style={{ textAlign: "right" }}>Действие</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(o => {
                const [label, cls] = STATUS[o.status] || [o.status, "c-gray"];
                const canAccept = o.status === "shipped" || o.status === "receiving";
                return (
                  <tr key={o.id} style={{ cursor: "pointer" }} onClick={() => openDetail(o.id)}>
                    <td className="td-main" style={{ fontFamily: "monospace", fontSize: 13 }}>
                      #{o.id.slice(0, 8).toUpperCase()}
                    </td>
                    <td className="text-muted text-sm">{new Date(o.created_at).toLocaleDateString("ru-RU")}</td>
                    <td>{o.items.length} поз.</td>
                    <td><span className={"chip " + cls}>{label}</span></td>
                    <td className="num" onClick={e => e.stopPropagation()}>
                      {canAccept && (
                        <button className="btn btn-primary btn-xs" onClick={() => onAccept(o.id)}>
                          Начать приёмку <IconArrow />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {shown.length === 0 && !err && (
                <EmptyState
                  title={orders.length ? "Ничего не найдено" : "Заявок пока нет"}
                  desc={orders.length ? "Измените условия фильтра" : "Создайте первую заявку на приёмку товара"}
                  action={<button className="btn btn-primary btn-sm" onClick={() => setCreating(true)}><IconPlus /> Создать заявку</button>}
                />
              )}
            </tbody>
          </table>
        )}
      </div>

      {creating && <CreateOrder onCreated={() => { setCreating(false); load(); }} onCancel={() => setCreating(false)} />}

      {detail && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(16,24,40,.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div style={{ background: "#fff", borderRadius: 14, width: "100%", maxWidth: 560, maxHeight: "85vh", overflow: "auto", boxShadow: "0 24px 48px rgba(16,24,40,.18)" }}>
            <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <strong style={{ fontSize: 15 }}>#{detail.id.slice(0, 8).toUpperCase()}</strong>
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{new Date(detail.created_at).toLocaleDateString("ru-RU")}</div>
              </div>
              <button onClick={() => setDetail(null)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 22, color: "var(--muted)" }}>×</button>
            </div>
            <div style={{ padding: 24 }}>
              <span className={"chip " + (STATUS[detail.status]?.[1] || "c-gray")} style={{ marginBottom: 16, display: "inline-block" }}>
                {STATUS[detail.status]?.[0] || detail.status}
              </span>
              <table style={{ width: "100%", marginTop: 8 }}>
                <thead>
                  <tr>
                    <th style={{ padding: "8px 0", fontSize: 11, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", borderBottom: "1px solid var(--border)", textAlign: "left" }}>Товар</th>
                    <th style={{ padding: "8px 0", fontSize: 11, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", borderBottom: "1px solid var(--border)", textAlign: "right" }}>Кол-во</th>
                    <th style={{ padding: "8px 0", fontSize: 11, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", borderBottom: "1px solid var(--border)", textAlign: "right" }}>Цена</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map(it => (
                    <tr key={it.id}>
                      <td style={{ padding: "10px 0", borderBottom: "1px solid var(--border)", fontSize: 14 }}>{it.name}</td>
                      <td style={{ padding: "10px 0", borderBottom: "1px solid var(--border)", textAlign: "right", fontSize: 14 }}>{Number(it.qty_ordered).toLocaleString("ru-RU")}</td>
                      <td style={{ padding: "10px 0", borderBottom: "1px solid var(--border)", textAlign: "right", fontSize: 14 }}>{it.price ? fmt(it.price) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
                <button className="btn btn-outline" onClick={() => setDetail(null)}>Закрыть</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
