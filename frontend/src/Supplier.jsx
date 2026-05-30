import React, { useEffect, useState } from "react";
import { api, fmt } from "./api.js";

export default function Supplier() {
  const [acts, setActs] = useState([]);
  const [err, setErr] = useState("");

  function load() {
    api("/api/v1/supplier/acts").then(setActs).catch((e) => setErr(e.message));
  }
  useEffect(load, []);

  async function correct(id) {
    try {
      await api(`/api/v1/acts/${id}/correct-invoice`, { method: "POST" });
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <>
      <h2>Акты расхождений</h2>
      {err && <div className="err">{err}</div>}
      <div className="card" style={{ padding: 6 }}>
        <table>
          <thead>
            <tr>
              <th>Акт</th>
              <th className="num">Было</th>
              <th className="num">Стало</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {acts.map((a) => (
              <tr key={a.id}>
                <td>
                  <b>{a.number}</b>
                </td>
                <td className="num">{fmt(a.original_sum)}</td>
                <td className="num">
                  <b>{fmt(a.corrected_sum)}</b>
                </td>
                <td>
                  <span className={"chip " + (a.status === "corrected" ? "c-green" : "c-amber")}>
                    {a.status === "corrected" ? "счёт скорректирован" : "создан"}
                  </span>
                </td>
                <td className="num">
                  {a.status !== "corrected" && (
                    <button className="btn btn-green btn-sm" onClick={() => correct(a.id)}>
                      Скорректировать счёт
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {acts.length === 0 && (
              <tr>
                <td className="muted">Актов пока нет</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
