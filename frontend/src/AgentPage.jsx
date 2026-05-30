import React, { useEffect, useRef, useState } from "react";
import { api, getConv, setConv } from "./api.js";
import { IconSparkles } from "./icons.jsx";

const SUGGESTIONS = [
  "сколько молока на складе?",
  "что на исходе?",
  "покажи расхождения",
  "у кого больше всего брака?",
  "закажи молоко и кефир как обычно",
];

export default function AgentPage() {
  const GREETING = { role: "a", text: "Я AI-помощник склада. Спросите про остатки, заявки, расхождения, траты — или попросите оформить заявку." };
  const [input, setInput] = useState("");
  const [busy, setBusy]   = useState(false);
  const [log, setLog]     = useState([GREETING]);
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [log]);

  // Восстанавливаем переписку текущей сессии (память диалога).
  useEffect(() => {
    const conv = getConv();
    if (!conv) return;
    api(`/api/v1/agent/messages?conversation_id=${conv}`)
      .then(rows => {
        if (rows && rows.length) {
          setLog(rows.map(m => ({ role: m.role === "user" ? "u" : "a", text: m.content })));
        }
      })
      .catch(() => {});
  }, []);

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
    } finally { setBusy(false); }
  }

  async function ask(q) {
    const t = (q ?? input).trim();
    if (!t || busy) return;
    setInput("");
    setLog(l => [...l, { role: "u", text: t }]);
    await send(t);
  }

  async function confirmDraft(d) {
    if (busy) return;
    setLog(l => [...l, { role: "u", text: "Создать черновик" }]);
    await send("Подтверждаю создание черновика", d);
  }

  return (
    <>
      <div className="page-hd"><h2>AI-помощник</h2></div>
      <div className="table-card" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 210px)", minHeight: 420, padding: 0 }}>
        <div className="agent-log" style={{ flex: 1, maxHeight: "none", padding: 16 }}>
          {log.map((m, i) => (
            <div key={i} className={"agent-msg " + m.role}>
              {m.text}
              {m.draft && m.draft.items && m.draft.items.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
                    {m.draft.items.map((it, j) => (
                      <li key={j}>{it.name} — {Number(it.qty)} шт{!it.product_id && " (нет в каталоге)"}</li>
                    ))}
                  </ul>
                  <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => confirmDraft(m.draft)}>
                    Создать черновик
                  </button>
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
        <div style={{ padding: 12, borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            {SUGGESTIONS.map(s => (
              <button key={s} className="btn btn-outline btn-xs" disabled={busy} onClick={() => ask(s)}>{s}</button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input className="input" style={{ flex: 1 }} value={input} placeholder="Введите запрос…"
              onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && ask()} />
            <button className="btn btn-primary" disabled={busy} onClick={() => ask()}>
              <IconSparkles size={15} /> {busy ? "…" : "Спросить"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
