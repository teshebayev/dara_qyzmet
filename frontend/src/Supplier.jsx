import React, { useEffect, useState } from "react";
import { api, fmt } from "./api.js";
import { IconRefresh, IconDownload } from "./icons.jsx";
import { Spinner, ErrBanner, EmptyState } from "./ui.jsx";

export default function Supplier() {
  const [acts,    setActs]    = useState([]);
  const [err,     setErr]     = useState("");
  const [loading, setLoading] = useState(true);
  const [fStatus, setFStatus] = useState("");
  const [fDate,   setFDate]   = useState("");

  function load() {
    setLoading(true); setErr("");
    api("/api/v1/supplier/acts")
      .then(setActs)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function correct(id) {
    try { await api(`/api/v1/acts/${id}/correct-invoice`, { method: "POST" }); load(); }
    catch (e) { setErr(e.message); }
  }

  const shown = acts.filter(a => {
    if (fStatus && a.status !== fStatus) return false;
    if (fDate && (a.created_at || "").slice(0, 10) !== fDate) return false;
    return true;
  });

  return (
    <>
      <div className="page-hd"><h2>Акты расхождений</h2></div>

      <div className="filter-card">
        <div className="filter-title">Фильтр</div>
        <div className="filter-grid filter-grid-2">
          <div>
            <div className="form-label">Статус</div>
            <select className="input" value={fStatus} onChange={e => setFStatus(e.target.value)}>
              <option value="">Все</option>
              <option value="created">Создан</option>
              <option value="corrected">Скорректирован</option>
            </select>
          </div>
          <div>
            <div className="form-label">Дата</div>
            <input className="input" type="date" value={fDate} onChange={e => setFDate(e.target.value)} />
          </div>
        </div>
        <div className="filter-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => { setFStatus(""); setFDate(""); }}>Сбросить</button>
        </div>
      </div>

      <ErrBanner message={err} onRetry={load} />

      <div className="table-card">
        <div className="table-toolbar">
          <button className="btn btn-ghost btn-sm" onClick={load}><IconRefresh /> Обновить</button>
          <button className="btn btn-outline btn-sm"><IconDownload /> Выгрузить в Excel</button>
        </div>
        {loading ? <Spinner /> : (
          <table>
            <thead>
              <tr>
                <th>Акт</th>
                <th className="num">По накладной</th>
                <th className="num">К оплате</th>
                <th className="num">Разница</th>
                <th>Статус</th>
                <th style={{ textAlign: "right" }}>Действие</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(a => {
                const delta = Number(a.corrected_sum) - Number(a.original_sum);
                return (
                  <tr key={a.id}>
                    <td className="td-main">{a.number}</td>
                    <td className="num">{fmt(a.original_sum)}</td>
                    <td className="num"><strong>{fmt(a.corrected_sum)}</strong></td>
                    <td className="num" style={{ color: delta < 0 ? "var(--danger)" : "var(--primary)", fontWeight: 600 }}>
                      {delta < 0 ? "−" : "+"}{fmt(Math.abs(delta))}
                    </td>
                    <td>
                      <span className={"chip " + (a.status === "corrected" ? "c-green" : "c-amber")}>
                        {a.status === "corrected" ? "Скорректирован" : "Создан"}
                      </span>
                    </td>
                    <td className="num">
                      {a.status !== "corrected" && (
                        <button className="btn btn-primary btn-xs" onClick={() => correct(a.id)}>
                          Скорректировать счёт
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {shown.length === 0 && !err && (
                <EmptyState
                  title={acts.length ? "Ничего не найдено" : "Актов нет"}
                  desc={acts.length ? "Измените условия фильтра" : "Акты появятся после приёмки с расхождениями"}
                />
              )}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
