import React, { useEffect, useRef, useState } from "react";
import { api, STATUS } from "./api.js";
import { IconRefresh, IconFilePdf } from "./icons.jsx";
import { Spinner, ErrBanner, EmptyState } from "./ui.jsx";
import ReceiptDocument from "./ReceiptDocument.jsx";
import ShipDialog from "./ShipDialog.jsx";
import { exportNodeToPdf } from "./pdfExport.js";

export default function Shipments() {
  const [orders,  setOrders]  = useState([]);
  const [err,     setErr]     = useState("");
  const [loading, setLoading] = useState(true);
  const [receipt, setReceipt] = useState(null);   // данные приходного ордера
  const [shipId, setShipId]   = useState(null);   // открытый диалог отгрузки
  const [exporting, setExporting] = useState(false);
  const [fStatus, setFStatus] = useState("");
  const [fDate,   setFDate]   = useState("");
  const docRef = useRef(null);

  function load() {
    setLoading(true); setErr("");
    api("/api/v1/orders")
      .then(setOrders)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function openReceipt(id) {
    setErr("");
    try { setReceipt(await api(`/api/v1/orders/${id}/receipt`)); }
    catch (e) { setErr(e.message); }
  }

  const shown = orders.filter(o => {
    if (fStatus && o.status !== fStatus) return false;
    if (fDate && (o.created_at || "").slice(0, 10) !== fDate) return false;
    return true;
  });

  async function printPdf() {
    if (!docRef.current) return;
    setExporting(true);
    try {
      const r = await exportNodeToPdf(docRef.current, `Приходный_ордер_${(receipt.number || "").replace("#", "")}.pdf`);
      if (r?.fallback) alert("Библиотека PDF не загрузилась — открыт диалог печати (сохраните как PDF).");
    } catch (e) { alert("Не удалось сформировать PDF: " + e.message); }
    finally { setExporting(false); }
  }

  return (
    <>
      <div className="page-hd"><h2>Отгрузка</h2></div>

      <div className="filter-card">
        <div className="filter-title">Фильтр</div>
        <div className="filter-grid filter-grid-2">
          <div>
            <div className="form-label">Статус</div>
            <select className="input" value={fStatus} onChange={e => setFStatus(e.target.value)}>
              <option value="">Все</option>
              {Object.entries(STATUS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </div>
          <div>
            <div className="form-label">Дата</div>
            <input className="input" type="date" value={fDate} onChange={e => setFDate(e.target.value)} />
          </div>
        </div>
        <div className="filter-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => { setFStatus(""); setFDate(""); }}>Сбросить</button>
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
                <th>№ Заявки</th><th>Дата</th><th>Позиций</th><th>Статус</th>
                <th style={{ textAlign: "right" }}>Действие</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(o => {
                const [label, cls] = STATUS[o.status] || [o.status, "c-gray"];
                return (
                  <tr key={o.id}>
                    <td className="td-main" style={{ fontFamily: "monospace", fontSize: 13 }}>
                      #{o.id.slice(0, 8).toUpperCase()}
                    </td>
                    <td className="text-muted text-sm">{new Date(o.created_at).toLocaleDateString("ru-RU")}</td>
                    <td>{o.items.length} поз.</td>
                    <td><span className={"chip " + cls}>{label}</span></td>
                    <td className="num" style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      {o.status === "new" && (
                        <button className="btn btn-primary btn-xs" onClick={() => setShipId(o.id)}>Отгрузить</button>
                      )}
                      <button className="btn btn-outline btn-xs" onClick={() => openReceipt(o.id)}>
                        <IconFilePdf size={13} /> Накладная
                      </button>
                    </td>
                  </tr>
                );
              })}
              {shown.length === 0 && !err && (
                <EmptyState
                  title={orders.length ? "Ничего не найдено" : "Заявок нет"}
                  desc={orders.length ? "Измените условия фильтра" : "Заявки от магазинов появятся здесь"}
                />
              )}
            </tbody>
          </table>
        )}
      </div>

      {shipId && (
        <ShipDialog
          orderId={shipId}
          onShipped={() => { setShipId(null); load(); }}
          onCancel={() => setShipId(null)}
        />
      )}

      {receipt && (
        <div className="modal-overlay" onClick={() => setReceipt(null)}>
          <div className="modal-card modal-wide" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <strong>Приходный ордер {receipt.number}</strong>
              <div className="flex gap-8">
                <button className="btn btn-primary btn-sm" disabled={exporting} onClick={printPdf}>
                  <IconFilePdf size={14} /> {exporting ? "Готовлю…" : "Печать / PDF"}
                </button>
                <button className="btn btn-outline btn-sm" onClick={() => setReceipt(null)}>Закрыть</button>
              </div>
            </div>
            <div className="modal-body po-scroll">
              <ReceiptDocument ref={docRef} data={receipt} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
