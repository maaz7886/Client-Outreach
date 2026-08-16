"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type SenderProfileRow = {
  id: number;
  name: string;
  display_name: string;
  email_address: string;
  enabled: boolean;
};

type DefaultSender = {
  display_name: string;
  email_address: string;
  configured: boolean;
  label: string;
};

function Modal({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 16, padding: 28, width: 460, maxWidth: "95vw",
          boxShadow: "0 8px 40px rgba(0,0,0,0.18)", border: "1px solid #dceae2",
        }}
      >
        {children}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
  fontSize: 13, color: "#0f1a14", background: "#f8faf9", outline: "none", width: "100%",
  boxSizing: "border-box",
};

function ProfileFormModal({
  title,
  initial,
  onClose,
  onSave,
}: {
  title: string;
  initial: { name: string; display_name: string; email_address: string; enabled: boolean };
  onClose: () => void;
  onSave: (data: typeof initial) => Promise<void>;
}) {
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!form.name.trim() || !form.display_name.trim() || !form.email_address.trim()) {
      setErr("Name, display name, and email are required.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSave({
        name: form.name.trim(),
        display_name: form.display_name.trim(),
        email_address: form.email_address.trim(),
        enabled: form.enabled,
      });
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>{title}</h2>
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Profile name</label>
        <input style={inputStyle} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Maaz — Outreach" />
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Display name (From)</label>
        <input style={inputStyle} value={form.display_name} onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))} placeholder="Maaz Patel" />
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Email address (From)</label>
        <input style={inputStyle} type="email" value={form.email_address} onChange={(e) => setForm((f) => ({ ...f, email_address: e.target.value }))} placeholder="maaz@company.com" />
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#4a7a5c" }}>
          <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))} />
          Enabled
        </label>
        {err && <p style={{ color: "#dc2626", fontSize: 12, margin: 0 }}>⚠ {err}</p>}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, cursor: "pointer" }}>Cancel</button>
          <button onClick={save} disabled={busy} style={{ background: busy ? "#6b9e7e" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: busy ? "not-allowed" : "pointer" }}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default function SendersPage() {
  const [rows, setRows] = useState<SenderProfileRow[]>([]);
  const [defaultSender, setDefaultSender] = useState<DefaultSender | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<SenderProfileRow | null>(null);

  const load = useCallback(() => {
    api<{ default: DefaultSender; items: SenderProfileRow[] }>("/api/sender-profiles")
      .then((d) => { setRows(d.items); setDefaultSender(d.default); setError(null); })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(load, [load]);

  if (error) {
    return (
      <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 12, padding: 20, color: "#dc2626" }}>
        ⚠ {error}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {creating && (
        <ProfileFormModal
          title="Create Sender Profile"
          initial={{ name: "", display_name: "", email_address: "", enabled: true }}
          onClose={() => setCreating(false)}
          onSave={async (data) => {
            await api("/api/sender-profiles", { method: "POST", body: JSON.stringify(data) });
            load();
          }}
        />
      )}
      {editing && (
        <ProfileFormModal
          title="Edit Sender Profile"
          initial={{
            name: editing.name,
            display_name: editing.display_name,
            email_address: editing.email_address,
            enabled: editing.enabled,
          }}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            await api(`/api/sender-profiles/${editing.id}`, { method: "PATCH", body: JSON.stringify(data) });
            load();
          }}
        />
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>Sender Profiles</h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>
            Override From Name and From Email at send time — SMTP credentials stay in .env
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          style={{
            background: "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none",
            borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}
        >
          + New Profile
        </button>
      </div>

      {defaultSender && (
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 12, padding: "14px 18px" }}>
          <p style={{ margin: 0, fontSize: 13, color: "#15803d", fontWeight: 700 }}>Default sender (.env)</p>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#166534" }}>
            {defaultSender.display_name} &lt;{defaultSender.email_address || "not configured"}&gt;
            {!defaultSender.configured && (
              <span style={{ color: "#92400e" }}> — set SENDER_NAME and SENDER_EMAIL in .env</span>
            )}
          </p>
        </div>
      )}

      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "Display Name", "Email", "Status", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.id} style={{ borderTop: "1px solid #f0f7f3", background: i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                <td style={{ padding: "10px 14px", fontWeight: 600, color: "#0f3622" }}>{p.name}</td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c" }}>{p.display_name}</td>
                <td style={{ padding: "10px 14px", fontFamily: "monospace", fontSize: 12, color: "#4a7a5c" }}>{p.email_address}</td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{
                    background: p.enabled ? "#d1fae5" : "#f3f4f6",
                    color: p.enabled ? "#065f46" : "#6b7280",
                    borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600,
                  }}>
                    {p.enabled ? "Enabled" : "Disabled"}
                  </span>
                </td>
                <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                  <button onClick={() => setEditing(p)} style={{ background: "#e8f5ee", color: "#1a5c38", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6 }}>✏ Edit</button>
                  <button
                    onClick={async () => {
                      if (!confirm(`Delete sender profile "${p.name}"?`)) return;
                      await api(`/api/sender-profiles/${p.id}`, { method: "DELETE" });
                      load();
                    }}
                    style={{ background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    🗑 Delete
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: "32px 16px", textAlign: "center", color: "#94b5a0" }}>
                  No custom profiles — the default .env sender is used unless you add one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
