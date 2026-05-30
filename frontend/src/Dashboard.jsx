import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { StatCard, ErrBanner, Spinner } from "./ui.jsx";

const TILES_STORE = [
  { label: "Создать заявку на приёмку", sub: "Загрузить накладную — AI распознает позиции", action: "scan",    img: "/img/truck.png",   dark: false },
  { label: "Мои заявки",               sub: "Просмотр всех статусов",                     action: "orders",  img: "/img/forklift.png", dark: true  },
  { label: "Сканировать накладную",     sub: "OCR распознавание фото и PDF",               action: "scan",    img: "/img/folders.png",  alt: true   },
  { label: "Последние приёмки",         sub: "История принятых накладных",                 action: "orders",  img: "/img/boxes.png",    alt: true   },
];

const TILES_DIST = [
  { label: "Акты расхождений", sub: "Просмотр актов и корректировка счетов", action: "supplier",  img: "/img/folders.png" },
  { label: "Мои поставки",     sub: "История отгрузок",                      action: "shipments", img: "/img/truck.png",  dark: true },
];

function Tile({ label, sub, action, img, dark, alt, onNavigate }) {
  return (
    <button
      className={"tile" + (dark ? " tile-dark" : alt ? " tile-outline" : "")}
      onClick={() => onNavigate(action)}
    >
      {img && <img className="tile-img" src={img} alt="" />}
      <div className="tile-label">{label}</div>
      <div className="tile-sub">{sub}</div>
    </button>
  );
}

export default function Dashboard({ role, onNavigate }) {
  const [stats,   setStats]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [err,     setErr]     = useState("");

  function load() {
    setLoading(true); setErr("");
    if (role === "store") {
      Promise.all([
        api("/api/v1/orders").catch(() => []),
        api("/api/v1/stock").catch(() => []),
      ]).then(([orders, stock]) => {
        const today = new Date().toDateString();
        setStats({
          ordersTotal:  orders.length,
          ordersToday:  orders.filter(o => new Date(o.created_at).toDateString() === today).length,
          accepted:     orders.filter(o => o.status === "accepted").length,
          stockItems:   stock.length,
        });
      }).catch(e => setErr(e.message)).finally(() => setLoading(false));
    } else {
      Promise.all([
        api("/api/v1/supplier/acts").catch(() => []),
        api("/api/v1/orders").catch(() => []),
      ]).then(([acts, orders]) => {
        setStats({
          actsTotal:     acts.length,
          actsPending:   acts.filter(a => a.status !== "corrected").length,
          ordersShipped: orders.filter(o => o.status === "shipped").length,
        });
      }).catch(e => setErr(e.message)).finally(() => setLoading(false));
    }
  }
  useEffect(load, [role]);

  const tiles = role === "store" ? TILES_STORE : TILES_DIST;

  return (
    <div className="dashboard-fill">
      <ErrBanner message={err} onRetry={load} />

      {loading ? <Spinner /> : stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 20 }}>
          {role === "store" ? <>
            <StatCard label="Всего заявок"    value={stats.ordersTotal}  sub="за всё время"          color="var(--primary)" />
            <StatCard label="Заявок сегодня"  value={stats.ordersToday}  sub="создано сегодня"        color="var(--info)" />
            <StatCard label="Принято"         value={stats.accepted}     sub="успешных приёмок"       color="#027A48" />
            <StatCard label="Товаров в стоке" value={stats.stockItems}   sub="позиций на складе"      color="var(--warning)" />
          </> : <>
            <StatCard label="Актов всего"  value={stats.actsTotal}     sub="за всё время"           color="var(--primary)" />
            <StatCard label="Ожидают"      value={stats.actsPending}   sub="требуют корректировки"  color="var(--danger)" />
            <StatCard label="Отгружено"    value={stats.ordersShipped} sub="ожидают приёмки"        color="var(--info)" />
          </>}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="tiles">
          {tiles.slice(0, 2).map((t, i) => <Tile key={i} {...t} onNavigate={onNavigate} />)}
        </div>
        {tiles.length > 2 && (
          <div className="tiles">
            {tiles.slice(2).map((t, i) => <Tile key={i} {...t} onNavigate={onNavigate} />)}
          </div>
        )}
      </div>
    </div>
  );
}
