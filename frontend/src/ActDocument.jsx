import React, { forwardRef } from "react";

// Бланк «АКТ О ПРИЕМКЕ ЗАПАСОВ» — точная структура из накладная.xlsx
// (приказ Министра финансов РК № 562 от 20.12.2012).
function breakdown(l) {
  const doc = Number(l.qtyDoc) || 0;
  const fact = Number(l.qtyFact) || 0;
  return {
    doc,
    fact,
    surplus:  l.type === "surplus"  ? Math.max(0, fact - doc) : 0,
    shortage: l.type === "shortage" ? Math.max(0, doc - fact) : 0,
    defect:   l.type === "defect"   ? Math.max(0, doc - fact) : 0,
    regrade:  l.type === "misgrade" ? fact : 0,
  };
}
const z = (n) => (n ? n.toLocaleString("ru-RU") : "—");

const ActDocument = forwardRef(function ActDocument(
  { meta, lines, totals, revealCount = lines.length },
  ref
) {
  const rows = lines.map(breakdown);
  const sum = (k) => rows.reduce((a, r) => a + r[k], 0);
  const photos = lines.filter((l) => l.type === "defect" && l.photo);
  const hasDiff = rows.some((r) => r.surplus || r.shortage || r.defect || r.regrade);

  return (
    <div className="akt-page" ref={ref}>
      <div className="akt-formhint">
        Приложение 25 к приказу Министра<br />финансов РК от 20.12.2012 № 562
      </div>

      <table className="akt-docnum">
        <tbody>
          <tr><td>Номер документа</td><td>Дата составления</td></tr>
          <tr><td>{meta.docNumber}</td><td>{meta.day}.{meta.monthNum}.{meta.year}</td></tr>
        </tbody>
      </table>

      <h3 className="akt-title">АКТ О ПРИЕМКЕ ЗАПАСОВ</h3>

      <table className="akt-fields">
        <tbody>
          <tr><td>Место составления акта:</td><td>{meta.place}</td></tr>
          <tr><td>Принят и осмотрен груз от:</td><td>«{meta.day}» {meta.monthName} {meta.year} г.</td></tr>
          <tr><td>Отправитель:</td><td>{meta.sender}</td></tr>
          <tr><td>Получатель:</td><td>{meta.receiver}</td></tr>
          <tr><td>Условия хранения продукции на складе получателя:</td><td>соответствуют нормам</td></tr>
          <tr><td>Состояние тары и упаковки в момент осмотра, количество мест:</td><td>{meta.places} мест — без повреждений</td></tr>
        </tbody>
      </table>

      <table className="akt-table">
        <colgroup>
          <col style={{ width: "4%" }} />
          <col style={{ width: "11%" }} />
          <col style={{ width: "26%" }} />
          <col style={{ width: "13%" }} />
          <col style={{ width: "9%" }} />
          <col style={{ width: "9%" }} />
          <col style={{ width: "10%" }} />
          <col style={{ width: "8%" }} />
          <col style={{ width: "10%" }} />
        </colgroup>
        <thead>
          <tr>
            <th rowSpan={3}>№ п/п</th>
            <th rowSpan={3}>Штрихкод</th>
            <th rowSpan={3}>Наименование запасов</th>
            <th rowSpan={2}>По сопроводительным документам значилось</th>
            <th colSpan={5}>Фактически оказалось</th>
          </tr>
          <tr>
            <th>Фактическое</th>
            <th>Излишки</th>
            <th>Недостача</th>
            <th>Брак</th>
            <th>Пересчёт</th>
          </tr>
          <tr>
            <th>Кол-во по документам</th>
            <th>Кол-во</th>
            <th>Кол-во</th>
            <th>Кол-во</th>
            <th>Кол-во</th>
            <th>Кол-во</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => {
            const r = rows[i];
            const shown = i < revealCount;
            return (
              <tr key={l.id} className={"akt-row" + (shown ? " is-in" : "")}>
                <td className="c">{i + 1}</td>
                <td className="c">{l.art || "—"}</td>
                <td>{l.name}</td>
                <td className="c">{r.doc}</td>
                <td className="c">{shown ? r.fact : ""}</td>
                <td className={"c " + (r.surplus ? "akt-plus" : "")}>{shown ? z(r.surplus) : ""}</td>
                <td className={"c " + (r.shortage ? "akt-minus" : "")}>{shown ? z(r.shortage) : ""}</td>
                <td className={"c " + (r.defect ? "akt-minus" : "")}>{shown ? z(r.defect) : ""}</td>
                <td className="c">{shown ? z(r.regrade) : ""}</td>
              </tr>
            );
          })}
          <tr className="akt-total">
            <td colSpan={3} className="r">ИТОГО:</td>
            <td className="c">{sum("doc")}</td>
            <td className="c">{sum("fact")}</td>
            <td className="c">{z(sum("surplus"))}</td>
            <td className="c">{z(sum("shortage"))}</td>
            <td className="c">{z(sum("defect"))}</td>
            <td className="c">{z(sum("regrade"))}</td>
          </tr>
        </tbody>
      </table>

      <div className="akt-zakl">
        <strong>Заключение:</strong>{" "}
        {hasDiff
          ? "при приёмке выявлены расхождения, перечисленные в таблице (недостача / излишки / брак / пересчёт)."
          : "запасы приняты полностью, расхождений не выявлено."}
      </div>

      {totals && (() => {
        const d = (totals.pay || 0) - (totals.doc || 0);
        const ten = (n) => Math.round(n).toLocaleString("ru-RU") + " ₸";
        return (
          <div className="akt-money">
            <span>Сумма по документам: <b>{ten(totals.doc || 0)}</b></span>
            <span>Сумма к оплате (с учётом расхождений): <b>{ten(totals.pay || 0)}</b></span>
            <span>Отклонение: <b className={d === 0 ? "" : d < 0 ? "m-minus" : "m-plus"}>
              {d === 0 ? "0 ₸" : (d < 0 ? "−" : "+") + ten(Math.abs(d))}
            </b></span>
          </div>
        );
      })()}

      {photos.length > 0 && (
        <div className="akt-photos">
          <div className="akt-photos-h">Фотофиксация брака:</div>
          <div className="akt-photos-row">
            {photos.map((l) => (
              <figure key={l.id} className="akt-photo">
                <img src={l.photo} alt="брак" />
                <figcaption>{l.name}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      <p className="akt-warn">
        С правилами приёмки запасов по количеству, качеству и комплектности все члены комиссии ознакомлены
        и предупреждены об ответственности за подписание акта, содержащего данные, не соответствующие действительности.
      </p>

      <table className="akt-sign2">
        <tbody>
          <tr>
            <td>Сдал:</td>
            <td className="akt-sl" /><td className="akt-cap">ФИО / подпись / расшифровка</td>
            <td className="akt-mp">М.П.</td>
          </tr>
          <tr>
            <td>Принял:</td>
            <td className="akt-sl" /><td className="akt-cap">ФИО / подпись / расшифровка</td>
            <td className="akt-mp">М.П.</td>
          </tr>
        </tbody>
      </table>

      <div className="akt-oprih">
        Запасы приняты и оприходованы «{meta.day}» {meta.monthName} {meta.year} года.
      </div>
    </div>
  );
});

export default ActDocument;
