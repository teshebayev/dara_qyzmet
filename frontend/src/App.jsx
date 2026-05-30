import React, { useState } from "react";
import { setToken } from "./api.js";
import Login from "./Login.jsx";
import Orders from "./Orders.jsx";
import Acceptance from "./Acceptance.jsx";
import Supplier from "./Supplier.jsx";
import AgentWidget from "./AgentWidget.jsx";

export default function App() {
  const [me, setMe] = useState(null);
  const [view, setView] = useState({ name: "orders" }); // orders | acceptance

  function logout() {
    setToken(null);
    setMe(null);
    setView({ name: "orders" });
  }

  function onLogin(user) {
    setMe(user);
    setView({ name: user.role === "store" ? "orders" : "supplier" });
  }

  return (
    <>
      <header>
        <div className="wrap nav">
          <div className="logo">
            <span className="m">D</span>Dara <b>Kyzmet</b>
          </div>
          {me && (
            <>
              <span className="who">
                {me.full_name} · {me.role === "store" ? "магазин" : "поставщик"}
              </span>
              <button className="btn btn-white btn-sm" onClick={logout}>
                Выйти
              </button>
            </>
          )}
        </div>
      </header>

      <main className="wrap">
        {!me && <Login onLogin={onLogin} />}

        {me && me.role === "store" && view.name === "orders" && (
          <Orders onAccept={(id) => setView({ name: "acceptance", orderId: id })} />
        )}
        {me && me.role === "store" && view.name === "acceptance" && (
          <Acceptance orderId={view.orderId} onDone={() => setView({ name: "orders" })} />
        )}
        {me && me.role === "distributor" && <Supplier />}
      </main>

      <footer>Dara Kyzmet · приёмка накладных · стиль Halyk</footer>

      {me && <AgentWidget />}
    </>
  );
}
