import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { IconRefresh, IconScan } from "./icons.jsx";
import { Spinner, ErrBanner, EmptyState } from "./ui.jsx";

export default function Products({ role, onOpenPhotos }) {
  const isStore = role === "store";
  const [products, setProducts] = useState([]);
  const [stock,    setStock]    = useState({});
  const [q,        setQ]        = useState("");
  const [bc,       setBc]       = useState("");
  const [err,      setErr]      = useState("");
  const [loading,  setLoading]  = useState(true);
  const [recOpen,  setRecOpen]  = useState(false);   // модалка распознавания
  const [recBusy,  setRecBusy]  = useState(false);
  const [recRes,   setRecRes]   = useState(null);

  async function recognize(fileObj) {
    if (!fileObj) return;
    setRecBusy(true); setRecRes(null);
    try {
      const fd = new FormData();
      fd.append("file", fileObj, fileObj.name);
      setRecRes(await api("/api/v1/products/recognize-image", { method: "POST", body: fd }));
    } catch (e) { setRecRes({ error: e.message }); }
    finally { setRecBusy(false); }
  }

  function load() {
    setLoading(true); setErr("");
    Promise.all([
      api("/api/v1/products"),
      api("/api/v1/stock"),
    ]).then(([prods, stockRows]) => {
      setProducts(prods);
      const map = {};
      stockRows.forEach(r => { map[r.product_id] = r.quantity; });
      setStock(map);
    }).catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  const filtered = products.filter(p => {
    if (q && !p.name.toLowerCase().includes(q.toLowerCase())) return false;
    if (bc && !(p.barcode || "").includes(bc)) return false;
    return true;
  });

  return (
    <>
      <div className="page-hd"><h2>Товары</h2></div>

      <div className="filter-card">
        <div className="filter-title">Фильтр</div>
        <div className="filter-grid">
          <div>
            <div className="form-label">Наименование</div>
            <input className="input" placeholder="Введите наименование" value={q} onChange={e => setQ(e.target.value)} />
          </div>
          <div>
            <div className="form-label">Штрихкод</div>
            <input className="input" placeholder="Введите штрихкод" value={bc} onChange={e => setBc(e.target.value)} />
          </div>
        </div>
        <div className="filter-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => { setQ(""); setBc(""); }}>Сбросить</button>
        </div>
      </div>

      <ErrBanner message={err} onRetry={load} />

      <div className="table-card">
        <div className="table-toolbar">
          <button className="btn btn-ghost btn-sm" onClick={load}><IconRefresh /> Обновить</button>
          <button className="btn btn-primary btn-sm" onClick={() => { setRecRes(null); setRecOpen(true); }}>
            <IconScan size={14} /> Распознать по фото
          </button>
        </div>
        {loading ? <Spinner /> : (
          <table>
            <thead>
              <tr>
                <th>Наименование</th><th>Штрихкод</th><th>Ед. изм.</th>
                <th className="num">Остаток</th>{isStore && <th>Фото</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => {
                const qty = stock[p.id];
                const hasStock = qty != null && Number(qty) > 0;
                return (
                  <tr key={p.id}>
                    <td className="td-main">{p.name}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 13 }}>{p.barcode || "—"}</td>
                    <td>{p.unit}</td>
                    <td className="num">
                      {qty != null ? (
                        <span style={{ fontWeight: 600, color: hasStock ? "var(--primary)" : "var(--danger)" }}>
                          {Number(qty).toLocaleString("ru-RU")} {p.unit}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    {isStore && (
                      <td>
                        <button className="btn btn-outline btn-xs"
                          onClick={() => onOpenPhotos && onOpenPhotos({ id: p.id, name: p.name, barcode: p.barcode })}>
                          📷 Фото{p.image_url ? " ●" : ""}
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
              {filtered.length === 0 && !err && (
                <EmptyState title="Товаров нет" desc={q ? `По запросу «${q}» ничего не найдено` : "Каталог пуст"} />
              )}
            </tbody>
          </table>
        )}
      </div>

      {recOpen && (
        <div className="modal-overlay" onClick={() => setRecOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="modal-head">
              <strong>Распознавание по фото</strong>
              <button onClick={() => setRecOpen(false)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "var(--muted)" }}>×</button>
            </div>
            <div className="modal-body">
              <div className="text-muted text-sm" style={{ marginBottom: 10 }}>
                Загрузите фото товара — найдём похожие в каталоге (эмбеддинги) и оценим количество единиц (VLM).
              </div>
              <input type="file" accept="image/*" disabled={recBusy}
                onChange={e => recognize(e.target.files[0])} />
              {recBusy && <div style={{ marginTop: 12 }}><Spinner /></div>}
              {recRes && !recBusy && (
                <div style={{ marginTop: 14 }}>
                  {recRes.error ? (
                    <div className="err-msg">{recRes.error}</div>
                  ) : (
                    <>
                      <div style={{ marginBottom: 8 }}>
                        Распознано: <b>{recRes.recognized_name || "—"}</b>
                        {recRes.count != null && <> · единиц на фото: <b>{recRes.count}</b></>}
                      </div>
                      <div className="form-label">Похожие товары:</div>
                      {(recRes.matches || []).length === 0 ? (
                        <div className="text-muted text-sm">Совпадений в каталоге нет.</div>
                      ) : (
                        <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
                          {recRes.matches.map((m, i) => (
                            <li key={i}>{m.name} <span className="text-muted">(score {Number(m.score).toFixed(2)})</span></li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
