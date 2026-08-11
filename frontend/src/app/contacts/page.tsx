"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type ContactRow = {
  id: number; full_name: string; role: string; college: string;
  email: string | null; confidence: number; status: string; notes: string | null;
};

const FILTERS = ["", "VERIFIED", "NEEDS_MANUAL_REVIEW", "CONTACTED",
  "REPLIED_POSITIVE", "MEETING_SCHEDULED", "WON", "LOST"];

const ALL_ROLES = [
  "TPO", "PLACEMENT_DIRECTOR", "TRAINING_OFFICER", "HOD", "DEAN",
  "DIRECTOR", "PRINCIPAL", "VICE_PRINCIPAL", "INNOVATION_CELL_HEAD",
  "ECELL_HEAD", "INCUBATION_HEAD", "AI_CS_DEPT_HEAD", "OTHER",
];

const ALL_STATUSES = [
  "VERIFIED", "NEEDS_MANUAL_REVIEW", "MEETING_SCHEDULED",
  "WON", "LOST", "REPLIED_POSITIVE", "REPLIED_NEGATIVE",
];

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  VERIFIED:             { bg: "#dcfce7", color: "#15803d" },
  NEEDS_MANUAL_REVIEW:  { bg: "#fef9c3", color: "#92400e" },
  CONTACTED:            { bg: "#dbeafe", color: "#1d4ed8" },
  REPLIED_POSITIVE:     { bg: "#ede9fe", color: "#6d28d9" },
  MEETING_SCHEDULED:    { bg: "#fce7f3", color: "#9d174d" },
  WON:                  { bg: "#d1fae5", color: "#065f46" },
  LOST:                 { bg: "#f3f4f6", color: "#6b7280" },
  BOUNCED:              { bg: "#fee2e2", color: "#991b1b" },
  UNSUBSCRIBED:         { bg: "#f3f4f6", color: "#6b7280" },
  REPLIED_NEGATIVE:     { bg: "#fee2e2", color: "#991b1b" },
};

function confidenceColor(c: number) {
  if (c >= 80) return "#15803d";
  if (c >= 60) return "#d97706";
  return "#dc2626";
}

// ─── modal shell ──────────────────────────────────────────────────────────────
function Modal({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: "#fff", borderRadius: 16, padding: 28, width: 460, maxWidth: "95vw", boxShadow: "0 8px 40px rgba(0,0,0,0.18)", border: "1px solid #dceae2" }}
      >
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
  fontSize: 13, color: "#0f1a14", background: "#f8faf9", outline: "none",
};

