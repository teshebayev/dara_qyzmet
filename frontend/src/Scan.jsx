import React, { useEffect, useRef, useState } from "react";
import { api, fmt } from "./api.js";
import { IconSparkles, IconCheck, IconArrow, IconFilePdf, IconScan, IconAlert, IconPrint } from "./icons.jsx";
import ActDocument from "./ActDocument.jsx";
import { exportNodeToPdf, printNode } from "./pdfExport.js";

const MONTHS = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];

const TYPES = [
  { id: "ok",       label: "Норма" },
  { id: "shortage", label: "Недостача" },
  { id: "surplus",  label: "Излишек" },
  { id: "misgrade", label: "Пересорт" },
  { id: "defect",   label: "Брак" },
];

// dqty — количество самого расхождения (брака / недостачи / излишка / пересорта).
// Из него считаем принятое кол-во (qtyFact) и сумму к оплате.
function computeLine(l) {
  const d = Math.max(0, Number(l.dqty) || 0);
  const doc = Number(l.qtyDoc) || 0;
  const price = Number(l.price) || 0;
  const pnew = Number(l.priceNew) || 0;
  let qtyFact, paySum;
  switch (l.type) {
    case "shortage": qtyFact = Math.max(0, doc - d); paySum = qtyFact * price; break;
    case "surplus":  qtyFact = doc + d;              paySum = qtyFact * price; break;
    case "defect":   qtyFact = Math.max(0, doc - d); paySum = qtyFact * price; break;
    case "misgrade": qtyFact = d;                    paySum = d * pnew;         break;
    default:         qtyFact = doc;                  paySum = doc * price;      break;
  }
  const docSum = doc * price;
  return { ...l, dqty: d, qtyFact, docSum, paySum, delta: paySum - docSum };
}

const DQTY_LABEL = {
  shortage: "шт недостачи", surplus: "шт излишка",
  defect: "шт брака", misgrade: "шт пересорта",
};

