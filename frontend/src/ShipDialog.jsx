import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// Отгрузка от имени поставщика: проставить цену (необязательно) и привязать
// позицию к товару каталога — тогда подтягивается штрихкод (в приходный ордер).
export default function ShipDialog({ orderId, onShipped, onCancel }) {
  const [items, setItems]       = useState([]);
  const [products, setProducts] = useState([]);
  const [busy, setBusy]         = useState(false);
  const [err, setErr]           = useState("");

  useEffect(() => {
    Promise.all([
      api(`/api/v1/orders/${orderId}`),
      api(`/api/v1/orders/${orderId}/catalog`).catch(() => []),
    ]).then(([o, cat]) => {
      setProducts(cat);
      setItems(o.items.map((it) => {
        const m = it.product_id
          ? cat.find((p) => p.id === it.product_id)
          : cat.find((p) => p.name === it.name);
        return {
          id: it.id,
          name: it.name,
          qty: Number(it.qty_ordered),
          product_id: m ? m.id : (it.product_id || ""),
          barcode: m ? (m.barcode || "") : "",
          price: it.price != null ? Number(it.price) : "",
        };
      }));
    }).catch((e) => setErr(e.message));
  }, [orderId]);

  function pickProduct(i, pid) {
    const p = products.find((x) => x.id === pid);
    setItems((arr) => arr.map((x, idx) =>
      idx === i ? { ...x, product_id: pid || "", barcode: p ? (p.barcode || "") : "" } : x));
  }
  function setPrice(i, v) {
    setItems((arr) => arr.map((x, idx) => idx === i ? { ...x, price: v } : x));
  }

  async function ship() {
    setBusy(true); setErr("");
    try {
      await api(`/api/v1/orders/${orderId}/ship`, {
        method: "POST",
        json: {
          items: items.map((it) => ({
            item_id: it.id,
            product_id: it.product_id || null,
            price: it.price !== "" && it.price != null ? Number(it.price) : null,
          })),
        },
      });
      onShipped();
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card modal-wide" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 820 }}>
        <div className="modal-head">
          <strong>Отгрузка заявки</strong>
          <button onClick={onCancel} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "var(--muted)" }}>×</button>
        </div>
        <div className="modal-body">
          <div className="text-muted text-sm" style={{ marginBottom: 12 }}>
            Привяжите позиции к товарам каталога (подтянется штрихкод) и при необходимости укажите цену.
          </div>
          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", fontSize: 11, color: "var(--muted)", textTransform: "uppercase", padding: "6px 8px" }}>Позиция</th>
                <th style={{ textAlign: "right", fontSize: 11, color: "var(--muted)", textTransform: "uppercase", padding: "6px 8px", width: 70 }}>Кол-во</th>
                <th style={{ textAlign: "left", fontSize: 11, color: "var(--muted)", textTransform: "uppercase", padding: "6px 8px" }}>Товар (каталог)</th>
                <th style={{ textAlign: "left", fontSize: 11, color: "var(--muted)", textTransform: "uppercase", padding: "6px 8px", width: 140 }}>Штрихкод</th>
                <th style={{ textAlign: "right", fontSize: 11, color: "var(--muted)", textTransform: "uppercase", padding: "6px 8px", width: 110 }}>Цена</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={it.id}>
                  <td style={{ padding: "6px 8px" }}>{it.name}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right" }}>{it.qty}</td>
                  <td style={{ padding: "6px 8px" }}>
                    <select className="input" style={{ fontSize: 13, padding: "6px 8px" }}
                      value={it.product_id} onChange={(e) => pickProduct(i, e.target.value)}>
                      <option value="">— не выбран —</option>
                      {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </td>
                  <td style={{ padding: "6px 8px", fontFamily: "monospace", fontSize: 13, color: it.barcode ? "var(--ink)" : "var(--muted)" }}>
                    {it.barcode || "—"}
                  </td>
                  <td style={{ padding: "6px 8px" }}>
                    <input className="input" style={{ fontSize: 13, padding: "6px 8px", textAlign: "right" }}
                      type="number" min="0" placeholder="0 ₸"
                      value={it.price} onChange={(e) => setPrice(i, e.target.value)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {err && <div className="err-msg">{err}</div>}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
            <button className="btn btn-outline" onClick={onCancel}>Отмена</button>
            <button className="btn btn-primary" disabled={busy} onClick={ship}>
              {busy ? "Отгружаем…" : "Отгрузить"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
