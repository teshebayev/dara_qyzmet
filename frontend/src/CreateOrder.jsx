import React, { useEffect, useState } from "react";
import { api, fmt } from "./api.js";
import { IconPlus } from "./icons.jsx";

export default function CreateOrder({ onCreated, onCancel }) {
  const [suppliers, setSuppliers] = useState([]);
  const [products,  setProducts]  = useState([]);
  const [suppId,    setSuppId]    = useState("");
  const [items,     setItems]     = useState([{ name: "", qty_ordered: 1, price: "", product_id: null }]);
  const [err,       setErr]       = useState("");
  const [busy,      setBusy]      = useState(false);

  useEffect(() => {
    api("/api/v1/suppliers").then(setSuppliers).catch(() => {});
    api("/api/v1/products").then(setProducts).catch(() => {});
  }, []);

  function updateItem(i, patch) {
    setItems(it => it.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  }

  function addItem() {
    setItems(it => [...it, { name: "", qty_ordered: 1, price: "", product_id: null }]);
  }

  function removeItem(i) {
    setItems(it => it.filter((_, idx) => idx !== i));
  }

  async function submit() {
    if (!suppId) return setErr("Выберите поставщика");
    if (items.some(it => !it.name)) return setErr("Заполните наименование всех позиций");
    setErr(""); setBusy(true);
    try {
      const order = await api("/api/v1/orders", {
        method: "POST",
        json: {
          supplier_org_id: suppId,
          items: items.map(it => ({
            name: it.name,
            qty_ordered: Number(it.qty_ordered),
            price: it.price ? Number(it.price) : null,
            product_id: it.product_id || null,
          })),
        },
      });
      onCreated(order);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(16,24,40,.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ background: "#fff", borderRadius: 14, width: "100%", maxWidth: 640, maxHeight: "90vh", overflow: "auto", boxShadow: "0 24px 48px rgba(16,24,40,.18)" }}>
        <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 16 }}>Создать заявку</strong>
          <button onClick={onCancel} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "var(--muted)" }}>×</button>
        </div>

        <div style={{ padding: 24 }}>
          <div className="form-field">
            <label className="form-label">Поставщик</label>
            <select className="form-input" value={suppId} onChange={e => setSuppId(e.target.value)}>
              <option value="">Выберите поставщика</option>
              {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <label className="form-label" style={{ margin: 0 }}>Позиции</label>
              <button className="btn btn-outline btn-xs" onClick={addItem}><IconPlus /> Добавить</button>
            </div>

            <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
              <table style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ padding: "8px 12px", fontSize: 11, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", background: "#FAFAFA", borderBottom: "1px solid var(--border)", textAlign: "left" }}>Наименование</th>
                    <th style={{ padding: "8px 12px", fontSize: 11, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", background: "#FAFAFA", borderBottom: "1px solid var(--border)", textAlign: "right", width: 100 }}>Кол-во</th>
                    <th style={{ width: 32, background: "#FAFAFA", borderBottom: "1px solid var(--border)" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, i) => (
                    <tr key={i}>
                      <td style={{ padding: "8px 10px", borderBottom: i < items.length - 1 ? "1px solid var(--border)" : "none" }}>
                        <input
                          className="input" style={{ fontSize: 13, padding: "6px 8px" }}
                          placeholder="Название товара"
                          value={it.name}
                          onChange={e => updateItem(i, { name: e.target.value })}
                          list={`prod-list-${i}`}
                        />
                        <datalist id={`prod-list-${i}`}>
                          {products.map(p => <option key={p.id} value={p.name} />)}
                        </datalist>
                      </td>
                      <td style={{ padding: "8px 6px", borderBottom: i < items.length - 1 ? "1px solid var(--border)" : "none" }}>
                        <input
                          className="input" style={{ fontSize: 13, padding: "6px 8px", textAlign: "right" }}
                          type="number" min="1" value={it.qty_ordered}
                          onChange={e => updateItem(i, { qty_ordered: e.target.value })}
                        />
                      </td>
                      <td style={{ padding: "8px 6px", textAlign: "center", borderBottom: i < items.length - 1 ? "1px solid var(--border)" : "none" }}>
                        {items.length > 1 && (
                          <button onClick={() => removeItem(i)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--danger)", fontSize: 16 }}>×</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {err && <div className="err-msg">{err}</div>}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
            <button className="btn btn-outline" onClick={onCancel}>Отмена</button>
            <button className="btn btn-primary" disabled={busy} onClick={submit}>
              {busy ? "Создаём…" : "Создать заявку"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