// ─── edit modal ───────────────────────────────────────────────────────────────
function EditModal({ contact, onClose, onSaved }: {
  contact: ContactRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    full_name: contact.full_name,
    email: contact.email ?? "",
    role: contact.role,
    status: contact.status,
    notes: contact.notes ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  // Only send fields that the backend allows manual edit on
  const isStatusManual = ALL_STATUSES.includes(form.status);

  async function save() {
    if (!isStatusManual) {
      setErr(`Status "${form.status}" is controlled by the pipeline and cannot be set manually.`);
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api(`/api/contacts/${contact.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          full_name: form.full_name.trim() || undefined,
          email: form.email.trim() || undefined,
          role: form.role || undefined,
          status: form.status || undefined,
          notes: form.notes || undefined,
        }),
      });
      onSaved();
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>Edit Contact</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>

        {/* College is read-only — shown for context */}
        <div style={{ background: "#f0f7f3", borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "#3d6b4f" }}>
          🏫 <strong>{contact.college}</strong>
        </div>

        <Field label="Full Name">
          <input style={inputStyle} value={form.full_name} onChange={set("full_name")} />
        </Field>
        <Field label="Email">
          <input style={inputStyle} type="email" value={form.email} onChange={set("email")} placeholder="email@example.com" />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Role">
            <select style={inputStyle} value={form.role} onChange={set("role")}>
              {ALL_ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
            </select>
          </Field>
          <Field label="Status">
            <select style={inputStyle} value={form.status} onChange={set("status")}>
              {ALL_STATUSES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Notes">
          <textarea
            style={{ ...inputStyle, resize: "vertical", minHeight: 72, fontFamily: "inherit" }}
            value={form.notes}
            onChange={set("notes")}
            placeholder="Internal notes…"
          />
        </Field>

        {err && (
          <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626" }}>
            ⚠ {err}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={save} disabled={saving} style={{ background: saving ? "#6b9e7e" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer" }}>
            {saving ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── delete confirm modal ─────────────────────────────────────────────────────
function DeleteModal({ contact, onClose, onDeleted }: {
  contact: ContactRow;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/contacts/${contact.id}`, { method: "DELETE" });
      onDeleted();
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#7f1d1d" }}>Delete Contact</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>
        <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "14px 16px", fontSize: 13, color: "#7f1d1d", lineHeight: 1.6 }}>
          <strong>Permanently delete:</strong><br />
          <span style={{ fontWeight: 700 }}>{contact.full_name}</span> — {contact.role.replaceAll("_", " ")} at {contact.college}<br />
          <span style={{ fontSize: 12, color: "#991b1b" }}>This will also delete all drafts and email history for this contact.</span>
        </div>
        {err && (
          <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626" }}>⚠ {err}</div>
        )}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={confirm} disabled={busy} style={{ background: busy ? "#fca5a5" : "#dc2626", color: "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: busy ? "not-allowed" : "pointer" }}>
            {busy ? "Deleting…" : "Yes, Delete"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────
export default function ContactsPage() {
  const [filter, setFilter] = useState("");
  const [rows, setRows] = useState<ContactRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ContactRow | null>(null);
  const [deleting, setDeleting] = useState<ContactRow | null>(null);

  const load = useCallback(() => {
    const qs = filter ? `?status=${filter.toLowerCase()}&limit=100` : "?limit=100";
    api<{ total: number; items: ContactRow[] }>(`/api/contacts${qs}`)
      .then((d) => { setRows(d.items); setTotal(d.total); setError(null); })
      .catch((e) => setError(String(e)));
  }, [filter]);

  useEffect(load, [load]);

  async function setStatus(id: number, status: string) {
    try {
      await api(`/api/contacts/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
      load();
    } catch (e) { setError(String(e)); }
  }

  if (error) return (
    <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 12, padding: 20, color: "#dc2626" }}>
      ⚠ {error}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* modals */}
      {editing && <EditModal contact={editing} onClose={() => setEditing(null)} onSaved={load} />}
      {deleting && <DeleteModal contact={deleting} onClose={() => setDeleting(null)} onDeleted={load} />}

      {/* header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>
            Contacts
            <span style={{ fontSize: 14, fontWeight: 400, color: "#6b9e7e", marginLeft: 8 }}>
              {total} total
            </span>
          </h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>Decision-makers discovered from college websites</p>
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 14px", fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none", cursor: "pointer" }}
        >
          {FILTERS.map((f) => (
            <option key={f} value={f}>{f === "" ? "All statuses" : f.replaceAll("_", " ")}</option>
          ))}
        </select>
      </div>

      {/* table */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "Role", "College", "Email", "Confidence", "Status", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2", whiteSpace: "nowrap" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => {
              const ss = STATUS_STYLE[c.status] ?? { bg: "#f3f4f6", color: "#6b7280" };
              return (
                <tr key={c.id} style={{ borderTop: "1px solid #f0f7f3", background: i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                  <td style={{ padding: "10px 14px", fontWeight: 600, color: "#0f3622" }}>{c.full_name}</td>
                  <td style={{ padding: "10px 14px" }}>
                    <span style={{ background: "#e8f5ee", color: "#1a5c38", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>
                      {c.role.replaceAll("_", " ")}
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px", color: "#4a7a5c" }}>{c.college}</td>
                  <td style={{ padding: "10px 14px", color: "#4a7a5c", fontFamily: "monospace", fontSize: 12 }}>
                    {c.email ?? <span style={{ color: "#c0d8c8" }}>not found</span>}
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    <span style={{ fontWeight: 700, color: confidenceColor(c.confidence), fontSize: 13 }}>
                      {c.confidence}%
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    <span style={{ background: ss.bg, color: ss.color, borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600 }}>
                      {c.status.replaceAll("_", " ")}
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                    {/* pipeline quick-actions (unchanged from original) */}
                    {c.status === "REPLIED_POSITIVE" && (
                      <button onClick={() => setStatus(c.id, "meeting_scheduled")}
                        style={{ background: "#ede9fe", color: "#6d28d9", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", marginRight: 4 }}>
                        📅 Meeting
                      </button>
                    )}
                    {c.status === "MEETING_SCHEDULED" && (
                      <>
                        <button onClick={() => setStatus(c.id, "won")}
                          style={{ background: "#d1fae5", color: "#065f46", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", marginRight: 4 }}>
                          🏆 Won
                        </button>
                        <button onClick={() => setStatus(c.id, "lost")}
                          style={{ background: "#f3f4f6", color: "#6b7280", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", marginRight: 4 }}>
                          Lost
                        </button>
                      </>
                    )}
                    {/* edit / delete */}
                    <button
                      onClick={() => setEditing(c)}
                      style={{ background: "#e8f5ee", color: "#1a5c38", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", marginRight: 4 }}
                    >
                      ✏ Edit
                    </button>
                    <button
                      onClick={() => setDeleting(c)}
                      style={{ background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer" }}
                    >
                      🗑 Delete
                    </button>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: "40px 16px", textAlign: "center", color: "#94b5a0" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>👤</div>
                  No contacts for this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
