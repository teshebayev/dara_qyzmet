import React, { useState } from "react";
import { api } from "./api.js";

export default function AgentWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [log, setLog] = useState([
    { role: "a", text: "Спросите про остатки, заявки или расхождения." },
  ]);

  async function ask() {
    const q = input.trim();
    if (!q) return;
    setInput("");
    setLog((l) => [...l, { role: "u", text: q }]);
    try {
      const r = await api("/api/v1/agent/ask", { method: "POST", json: { message: q } });
      setLog((l) => [...l, { role: "a", text: r.answer }]);
    } catch (e) {
      setLog((l) => [...l, { role: "a", text: "Ошибка: " + e.message }]);
    }
  }

  return (
    <div className="agent">
      {open && (
        <div className="box">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b>Поддержка</b>
            <span style={{ cursor: "pointer" }} onClick={() => setOpen(false)}>
              ✕
            </span>
          </div>
          <div className="log">
            {log.map((m, i) => (
              <div key={i} className={"msg " + m.role}>
                {m.text}
              </div>
            ))}
          </div>
          <div className="row">
            <input
              style={{ flex: 1 }}
              value={input}
              placeholder="сколько молока на складе?"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
            />
            <button className="btn btn-green btn-sm" onClick={ask}>
              →
            </button>
          </div>
        </div>
      )}
      <button className="fab" onClick={() => setOpen((o) => !o)}>
        🤖
      </button>
    </div>
  );
}
