import React, { useEffect, useState } from "react";
import { api } from "./api.js";

const MAX = 5;

// Отдельная страница: добавление фото товара с разных сторон (до 5) для поиска по фото.
export default function ProductPhotos({ product, onBack }) {
  const [count, setCount]       = useState(null);
  const [previews, setPreviews] = useState([]);   // локальные превью загруженного в этой сессии
  const [busy, setBusy]         = useState(false);
  const [err, setErr]           = useState("");

  useEffect(() => {
    api(`/api/v1/products/${product.id}/photos`)
      .then(r => setCount(r.photos))
      .catch(() => setCount(0));
  }, [product.id]);

  async function addFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setErr(""); setBusy(true);
    for (const f of files) {
      try {
        const fd = new FormData();
        fd.append("file", f, f.name);
        const r = await api(`/api/v1/products/${product.id}/photo`, { method: "POST", body: fd });
        setCount(r.photos);
        setPreviews(p => [...p, URL.createObjectURL(f)]);
      } catch (e) {
        setErr(e.message);   // например, 409 «Достигнут лимит 5 фото»
        break;
      }
    }
    setBusy(false);
  }

  async function clearAll() {
    setBusy(true); setErr("");
    try {
      await api(`/api/v1/products/${product.id}/photos`, { method: "DELETE" });
      setCount(0); setPreviews([]);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  const remaining = count == null ? MAX : Math.max(0, MAX - count);

  return (
    <>
      <div className="page-hd">
        <h2>Фото товара</h2>
        <button className="btn btn-outline btn-sm" onClick={onBack}>← К товарам</button>
      </div>

      <div className="table-card" style={{ padding: 22 }}>
        <div style={{ fontSize: 16, fontWeight: 600 }}>{product.name}</div>
        <div className="text-muted text-sm" style={{ marginTop: 4, marginBottom: 16 }}>
          Штрихкод: {product.barcode || "—"} · ракурсов: {count == null ? "…" : `${count}/${MAX}`}
        </div>
        <div className="text-muted text-sm" style={{ marginBottom: 14 }}>
          Добавьте до {MAX} фото с разных сторон — чем больше ракурсов, тем точнее поиск по фото.
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label className="btn btn-primary"
            style={{ cursor: (busy || remaining === 0) ? "not-allowed" : "pointer", opacity: (busy || remaining === 0) ? 0.6 : 1 }}>
            {busy ? "Загрузка…" : (remaining === 0 ? "Лимит достигнут" : "📷 Добавить фото")}
            <input type="file" accept="image/*" multiple hidden
              disabled={busy || remaining === 0}
              onChange={e => { addFiles(e.target.files); e.target.value = ""; }} />
          </label>
          {count > 0 && (
            <button className="btn btn-outline" disabled={busy} onClick={clearAll}>Удалить все</button>
          )}
        </div>

        {err && <div className="err-msg">{err}</div>}

        {previews.length > 0 && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 18 }}>
            {previews.map((src, i) => (
              <img key={i} src={src} alt=""
                style={{ width: 120, height: 120, objectFit: "cover", borderRadius: 10, border: "1px solid var(--border)" }} />
            ))}
          </div>
        )}

        <div className="text-muted text-sm" style={{ marginTop: 16 }}>
          Превью показывает фото, добавленные в этой сессии. Сами изображения хранятся как
          векторы (эмбеддинги) для поиска, а не как файлы.
        </div>
      </div>
    </>
  );
}
