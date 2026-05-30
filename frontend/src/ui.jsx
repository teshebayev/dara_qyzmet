import React from "react";

export function Spinner() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
      <div style={{
        width: 32, height: 32,
        border: "3px solid var(--border)",
        borderTopColor: "var(--primary)",
        borderRadius: "50%",
        animation: "spin .7s linear infinite",
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export function ErrBanner({ message, onRetry }) {
  if (!message) return null;
  const isOffline = message.includes("сервер") || message.includes("связи");
  return (
    <div style={{
      background: isOffline ? "#FFF8F0" : "var(--danger-light)",
      border: `1px solid ${isOffline ? "#FEC84B" : "rgba(217,45,32,.15)"}`,
      borderRadius: "var(--r)",
      padding: "12px 16px",
      marginBottom: 16,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 18 }}>{isOffline ? "🔌" : "⚠️"}</span>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, color: isOffline ? "#B54708" : "var(--danger)" }}>
            {isOffline ? "Сервер недоступен" : "Ошибка"}
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{message}</div>
        </div>
      </div>
      {onRetry && (
        <button className="btn btn-outline btn-xs" onClick={onRetry}>Повторить</button>
      )}
    </div>
  );
}

export function EmptyState({ icon, title, desc, action }) {
  return (
    <tr>
      <td colSpan={99}>
        <div style={{ textAlign: "center", padding: "52px 24px" }}>
          <div style={{ fontSize: 36, marginBottom: 12, opacity: .5 }}>{icon || "📭"}</div>
          <div style={{ fontWeight: 600, fontSize: 15, color: "var(--ink-2)" }}>{title}</div>
          {desc && <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 6 }}>{desc}</div>}
          {action && <div style={{ marginTop: 16 }}>{action}</div>}
        </div>
      </td>
    </tr>
  );
}

export function StatCard({ label, value, sub, color }) {
  return (
    <div style={{
      background: "#fff",
      border: "1px solid var(--border)",
      borderRadius: "var(--r-lg)",
      padding: "12px 16px",
      borderLeft: `3px solid ${color || "var(--primary)"}`,
      display: "flex",
      alignItems: "center",
      gap: 14,
    }}>
      <div>
        <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".4px" }}>{label}</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: "var(--ink)", lineHeight: 1.2, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}
