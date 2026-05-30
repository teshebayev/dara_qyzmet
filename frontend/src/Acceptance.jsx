import React, { useState } from "react";
import { api, fmt } from "./api.js";

export default function Acceptance({ orderId, onDone }) {
  const [step, setStep] = useState("upload");
  const [invoice, setInvoice] = useState(null);
  const [accId, setAccId] = useState(null);
  const [file, setFile] = useState(null);
  const [original, setOriginal] = useState(0);
  const [corrected, setCorrected] = useState(0);
  const [drafts, setDrafts] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function upload() {
    setErr("");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file || new Blob(["x"], { type: "image/png" }), "invoice.png");
      const inv = await api(`/api/v1/orders/${orderId}/invoice/upload`, {
        method: "POST",
        body: fd,
      });
      const acc = await api(`/api/v1/orders/${orderId}/acceptance`, { method: "POST" });
      setInvoice(inv);
      setAccId(acc.id);
      setOriginal(Number(inv.total_sum || 0));
      setCorrected(Number(inv.total_sum || 0));
      setStep("review");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function editItem(itemId, field, value) {
    try {
      const inv = await api(`/api/v1/invoice-items/${itemId}`, {
        method: "PATCH",
        json: { [field]: Number(value) },
      });
      setInvoice(inv);
    } catch (e) {
      setErr(e.message);
    }
  }

  function addDraft(item) {
    setDrafts((d) => [
      ...d,
      {
        key: "d" + Date.now(),
        invoice_item_id: item.id,
        name: item.name,
        qty: Number(item.qty),
        price: Number(item.price),
        type: "shortage",
        qty_actual: Number(item.qty),
        saved: null,
      },
    ]);
  }

  function updateDraft(key, patch) {
    setDrafts((d) => d.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  }

  async function saveDraft(dr) {
    setErr("");
    const body = {
      invoice_item_id: dr.invoice_item_id,
      type: dr.type,
      qty_actual: dr.qty_actual,
    };
    if (dr.type === "misgrade") body.price_new = dr.price;
    try {
      const res = await api(`/api/v1/acceptance/${accId}/discrepancies`, {
        method: "POST",
        json: body,
      });
      setOriginal(Number(res.original_sum));
      setCorrected(Number(res.corrected_sum));
      updateDraft(dr.key, { saved: Number(res.total_delta) });
    } catch (e) {
      setErr(e.message);
    }
  }

  async function accept() {
    try {
      await api(`/api/v1/acceptance/${accId}/accept`, { method: "POST" });
      alert("Приёмка подтверждена — товары добавлены в сток");
      onDone();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function makeAct() {
    try {
      const a = await api(`/api/v1/acceptance/${accId}/act`, { method: "POST" });
      alert(
        `Акт ${a.number}\nПо накладной: ${fmt(a.original_sum)}\nК оплате: ${fmt(
          a.corrected_sum
        )}\nРазница: ${fmt(a.total_delta)}`
      );
      onDone();
    } catch (e) {
      setErr(e.message);
    }
  }

  if (step === "upload") {
    return (
      <>
        <h2>Приёмка</h2>
        <div className="card">
          <div className="row">
            <b>Загрузите фото или PDF накладной</b>
            <input type="file" accept="image/*,application/pdf" onChange={(e) => setFile(e.target.files[0])} />
            <button className="btn btn-green btn-sm" disabled={busy} onClick={upload}>
              {busy ? "Распознаю…" : "Распознать"}
            </button>
            <button className="btn btn-white btn-sm" onClick={onDone}>
              Назад
            </button>
          </div>
          <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>
            В демо-режиме (mock) распознавание вернёт типовую накладную независимо от файла.
          </div>
          {err && <div className="err">{err}</div>}
        </div>
      </>
    );
  }

  return (
    <>
      <h2>Приёмка по накладной</h2>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <b>
            {invoice.supplier_name || "—"} · № {invoice.invoice_number || "—"} ·{" "}
            {invoice.invoice_date || ""}
          </b>
          <span className="chip c-green">распознано</span>
        </div>
        <table style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>Товар</th>
              <th className="num">Кол-во</th>
              <th className="num">Цена</th>
              <th className="num">Сумма</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {invoice.items.map((it) => (
              <tr key={it.id}>
                <td>
                  {it.name}
                  {it.was_edited && <span style={{ color: "var(--green)" }}> ●</span>}
                </td>
                <td className="num">
                  <input
                    className={"cell " + (it.confidence < 0.8 ? "low" : "")}
                    defaultValue={it.qty}
                    onBlur={(e) => editItem(it.id, "qty", e.target.value)}
                  />
                </td>
                <td className="num">
                  <input
                    className={"cell " + (it.confidence < 0.8 ? "low" : "")}
                    defaultValue={it.price}
                    onBlur={(e) => editItem(it.id, "price", e.target.value)}
                  />
                </td>
                <td className="num">{fmt(it.line_total)}</td>
                <td className="num">
                  <button className="btn btn-white btn-sm" onClick={() => addDraft(it)}>
                    расхождение
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 style={{ fontSize: 18 }}>Расхождения</h2>
      <div className="card">
        {drafts.length === 0 && (
          <div className="muted" style={{ fontSize: 13 }}>
            Пока нет. Нажмите «расхождение» у позиции.
          </div>
        )}
        {drafts.map((dr) => (
          <div className="disc" key={dr.key}>
            <div>
              <b>{dr.name}</b>
              <br />
              <span className="muted" style={{ fontSize: 12 }}>
                накладная: {dr.qty} × {dr.price}
              </span>
            </div>
            <input
              className="cell"
              defaultValue={dr.qty_actual}
              onChange={(e) => updateDraft(dr.key, { qty_actual: Number(e.target.value) })}
            />
            <div className="seg">
              {["shortage", "misgrade"].map((t) => (
                <button
                  key={t}
                  className={dr.type === t ? "on " + t : ""}
                  onClick={() => updateDraft(dr.key, { type: t })}
                >
                  {t === "shortage" ? "недостача" : "пересорт"}
                </button>
              ))}
            </div>
            <button className="btn btn-green btn-sm" onClick={() => saveDraft(dr)}>
              сохранить
            </button>
            {dr.saved != null && (
              <span className={"delta " + (dr.saved < 0 ? "minus" : "plus")}>
                итог изменён: {dr.saved < 0 ? "− " : "+ "}
                {Math.abs(Math.round(dr.saved)).toLocaleString("ru-RU")} ₸
              </span>
            )}
          </div>
        ))}

        <div className="totbar">
          <div style={{ textAlign: "right" }}>
            <div className="l">По накладной</div>
            <div className="v" style={{ fontSize: 16 }}>
              {fmt(original)}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="l">К оплате</div>
            <div className={"v " + (corrected !== original ? "green" : "")}>{fmt(corrected)}</div>
          </div>
        </div>

        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
          <button className="btn btn-white" onClick={makeAct}>
            Сформировать акт
          </button>
          <button className="btn btn-green" onClick={accept}>
            Подтвердить приёмку
          </button>
        </div>
        {err && <div className="err">{err}</div>}
      </div>
    </>
  );
}
