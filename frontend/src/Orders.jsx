import React, { useEffect, useState } from "react";
import { api, STATUS } from "./api.js";

export default function Orders({ onAccept }) {
  const [orders, setOrders] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    api("/api/v1/orders")
      .then(setOrders)
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <>
      <div className="hero">
        <h1>Приёмка товара без бумаги и ошибок</h1>
        <p>Сфотографируйте накладную — AI распознает позиции, вы проверите и подтвердите</p>
      </div>
      <h2>Заявки</h2>
      {err && <div className="err">{err}</div>}
      <div className="card" style={{ padding: 6 }}>
        <table>
          <thead>
            <tr>
              <th>Заявка</th>
              <th>Позиций</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => {
              const [label, cls] = STATUS[o.status] || [o.status, "c-gray"];
              const canAccept = o.status === "shipped" || o.status === "receiving";
              return (
                <tr key={o.id}>
                  <td>
                    <b>{o.id.slice(0, 8)}</b>
                  </td>
                  <td>{o.items.length}</td>
                  <td>
                    <span className={"chip " + cls}>{label}</span>
                  </td>
                  <td className="num">
                    {canAccept && (
                      <button className="btn btn-green btn-sm" onClick={() => onAccept(o.id)}>
                        Принять
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {orders.length === 0 && (
              <tr>
                <td className="muted">Заявок пока нет</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
