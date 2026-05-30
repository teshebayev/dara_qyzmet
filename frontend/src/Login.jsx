import React, { useState } from "react";
import { api, setToken } from "./api.js";

// Реальный вход: POST /auth/login -> токен, затем GET /auth/me -> профиль/роль.
export default function Login({ onLogin }) {
  const [email,    setEmail]    = useState("store@dara.kz");
  const [password, setPassword] = useState("demo12345");
  const [err,      setErr]      = useState("");
  const [busy,     setBusy]     = useState(false);

  async function submit(creds) {
    const e = (creds?.email ?? email).toLowerCase().trim();
    const pw = creds?.password ?? password;
    if (!e || !pw) { setErr("Введите email и пароль"); return; }
    setErr(""); setBusy(true);
    try {
      const { access_token } = await api("/api/v1/auth/login", {
        method: "POST",
        json: { email: e, password: pw },
      });
      setToken(access_token);
      const me = await api("/api/v1/auth/me");
      onLogin(me);
    } catch (e2) {
      setToken(null);
      setErr(e2.message || "Не удалось войти");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-icon">D</div>
          <h1>Dara Qyzmet</h1>
          <p>Цифровая приёмка накладных</p>
        </div>

        <div className="form-field">
          <label className="form-label">Email</label>
          <input
            className="form-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@company.kz"
          />
        </div>
        <div className="form-field">
          <label className="form-label">Пароль</label>
          <input
            className="form-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
        </div>

        {err && <div className="err-msg">{err}</div>}

        <div className="login-actions">
          <button className="btn btn-primary" style={{ width: "100%" }} disabled={busy} onClick={() => submit()}>
            {busy ? "Входим…" : "Войти"}
          </button>
          <div className="login-divider">или</div>
          <button
            className="btn btn-outline" style={{ width: "100%" }} disabled={busy}
            onClick={() => { setEmail("dist@dara.kz"); submit({ email: "dist@dara.kz", password: "demo12345" }); }}
          >
            Войти как поставщик
          </button>
        </div>

        <div className="login-demo">
          Демо магазин: <code>store@dara.kz</code><br />
          Демо поставщик: <code>dist@dara.kz</code><br />
          Пароль: <code>demo12345</code>
        </div>
      </div>
    </div>
  );
}
