import React, { useEffect, useState } from "react";
import { api, setToken, getToken, setConv } from "./api.js";
import { IconHome, IconList, IconDoc, IconLogout, IconScan, IconPackage, IconClipboard, IconSparkles } from "./icons.jsx";
import Login from "./Login.jsx";
import Dashboard from "./Dashboard.jsx";
import Orders from "./Orders.jsx";
import Scan from "./Scan.jsx";
import Supplier from "./Supplier.jsx";
import Shipments from "./Shipments.jsx";
import Products from "./Products.jsx";
import ProductPhotos from "./ProductPhotos.jsx";
import Stock from "./Stock.jsx";
import AgentPage from "./AgentPage.jsx";
import AgentWidget from "./AgentWidget.jsx";

const NAV_STORE = [
  { id: "dashboard", label: "Главная",      Icon: IconHome },
  { id: "orders",    label: "Заявки",       Icon: IconList },
  { id: "scan",      label: "Сканировать",  Icon: IconScan },
  { id: "products",  label: "Товары",       Icon: IconPackage },
  { id: "stock",     label: "Остатки",      Icon: IconClipboard },
  { id: "agent",     label: "AI-помощник",  Icon: IconSparkles },
];
const NAV_DIST = [
  { id: "dashboard", label: "Главная",          Icon: IconHome },
  { id: "shipments", label: "Отгрузка",         Icon: IconList },
  { id: "supplier",  label: "Акты расхождений", Icon: IconDoc },
  { id: "products",  label: "Товары",           Icon: IconPackage },
  { id: "agent",     label: "AI-помощник",      Icon: IconSparkles },
];

const TITLES = {
  dashboard:  "Главная",
  orders:     "Заявки",
  scan:       "Сканирование и приёмка",
  supplier:   "Акты расхождений",
  shipments:  "Отгрузка",
  products:   "Товары",
  stock:      "Остатки",
  agent:      "AI-помощник",
};

const readJSON = (key, fallback) => {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; }
  catch (_) { return fallback; }
};

export default function App() {
  // Восстанавливаем сессию и активную страницу из localStorage (переживает F5).
  const [me,   setMe]   = useState(() => readJSON("dara_me", null));
  const [view, setView] = useState(() => readJSON("dara_view", { name: "dashboard" }));

  // Сохраняем выбранную страницу
  useEffect(() => {
    try { localStorage.setItem("dara_view", JSON.stringify(view)); } catch (_) {}
  }, [view]);

  // На старте проверяем токен: если протух/отозван — разлогиниваем.
  useEffect(() => {
    if (me && getToken()) {
      api("/api/v1/auth/me")
        .then((fresh) => { setMe(fresh); try { localStorage.setItem("dara_me", JSON.stringify(fresh)); } catch (_) {} })
        .catch(() => logout());
    } else if (me && !getToken()) {
      logout();
    }
  }, []); // eslint-disable-line

  function logout() {
    setToken(null);
    setConv(null);  // новая сессия -> новый разговор с агентом
    try { localStorage.removeItem("dara_me"); } catch (_) {}
    setMe(null);
    setView({ name: "dashboard" });
  }
  function onLogin(user) {
    setMe(user);
    try { localStorage.setItem("dara_me", JSON.stringify(user)); } catch (_) {}
    setView({ name: "dashboard" });
  }

  if (!me) return <Login onLogin={onLogin} />;

  const nav = me.role === "store" ? NAV_STORE : NAV_DIST;
  const initials = (me.full_name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <img className="brand-logo" src="/logo.svg" alt="DaraQyzmet" />
          <div className="brand-text">Dara<span>Qyzmet</span></div>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-label">Меню</div>
          {nav.map(({ id, label, Icon }) => (
            <button
              key={id}
              className={"nav-link" + (view.name === id ? " active" : "")}
              onClick={() => setView({ name: id })}
            >
              <span className="nav-icon"><Icon /></span>
              {label}
            </button>
          ))}
        </div>

        <div className="sidebar-spacer" />

        <div className="sidebar-user">
          <div className="user-avatar">{initials}</div>
          <div className="user-meta">
            <div className="user-name">{me.full_name}</div>
            <div className="user-role">{me.role === "store" ? "Магазин" : "Поставщик"}</div>
          </div>
          <button className="btn-logout" onClick={logout} title="Выйти">
            <IconLogout />
          </button>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <span className="page-title">{TITLES[view.name] || ""}</span>
          <div className="topbar-right">
            <span className="halyk-badge">Halyk Ecosystem</span>
          </div>
        </header>

        <main className="page-body">
          {view.name === "dashboard" && (
            <Dashboard role={me.role} onNavigate={name => setView({ name })} />
          )}
          {view.name === "products" && (
            <Products role={me.role} onOpenPhotos={prod => setView({ name: "product-photos", product: prod })} />
          )}
          {view.name === "product-photos" && (
            <ProductPhotos product={view.product} onBack={() => setView({ name: "products" })} />
          )}
          {view.name === "stock"    && <Stock />}
          {view.name === "agent"    && <AgentPage />}
          {me.role === "store" && view.name === "orders" && (
            <Orders onAccept={id => setView({ name: "scan", orderId: id })} />
          )}
          {me.role === "store" && view.name === "scan" && (
            <Scan orderId={view.orderId || null} onDone={() => setView({ name: "orders" })} />
          )}
          {me.role === "distributor" && view.name === "supplier" && <Supplier />}
          {me.role === "distributor" && view.name === "shipments" && <Shipments />}
        </main>
      </div>

      <AgentWidget />
    </div>
  );
}