export default function Scan({ orderId, orders = [], onDone }) {
  const [step, setStep]   = useState(orderId ? "upload" : "select");
  const [allOrders, setAllOrders] = useState(orders);
  const [order, setOrder] = useState(orders.find((o) => o.id === orderId) || null);

  const [file, setFile]       = useState(null);
  const [invoice, setInvoice] = useState(null);
  const [accId, setAccId]     = useState(null);
  const [check, setCheck]     = useState(null);

  const [lines, setLines]     = useState([]);
  const [act, setAct]         = useState(null);
  const [receipt, setReceipt] = useState(null);   // реальные контрагенты (магазин/поставщик) из БД
  const [busy, setBusy]       = useState(false);
  const [err, setErr]         = useState("");
  const [exporting, setExporting] = useState(false);
  const actRef = useRef(null);

  // Подтягиваем список заявок и, если передан orderId, восстанавливаем сам объект
  // заявки (из «Заявки» приходит только id) — иначе recognize() думает, что заявка не выбрана.
  useEffect(() => {
    if (orders.length) return;
    api("/api/v1/orders").then((list) => {
      setAllOrders(list);
      if (orderId) {
        const found = list.find((o) => o.id === orderId);
        if (found) setOrder(found);
      }
    }).catch(() => {});
  }, []); // eslint-disable-line

  // Реальные стороны (получатель-магазин + отправитель-поставщик) с их БИН берём
  // с бэкенда, а не хардкодим — те же данные, что и в приходном ордере.
  useEffect(() => {
    const oid = order?.id || orderId;
    if (!oid) { setReceipt(null); return; }
    api(`/api/v1/orders/${oid}/receipt`).then(setReceipt).catch(() => setReceipt(null));
  }, [order?.id, orderId]);

  async function loadCheck(invId) {
    try { setCheck(await api(`/api/v1/invoices/${invId}/check`)); }
    catch (_) { setCheck(null); }
  }

  // Загрузка файла -> распознавание (vLLM) -> старт приёмки -> проверка.
  // Если заявка не выбрана — идём по пути «скан без заявки»: бэкенд сам создаёт
  // поставщика и заявку из распознанной накладной.
  async function recognize() {
    if (!file) return setErr("Выберите файл накладной (фото или PDF)");
    setErr(""); setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file, file.name);
      let oid = order?.id || orderId;
      let inv;
      if (oid) {
        inv = await api(`/api/v1/orders/${oid}/invoice/upload`, { method: "POST", body: fd });
      } else {
        inv = await api(`/api/v1/invoices/scan`, { method: "POST", body: fd });
        oid = inv.order_id;
        // минимальный объект заявки для дальнейших шагов (акт, подтягивание контрагентов)
        setOrder({ id: oid, status: "receiving", items: inv.items || [], created_at: new Date().toISOString() });
      }
      const acc = await api(`/api/v1/orders/${oid}/acceptance`, { method: "POST" });
      setInvoice(inv);
      setAccId(acc.id);
      await loadCheck(inv.id);
      setStep("review");
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  async function editItem(itemId, patch) {
    try {
      const inv = await api(`/api/v1/invoice-items/${itemId}`, { method: "PATCH", json: patch });
      setInvoice(inv);
      loadCheck(inv.id);
    } catch (e) { setErr(e.message); }
  }

  // invoice.items -> локальные строки приёмки
  function goToCheck() {
    setLines(invoice.items.map((it) => ({
      id: it.id, name: it.name, unit: it.unit, art: it.barcode,
      qtyDoc: Number(it.qty), price: Number(it.price),
      type: "ok", dqty: 0, priceNew: Number(it.price), photo: null,
    })));
    setStep("check");
  }

  function updateLine(id, patch) {
    setLines((arr) => arr.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  }
  function setType(id, type) {
    setLines((arr) => arr.map((x) => {
      if (x.id !== id) return x;
      const next = { ...x, type };
      if (type === "ok") next.dqty = 0;
      else if (!next.dqty || next.dqty <= 0) next.dqty = 1;  // дефолт: 1 ед. расхождения
      if (type === "misgrade") next.priceNew = x.priceNew || x.price;
      return next;
    }));
  }

  const computed = lines.map(computeLine);
  const totals = {
    doc: computed.reduce((a, l) => a + l.docSum, 0),
    pay: computed.reduce((a, l) => a + l.paySum, 0),
  };

  function discrepancyPayload(l) {
    const base = { invoice_item_id: l.id, type: l.type };
    if (l.type === "shortage") base.qty_actual = Math.max(0, l.qtyDoc - l.dqty);
    if (l.type === "surplus") base.qty_actual = l.qtyDoc + l.dqty;
    if (l.type === "misgrade") { base.qty_actual = l.dqty; base.price_new = l.priceNew; }
    if (l.type === "defect") { base.qty_defect = l.dqty; base.photo_url = "photo-attached"; }
    return base;
  }

  // Отправляем расхождения на бэкенд, формируем акт (если они есть)
  async function formAct() {
    const diffs = computed.filter((l) => l.type !== "ok" && l.dqty > 0);
    if (diffs.some((l) => l.type === "defect" && !l.photo)) {
      return setErr("Для позиций с браком приложите фото");
    }
    setErr(""); setBusy(true);
    try {
      for (const l of diffs) {
        await api(`/api/v1/acceptance/${accId}/discrepancies`, { method: "POST", json: discrepancyPayload(l) });
      }
      if (diffs.length) {
        setAct(await api(`/api/v1/acceptance/${accId}/act`, { method: "POST" }));
      }
      setStep("act");
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  async function accept() {
    setBusy(true);
    try {
      await api(`/api/v1/acceptance/${accId}/accept`, { method: "POST" });
      alert("Приёмка подтверждена — товары добавлены в сток.");
      onDone();
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  async function downloadPdf() {
    if (!actRef.current) return;
    setExporting(true);
    try {
      const r = await exportNodeToPdf(actRef.current, `Акт_приёмки_${actMeta.actNumber}.pdf`);
      if (r?.fallback) alert("Библиотека PDF не загрузилась — открыт диалог печати (сохраните как PDF).");
    } catch (e) { alert("Не удалось сформировать PDF: " + e.message); }
    finally { setExporting(false); }
  }

  function printAct() {
    if (!actRef.current) return;
    printNode(actRef.current, `Акт о приёмке запасов ${actMeta.actNumber}`);
  }

  const now = new Date();
  const actMeta = {
    supplierName: invoice?.supplier_name || "—",
    invoiceNumber: invoice?.invoice_number || "—",
    invoiceDate: invoice?.invoice_date || "",
    docNumber: act?.number || invoice?.invoice_number || "—",
    actNumber: act?.number || (order ? order.id.slice(0, 8).toUpperCase() : "—"),
    day: String(now.getDate()).padStart(2, "0"),
    monthNum: String(now.getMonth() + 1).padStart(2, "0"),
    monthName: MONTHS[now.getMonth()],
    year: now.getFullYear(),
    place: "г. Алматы",
    sender: receipt?.supplier?.name
      || ((invoice?.supplier_name && invoice.supplier_name !== "null") ? invoice.supplier_name : "—"),
    senderBin: receipt?.supplier?.bin || "—",
    receiver: receipt?.receiver?.name || "—",
    receiverBin: receipt?.receiver?.bin || "—",
    places: computed.length,
  };
  const actTotals = act
    ? { doc: Number(act.original_sum), pay: Number(act.corrected_sum) }
    : totals;

  const stepNo = { select: 1, upload: 2, review: 3, check: 4, act: 5 }[step];
  const STEPS = ["Заявка", "Накладная", "Проверка OCR", "Приёмка", "Акт"];

  return (
    <div className="scan-wrap">
      <div className="page-hd">
        <h2>Сканирование и приёмка</h2>
        <button className="btn btn-outline btn-sm" onClick={onDone}>← К заявкам</button>
      </div>

      <div className="stepper">
        {STEPS.map((s, i) => (
          <div key={s} className={"stepper-item" + (i + 1 < stepNo ? " done" : i + 1 === stepNo ? " active" : "")}>
            <span className="stepper-dot">{i + 1 < stepNo ? <IconCheck size={13} /> : i + 1}</span>
            <span className="stepper-label">{s}</span>
          </div>
        ))}
      </div>

      {err && <div className="err-msg">{err}</div>}

      {step === "select" && (
        <SelectOrder
          orders={allOrders}
          onPick={(o) => { setOrder(o); setStep("upload"); }}
          onScanNew={() => { setOrder(null); setStep("upload"); }}
        />
      )}

      {step === "upload" && (
        <div className="scan-grid">
          <div className="scan-side">
            <div className="scan-cta">
              <div className="scan-cta-ic"><IconScan size={28} /></div>
              <h3>Распознавание накладной</h3>
              <p className="text-muted text-sm">
                Загрузите фото или PDF накладной — модель Qwen2.5-VL извлечёт позиции, количество и цены.
                {!order && !orderId && " Заявка не выбрана — система создаст её автоматически из накладной."}
              </p>
              <input
                type="file" accept="image/*,application/pdf"
                onChange={(e) => setFile(e.target.files[0])}
                style={{ margin: "12px 0" }}
              />
              <button className="btn btn-primary" style={{ width: "100%" }} disabled={busy || !file} onClick={recognize}>
                <IconSparkles size={16} /> {busy ? "Распознаю…" : "Распознать накладную"}
              </button>
            </div>
          </div>
        </div>
      )}

      {step === "review" && invoice && (
        <ReviewOcr invoice={invoice} check={check} onEdit={editItem} onNext={goToCheck} />
      )}

      {step === "check" && (
        <CheckAcceptance lines={computed} totals={totals} busy={busy} onType={setType} onLine={updateLine} onNext={formAct} />
      )}

      {step === "act" && (
        <div className="act-stage">
          <div className="act-toolbar">
            <div className="act-done"><IconCheck size={16} /> {act ? "Акт расхождений сформирован" : "Расхождений нет"}</div>
            <div className="flex gap-8">
              <button className="btn btn-primary" disabled={exporting} onClick={downloadPdf}>
                <IconFilePdf size={16} /> {exporting ? "Готовлю PDF…" : "Скачать акт (PDF)"}
              </button>
              <button className="btn btn-outline" onClick={printAct}>
                <IconPrint size={16} /> Печать акта
              </button>
              <button className="btn btn-outline" disabled={busy} onClick={accept}>
                <IconCheck size={16} /> Подтвердить приёмку
              </button>
            </div>
          </div>
          <ScaledAct width={1080}>
            <ActDocument ref={actRef} meta={actMeta} lines={computed} totals={actTotals} revealCount={computed.length} />
          </ScaledAct>
        </div>
      )}
    </div>
  );
}

// ── Подкомпоненты ───────────────────────────────────────────────────────────

function SelectOrder({ orders, onPick, onScanNew }) {
  const eligible = orders.filter((o) => ["shipped", "receiving"].includes(o.status));
  const list = eligible.length ? eligible : orders;
  return (
    <div className="table-card" style={{ padding: 18 }}>
      <button className="scan-noorder" onClick={onScanNew}>
        <div className="scan-noorder-ic"><IconScan size={22} /></div>
        <div className="scan-noorder-tx">
          <strong>Сканировать без заявки</strong>
          <span>Сфотографируйте накладную — система сама определит поставщика, номер, дату и позиции и создаст заявку.</span>
        </div>
        <IconArrow size={16} />
      </button>

      <div className="filter-title" style={{ margin: "18px 0 14px" }}>…или выберите существующую заявку</div>
      <div className="order-pick-grid">
        {list.map((o) => (
          <button key={o.id} className="order-pick" onClick={() => onPick(o)}>
            <div className="order-pick-id">#{o.id.slice(0, 8).toUpperCase()}</div>
            <div className="order-pick-meta">{new Date(o.created_at).toLocaleDateString("ru-RU")} · {o.items.length} поз.</div>
            <span className="order-pick-go">Принять <IconArrow size={13} /></span>
          </button>
        ))}
        {list.length === 0 && <div className="text-muted text-sm">Готовых заявок нет — используйте «Сканировать без заявки».</div>}
      </div>
    </div>
  );
}

function ReviewOcr({ invoice, check, onEdit, onNext }) {
  const cmap = {};
  (check?.items || []).forEach((c) => (cmap[c.invoice_item_id] = c));
  return (
    <div className="table-card" style={{ padding: 0 }}>
      <div className="invoice-meta">
        <strong>{invoice.supplier_name || "—"} · № {invoice.invoice_number || "—"} · {invoice.invoice_date || ""}</strong>
        <span className="chip c-green"><IconCheck size={12} /> Распознано</span>
      </div>

      {check && (
        <div style={{ margin: "12px 16px 0", padding: "8px 12px", borderRadius: 8, fontSize: 13,
          background: check.ok ? "#e9f7ef" : "#fdecea", color: check.ok ? "#1e7e34" : "#b3261e" }}>
          {check.ok ? "✓ " : "⚠ "}{check.summary}
        </div>
      )}

      <div style={{ padding: "12px 16px 0" }} className="text-muted text-sm">
        Шаг 3. Проверьте распознанные данные и при необходимости поправьте. Изменения сохраняются на сервере.
      </div>
      <table>
        <thead>
          <tr><th>Наименование</th><th>Ед.</th><th className="num">Кол-во</th><th className="num">Цена, ₸</th><th className="num">Сумма, ₸</th></tr>
        </thead>
        <tbody>
          {invoice.items.map((it) => {
            const c = cmap[it.id];
            const bad = c && !c.ok;
            const lowConf = it.confidence != null && it.confidence < 0.85;
            return (
              <React.Fragment key={it.id}>
                <tr>
                  <td className="td-main">
                    <input className={"cell-input cell-wide" + (bad || lowConf ? " low" : "")} defaultValue={it.name}
                      onBlur={(e) => e.target.value !== it.name && onEdit(it.id, { name: e.target.value })} />
                    {(bad || lowConf) && <span className="conf-warn" title="Проверьте строку"><IconAlert size={13} /></span>}
                  </td>
                  <td>{it.unit}</td>
                  <td className="num"><input className={"cell-input" + (bad ? " low" : "")} defaultValue={it.qty}
                    onBlur={(e) => Number(e.target.value) !== Number(it.qty) && onEdit(it.id, { qty: Number(e.target.value) })} /></td>
                  <td className="num"><input className={"cell-input" + (bad ? " low" : "")} defaultValue={it.price}
                    onBlur={(e) => Number(e.target.value) !== Number(it.price) && onEdit(it.id, { price: Number(e.target.value) })} /></td>
                  <td className="num">{Number(it.line_total).toLocaleString("ru-RU")}</td>
                </tr>
                {bad && (c.message || c.issues.length > 0) && (
                  <tr>
                    <td colSpan={5} style={{ background: "#fff8f6", fontSize: 13 }}>
                      <div style={{ color: "#b3261e", marginBottom: 6 }}>{c.message || c.issues.join("; ")}</div>
                      <div className="flex gap-8">
                        {c.suggestions.map((s, i) => (
                          <button key={i} className="btn btn-outline btn-xs"
                            onClick={() => onEdit(it.id, { [s.field]: Number(s.value) })}>
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      <div className="flex justify-end gap-8" style={{ padding: 16 }}>
        <button className="btn btn-primary" onClick={onNext}>Подтвердить и перейти к приёмке <IconArrow size={14} /></button>
      </div>
    </div>
  );
}

function CheckAcceptance({ lines, totals, busy, onType, onLine, onNext }) {
  const delta = totals.pay - totals.doc;
  function readPhoto(id, file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onLine(id, { photo: reader.result });
    reader.readAsDataURL(file);
  }
  return (
    <>
      <div className="table-card acc-card" style={{ padding: 0, marginBottom: 14 }}>
        <div style={{ padding: "14px 16px" }} className="text-muted text-sm">
          Шаг 4. Отметьте тип расхождения и укажите его количество (недостача / излишек / брак / пересорт).
          Суммы пересчитываются на лету. Для «Брака» приложите фото-подтверждение.
        </div>
        <table>
          <thead>
            <tr>
              <th>Товар</th><th className="num">По док.</th><th className="num">Цена</th>
              <th>Тип</th><th className="num">Кол-во расхожд.</th><th className="num">К оплате</th><th className="num">Δ</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={l.id}>
                <td className="td-main">{l.name}</td>
                <td className="num">{l.qtyDoc} {l.unit}</td>
                <td className="num">
                  {l.type === "misgrade" ? (
                    <input className="cell-input" value={l.priceNew}
                      onChange={(e) => onLine(l.id, { priceNew: Number(e.target.value.replace(/\D/g, "") || 0) })} />
                  ) : l.price.toLocaleString("ru-RU")}
                </td>
                <td>
                  <select className="type-select" value={l.type} onChange={(e) => onType(l.id, e.target.value)}>
                    {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                  </select>
                  {l.type === "defect" && (
                    <div className="brak-photo">
                      <label className="brak-add">
                        {l.photo ? "↻ Заменить фото" : "📷 Фото брака"}
                        <input type="file" accept="image/*" hidden onChange={(e) => readPhoto(l.id, e.target.files[0])} />
                      </label>
                      {l.photo && (
                        <span className="brak-thumb-wrap">
                          <img className="brak-thumb" src={l.photo} alt="брак" />
                          <button className="brak-del" title="Удалить" onClick={() => onLine(l.id, { photo: null })}>×</button>
                        </span>
                      )}
                    </div>
                  )}
                </td>
                <td className="num">
                  {l.type === "ok" ? (
                    <span className="text-muted">—</span>
                  ) : (
                    <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                      <input className="cell-input" autoFocus value={l.dqty}
                        onChange={(e) => onLine(l.id, { dqty: Number(e.target.value.replace(/\D/g, "") || 0) })} />
                      <span className="text-muted" style={{ fontSize: 10 }}>{DQTY_LABEL[l.type]}</span>
                    </span>
                  )}
                </td>
                <td className="num"><strong>{l.paySum.toLocaleString("ru-RU")}</strong></td>
                <td className="num" style={{ color: l.delta < 0 ? "var(--danger)" : l.delta > 0 ? "var(--primary)" : "var(--muted)", fontWeight: 600 }}>
                  {l.delta === 0 ? "—" : (l.delta < 0 ? "−" : "+") + Math.abs(l.delta).toLocaleString("ru-RU")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="totals-bar">
          <div className="totals-item"><div className="lbl">По накладной</div><div className="val">{fmt(totals.doc)}</div></div>
          <div className="totals-item"><div className="lbl">К оплате</div><div className={"val" + (delta !== 0 ? " changed" : "")}>{fmt(totals.pay)}</div></div>
          <div className="totals-item"><div className="lbl">Отклонение</div><div className="val" style={{ color: delta < 0 ? "var(--danger)" : delta > 0 ? "var(--primary)" : "var(--ink)" }}>{delta === 0 ? "0 ₸" : (delta < 0 ? "−" : "+") + fmt(Math.abs(delta))}</div></div>
        </div>
      </div>

      <div className="flex justify-end gap-8">
        <button className="btn btn-primary" disabled={busy} onClick={onNext}>
          <IconSparkles size={16} /> {busy ? "Сохраняю…" : "Сформировать акт"}
        </button>
      </div>
    </>
  );
}

function ScaledAct({ width = 1080, children }) {
  const wrapRef = useRef(null);
  const innerRef = useRef(null);
  const [scale, setScale] = useState(1);
  const [h, setH] = useState(0);

  useEffect(() => {
    const fit = () => {
      const cw = wrapRef.current ? wrapRef.current.clientWidth : width;
      const ns = Math.min(1, cw / width);
      setScale((p) => (Math.abs(p - ns) > 0.002 ? ns : p));
    };
    fit();
    const ro = new ResizeObserver(fit);
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener("resize", fit);
    return () => { ro.disconnect(); window.removeEventListener("resize", fit); };
  }, [width]);

  useEffect(() => {
    const measure = () => { if (innerRef.current) setH(innerRef.current.offsetHeight); };
    measure();
    const ro = new ResizeObserver(measure);
    if (innerRef.current) ro.observe(innerRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={wrapRef} className="act-fit" style={{ height: h ? h * scale : undefined }}>
      <div ref={innerRef} style={{ width, transformOrigin: "top left", transform: `scale(${scale})` }}>
        {children}
      </div>
    </div>
  );
}
