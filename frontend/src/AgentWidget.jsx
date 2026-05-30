import React, { useEffect, useRef, useState } from "react";
import { api, getConv, setConv } from "./api.js";

export default function AgentWidget() {
  const [open,  setOpen]  = useState(false);
  const [input, setInput] = useState("");
  const [busy,  setBusy]  = useState(false);
  const [log,   setLog]   = useState([
    { role: "a", text: "Спросите про остатки, заявки, расхождения — или попросите оформить заявку." },
  ]);
  const loaded = useRef(false);

  // При первом открытии — подтянуть историю текущего разговора (память сессии).
  useEffect(() => {
    if (!open || loaded.current) return;
    loaded.current = true;
    const conv = getConv();
    if (!conv) return;
    api(`/api/v1/agent/messages?conversation_id=${conv}`)
      .then(rows => { if (rows && rows.length) setLog(rows.map(m => ({ role: m.role === "user" ? "u" : "a", text: m.content }))); })
      .catch(() => {});
  }, [open]);

  async function send(message, confirm_draft) {
    setBusy(true);
    try {
      const conv = getConv();
      const r = await api("/api/v1/agent/ask", {
        method: "POST",
        json: {
          message,
          ...(confirm_draft ? { confirm_draft } : {}),
          ...(conv ? { conversation_id: conv } : {}),
        },
      });
      if (r.conversation_id) setConv(r.conversation_id);
      setLog(l => [...l, { role: "a", text: r.answer, draft: r.data && r.data.draft }]);
    } catch (e) {
      setLog(l => [...l, { role: "a", text: "Ошибка: " + e.message }]);
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    setLog(l => [...l, { role: "u", text: q }]);
    await send(q);
  }

  async function confirmDraft(draft) {
    if (busy) return;
    setLog(l => [...l, { role: "u", text: "Создать черновик" }]);
    await send("Подтверждаю создание черновика", draft);
  }

  return (
    <div className="agent-widget">
      {open && (
        <div className="agent-box">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <strong style={{ fontSize: 14 }}>AI-помощник</strong>
            <button
              onClick={() => setOpen(false)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--muted)", fontSize: 18 }}
            >×</button>
          </div>
          <div className="agent-log">
            {log.map((m, i) => (
              <div key={i} className={"agent-msg " + m.role}>
                {m.text}
                {m.draft && m.draft.items && m.draft.items.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
                      {m.draft.items.map((it, j) => (
                        <li key={j}>
                          {it.name} — {Number(it.qty)} шт
                          {!it.product_id && " (нет в каталоге)"}
                        </li>
                      ))}
                    </ul>
                    <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => confirmDraft(m.draft)}>
                      Создать черновик
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input"
              value={input}
              placeholder="закажи молоко и кефир как обычно"
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && ask()}
            />
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={ask}>→</button>
          </div>
        </div>
      )}
      <button className="agent-fab" onClick={() => setOpen(o => !o)}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </button>
    </div>
  );
}
