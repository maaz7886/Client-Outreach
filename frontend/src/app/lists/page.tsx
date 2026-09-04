"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

type ListRow = {
  id: number;
  name: string;
  description: string | null;
  contact_count: number;
  created_at: string;
  updated_at: string;
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
  fontSize: 13, color: "#0f1a14", background: "#f8faf9", outline: "none",
};

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!name.trim()) {
      setErr("List name is required.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api("/api/lists", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || undefined,
        }),
      });
      onCreated();
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
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>Create List</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>
        <Field label="Name">
          <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Karnataka TPOs" autoFocus />
        </Field>
        <Field label="Description (optional)">
          <textarea
            style={{ ...inputStyle, resize: "vertical", minHeight: 72, fontFamily: "inherit" }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this list for?"
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
            {saving ? "Creating…" : "Create List"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function RenameModal({ list, onClose, onSaved }: {
  list: ListRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(list.name);
  const [description, setDescription] = useState(list.description ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!name.trim()) {
      setErr("List name is required.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api(`/api/lists/${list.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
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
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>Rename List</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>
        <Field label="Name">
          <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Field label="Description (optional)">
          <textarea
            style={{ ...inputStyle, resize: "vertical", minHeight: 72, fontFamily: "inherit" }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this list for?"
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

function DeleteModal({ list, onClose, onDeleted }: {
  list: ListRow;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/lists/${list.id}`, { method: "DELETE" });
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
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#7f1d1d" }}>Delete List</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>
        <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "14px 16px", fontSize: 13, color: "#7f1d1d", lineHeight: 1.6 }}>
          <strong>Permanently delete:</strong><br />
          <span style={{ fontWeight: 700 }}>{list.name}</span>
          {list.contact_count > 0 && (
            <>
              <br />
              <span style={{ fontSize: 12, color: "#991b1b" }}>
                This list contains {list.contact_count} contact{list.contact_count === 1 ? "" : "s"}. Contacts themselves will not be deleted.
              </span>
            </>
          )}
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

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

export default function ListsPage() {
  const [rows, setRows] = useState<ListRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<ListRow | null>(null);
  const [deleting, setDeleting] = useState<ListRow | null>(null);

  const load = useCallback(() => {
    api<{ total: number; items: ListRow[] }>("/api/lists")
      .then((d) => { setRows(d.items); setTotal(d.total); setError(null); })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(load, [load]);

  if (error) return (
    <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 12, padding: 20, color: "#dc2626" }}>
      ⚠ {error}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {creating && <CreateModal onClose={() => setCreating(false)} onCreated={load} />}
      {renaming && <RenameModal list={renaming} onClose={() => setRenaming(null)} onSaved={load} />}
      {deleting && <DeleteModal list={deleting} onClose={() => setDeleting(null)} onDeleted={load} />}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>
            Lists
            <span style={{ fontSize: 14, fontWeight: 400, color: "#6b9e7e", marginLeft: 8 }}>
              {total} total
            </span>
          </h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>Organize contacts into named groups for targeted outreach</p>
        </div>
        <button
          onClick={() => setCreating(true)}
          style={{
            background: "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none",
            borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}
        >
          + New List
        </button>
      </div>

      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "Description", "Contacts", "Created", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2", whiteSpace: "nowrap" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((lst, i) => (
              <tr key={lst.id} style={{ borderTop: "1px solid #f0f7f3", background: i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                <td style={{ padding: "10px 14px", fontWeight: 600, color: "#0f3622" }}>
                  <Link href={`/lists/${lst.id}`} style={{ color: "#0f3622", textDecoration: "none" }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#1a5c38")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "#0f3622")}
                  >
                    {lst.name}
                  </Link>
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", maxWidth: 280 }}>
                  {lst.description ?? <span style={{ color: "#c0d8c8" }}>—</span>}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{
                    background: lst.contact_count > 0 ? "#e8f5ee" : "#f5f5f5",
                    color: lst.contact_count > 0 ? "#1a5c38" : "#9ca3af",
                    borderRadius: 6, padding: "2px 10px", fontSize: 12, fontWeight: 700,
                  }}>
                    {lst.contact_count}
                  </span>
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", whiteSpace: "nowrap" }}>
                  {formatDate(lst.created_at)}
                </td>
                <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                  <Link href={`/lists/${lst.id}`}
                    style={{ display: "inline-block", background: "#e8f5ee", color: "#1a5c38", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6, textDecoration: "none" }}
                  >
                    ✍️ View / Draft
                  </Link>
                  <button
                    onClick={() => setRenaming(lst)}
                    style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1px solid #cce0d4", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6 }}
                  >
                    ✏ Rename
                  </button>
                  <button
                    onClick={() => setDeleting(lst)}
                    style={{ background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    🗑 Delete
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: "40px 16px", textAlign: "center", color: "#94b5a0" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
                  No lists yet — create one to start grouping contacts.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
