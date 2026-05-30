import React, { useState } from "react";
import { api, setToken } from "./api.js";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("store@dara.kz");
  const [password, setPassword] = useState("demo12345");
  const [err, setErr] = useState("");

  async function submit(asEmail) {
    setErr("");
    const e = asEmail || email;
    try {
      const d = await api("/api/v1/auth/login", {
        method: "POST",
        json: { email: e, password },
      });
      setToken(d.access_token);
      const me = await api("/api/v1/auth/me");
      onLogin(me);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div className="login">
      <h2>Вход</h2>
      <div className="card">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="пароль"
        />
        <button className="btn btn-green" style={{ width: "100%" }} onClick={() => submit()}>
          Войти как магазин
        </button>
        <button
          className="btn btn-white"
          style={{ width: "100%" }}
          onClick={() => {
            setEmail("dist@dara.kz");
            submit("dist@dara.kz");
          }}
        >
          Войти как поставщик
        </button>
        {err && <div className="err">{err}</div>}
        <div className="muted" style={{ fontSize: 12 }}>
          демо: store@dara.kz / dist@dara.kz · пароль demo12345
        </div>
      </div>
    </div>
  );
}
