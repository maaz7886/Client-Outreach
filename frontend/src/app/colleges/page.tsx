"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type CollegeRow = {
  id: number; name: string; city: string; state: string;
  website: string | null; naac_grade: string | null; nirf_rank: number | null;
  type: string; contacts: number;
};

const COLLEGE_TYPES = ["GOVERNMENT", "PRIVATE", "AUTONOMOUS", "DEEMED", "UNKNOWN"];

// ─── tiny reusable modal shell ────────────────────────────────────────────────
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
          background: "#fff", borderRadius: 16, padding: 28, width: 480, maxWidth: "95vw",
          boxShadow: "0 8px 40px rgba(0,0,0,0.18)", border: "1px solid #dceae2",
        }}
      >
        {children}
      </div>
    </div>
  );
}

// ─── field component ─────────────────────────────────────────────────────────
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

// ─── edit modal ───────────────────────────────────────────────────────────────
function EditModal({ college, onClose, onSaved }: {
  college: CollegeRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: college.name,
    city: college.city,
    state: college.state,
    website: college.website ?? "",
    naac_grade: college.naac_grade ?? "",
    nirf_rank: college.nirf_rank !== null ? String(college.nirf_rank) : "",
    college_type: college.type,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await api(`/api/colleges/${college.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name.trim() || undefined,
          city: form.city.trim() || undefined,
          state: form.state.trim() || undefined,
          website: form.website.trim() || undefined,
          naac_grade: form.naac_grade.trim() || undefined,
          nirf_rank: form.nirf_rank ? Number(form.nirf_rank) : undefined,
          college_type: form.college_type || undefined,
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
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {/* header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>Edit College</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e", lineHeight: 1 }}>✕</button>
        </div>

        {/* fields */}
        <Field label="Name">
          <input style={inputStyle} value={form.name} onChange={set("name")} />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="City">
            <input style={inputStyle} value={form.city} onChange={set("city")} />
          </Field>
          <Field label="State">
            <input style={inputStyle} value={form.state} onChange={set("state")} />
          </Field>
        </div>
        <Field label="Website">
          <input style={inputStyle} value={form.website} onChange={set("website")} placeholder="https://..." />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <Field label="Type">
            <select style={inputStyle} value={form.college_type} onChange={set("college_type")}>
              {COLLEGE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="NAAC Grade">
            <input style={inputStyle} value={form.naac_grade} onChange={set("naac_grade")} placeholder="A++, A+, A…" />
          </Field>
          <Field label="NIRF Rank">
            <input style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={form.nirf_rank} onChange={set("nirf_rank")} type="number" min="1" placeholder="—" />
          </Field>
        </div>

        {err && (
          <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626" }}>
            ⚠ {err}
          </div>
        )}

        {/* actions */}
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
function DeleteModal({ college, onClose, onDeleted }: {
  college: CollegeRow;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/colleges/${college.id}`, { method: "DELETE" });
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
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#7f1d1d" }}>Delete College</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>
        <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "14px 16px", fontSize: 13, color: "#7f1d1d", lineHeight: 1.6 }}>
          <strong>This will permanently delete:</strong><br />
          <span style={{ fontWeight: 700 }}>{college.name}</span> and all its contacts, drafts, and research data.<br />
          <span style={{ fontSize: 12, color: "#991b1b" }}>This action cannot be undone.</span>
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
export default function CollegesPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<CollegeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CollegeRow | null>(null);
  const [deleting, setDeleting] = useState<CollegeRow | null>(null);

  function load(search = q) {
    api<{ total: number; items: CollegeRow[] }>(
      `/api/colleges?q=${encodeURIComponent(search)}&limit=100`
    )
      .then((d) => { setRows(d.items); setTotal(d.total); setError(null); })
      .catch((e) => setError(String(e)));
  }

  // debounced search
  useEffect(() => {
    const t = setTimeout(() => load(q), 250);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  if (error) return (
    <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 12, padding: 20, color: "#dc2626" }}>
      ⚠ {error}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* modals */}
      {editing && <EditModal college={editing} onClose={() => setEditing(null)} onSaved={() => load()} />}
      {deleting && <DeleteModal college={deleting} onClose={() => setDeleting(null)} onDeleted={() => load()} />}

      {/* header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>
            Colleges
            <span style={{ fontSize: 14, fontWeight: 400, color: "#6b9e7e", marginLeft: 8 }}>
              {total} total
            </span>
          </h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>All colleges in your outreach database</p>
        </div>
        <input
          placeholder="🔍  Search colleges…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{
            border: "1.5px solid #cce0d4", borderRadius: 8,
            padding: "8px 14px", fontSize: 13, color: "#0f1a14",
            background: "#fff", outline: "none", width: 220,
          }}
        />
      </div>

      {/* table */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "City", "State", "Type", "NAAC", "NIRF Rank", "Contacts", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2", whiteSpace: "nowrap" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={c.id} style={{ borderTop: "1px solid #f0f7f3", background: i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                <td style={{ padding: "10px 14px", fontWeight: 600, color: "#0f3622", maxWidth: 200 }}>
                  {c.website ? (
                    <a href={c.website} target="_blank" rel="noreferrer"
                      style={{ color: "#1a5c38", textDecoration: "none" }}
                      onMouseEnter={e => (e.currentTarget.style.textDecoration = "underline")}
                      onMouseLeave={e => (e.currentTarget.style.textDecoration = "none")}
                    >
                      {c.name} ↗
                    </a>
                  ) : c.name}
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c" }}>{c.city}</td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c" }}>{c.state}</td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ background: "#e8f5ee", color: "#1a5c38", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>
                    {c.type}
                  </span>
                </td>
                <td style={{ padding: "10px 14px" }}>
                  {c.naac_grade
                    ? <span style={{ background: "#f0fdf4", color: "#15803d", borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 700 }}>{c.naac_grade}</span>
                    : <span style={{ color: "#c0d8c8" }}>—</span>}
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c" }}>{c.nirf_rank ?? "—"}</td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ background: c.contacts > 0 ? "#e8f5ee" : "#f5f5f5", color: c.contacts > 0 ? "#1a5c38" : "#9ca3af", borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 700 }}>
                    {c.contacts}
                  </span>
                </td>
                {/* actions */}
                <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                  <button
                    onClick={() => setEditing(c)}
                    style={{ background: "#e8f5ee", color: "#1a5c38", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6 }}
                  >
                    ✏ Edit
                  </button>
                  <button
                    onClick={() => setDeleting(c)}
                    style={{ background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, padding: "5px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    🗑 Delete
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: "40px 16px", textAlign: "center", color: "#94b5a0" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>🏫</div>
                  No colleges yet — import a CSV with the CLI:<br />
                  <code style={{ fontSize: 12, background: "#f0f7f3", padding: "2px 6px", borderRadius: 4 }}>
                    docker compose exec api python -m app.cli import-csv colleges.csv
                  </code>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
