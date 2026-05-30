import React, { forwardRef, useEffect, useState } from "react";

// Штрихкод номера заявки. Рендерим в off-screen canvas через JsBarcode и
// показываем как <img> (dataURL) — так он корректно попадает в PDF (html2canvas
// клонирует узел, а клон <canvas> теряет картинку, <img> — нет).
function Barcode({ value }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    if (!value || !window.JsBarcode) return;
    try {
      const c = document.createElement("canvas");
      window.JsBarcode(c, value, { format: "CODE128", height: 46, width: 2, fontSize: 14, margin: 0, displayValue: true });
      setSrc(c.toDataURL("image/png"));
    } catch (_) {}
  }, [value]);
  return src
    ? <img className="po-barcode" src={src} alt={value} />
    : <div className="po-barcode-fallback">{value}</div>;
}

const z = (n) => Number(n || 0).toLocaleString("ru-RU");

// Приходный ордер запасов — Приложение 25 к приказу Минфина РК № 562 от 20.12.2012.
const ReceiptDocument = forwardRef(function ReceiptDocument({ data }, ref) {
  const items = data.items || [];
  const totalQty = items.reduce((a, i) => a + Number(i.qty), 0);
  const totalSum = items.reduce((a, i) => a + Number(i.total), 0);
  const barcodeValue = (data.number || "").replace("#", "");
  const dateStr = data.date ? new Date(data.date).toLocaleDateString("ru-RU") : "";

  return (
    <div className="po-page" ref={ref}>
      <div className="po-top">
        <Barcode value={barcodeValue} />
        <div className="po-appendix">
          Приложение 25<br />к приказу Министра финансов<br />
          Республики Казахстан<br />от 20 декабря 2012 года № 562
        </div>
      </div>

      <div className="po-org">
        <span className="po-org-cap">Организация (индивидуальный предприниматель)</span>
        <span className="po-org-name">{data.receiver?.name || "—"}</span>
        <span className="po-bin">ИИН/БИН <b>{data.receiver?.bin || "—"}</b></span>
      </div>

      <h3 className="po-title">
        ПРИХОДНЫЙ ОРДЕР ЗАПАСОВ {data.number}{dateStr ? ` от ${dateStr}` : ""}
      </h3>

      <table className="po-table">
        <colgroup>
          <col style={{ width: "4%" }} />
          <col style={{ width: "30%" }} />
          <col style={{ width: "13%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "13%" }} />
          <col style={{ width: "14%" }} />
          <col style={{ width: "16%" }} />
        </colgroup>
        <thead>
          <tr>
            <th rowSpan={2}>№</th>
            <th rowSpan={2}>Наименование, сорт, размер, марка</th>
            <th rowSpan={2}>Штрихкод</th>
            <th rowSpan={2}>Единица измерения</th>
            <th>По документу</th>
            <th rowSpan={2}>Цена за единицу, в тенге</th>
            <th rowSpan={2}>Сумма, в тенге</th>
          </tr>
          <tr><th>количество</th></tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={i}>
              <td className="c">{i + 1}</td>
              <td>{it.name}</td>
              <td className="c">{it.barcode || "—"}</td>
              <td className="c">{it.unit}</td>
              <td className="r">{z(it.qty)}</td>
              <td className="r">{z(it.price)}</td>
              <td className="r">{z(it.total)}</td>
            </tr>
          ))}
          <tr className="po-total">
            <td colSpan={4} className="r">Итого:</td>
            <td className="r">{z(totalQty)}</td>
            <td />
            <td className="r">{z(totalSum)}</td>
          </tr>
        </tbody>
      </table>

      <div className="po-signs">
        <div className="po-sign">
          <span className="po-sign-role">Принял</span>
          <span className="po-sign-line">{data.receiver?.name || ""}</span>
          <span className="po-sign-cap">подпись / расшифровка подписи</span>
        </div>
        <div className="po-sign">
          <span className="po-sign-role">Сдал</span>
          <span className="po-sign-line">{data.supplier?.name || ""}</span>
          <span className="po-sign-cap">подпись / расшифровка подписи</span>
        </div>
      </div>

      <p className="po-foot">
        *Графа «Номер паспорта» заполняется при оформлении операций по запасам,
        содержащим драгоценные металлы и камни.
      </p>
    </div>
  );
});

export default ReceiptDocument;
