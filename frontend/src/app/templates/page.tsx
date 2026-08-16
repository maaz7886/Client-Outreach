"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type TemplateRow = {
  id: number;
  name: string;
  description: string | null;
  additional_context: string | null;
  formatting_notes: string | null;
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
          background: "#fff", borderRadius: 16, padding: 28, width: 520, maxWidth: "95vw",
          maxHeight: "90vh", overflow: "auto",
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

const textareaStyle: React.CSSProperties = {
  ...inputStyle, resize: "vertical", minHeight: 90, fontFamily: "inherit",
};

function TemplateFormModal({
  title,
  initial,
  onClose,
  onSave,
}: {
  title: string;
  initial: {
    name: string;
    description: string;
    additional_context: string;
    formatting_notes: string;
  };
  onClose: () => void;
  onSave: (data: typeof initial) => Promise<void>;
}) {
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!form.name.trim()) {
      setErr("Template name is required.");
      return;
    }
    if (!form.additional_context.trim() && !form.formatting_notes.trim()) {
      setErr("Provide additional context and/or formatting notes.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSave({
        name: form.name.trim(),
        description: form.description.trim(),
        additional_context: form.additional_context.trim(),
        formatting_notes: form.formatting_notes.trim(),
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
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Name *</label>
        <input style={inputStyle} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. AI Workshop Intro" />
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Description (optional)</label>
        <input style={inputStyle} value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="When to use this template" />
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Additional context</label>
        <textarea style={textareaStyle} value={form.additional_context} onChange={(e) => setForm((f) => ({ ...f, additional_context: e.target.value }))} placeholder="Extra talking points, offers, or constraints for the AI…" />
        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f" }}>Formatting notes</label>
        <textarea style={textareaStyle} value={form.formatting_notes} onChange={(e) => setForm((f) => ({ ...f, formatting_notes: e.target.value }))} placeholder="Tone, structure, bullet points, sign-off style…" />
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

function PreviewModal({ template, onClose }: { template: TemplateRow; onClose: () => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ preview: string }>(`/api/templates/${template.id}/preview`, {
      method: "POST",
      body: JSON.stringify({}),
    })
      .then((d) => { setPreview(d.preview); setErr(null); })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [template.id]);

  return (
    <Modal onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>Preview: {template.name}</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
        </div>
        <p style={{ margin: 0, fontSize: 12, color: "#6b9e7e" }}>
          Shows how this template augments the draft-generation prompt (sample fact sheet).
        </p>
        {loading && <p style={{ fontSize: 13, color: "#94b5a0" }}>Loading preview…</p>}
        {err && <p style={{ color: "#dc2626", fontSize: 12 }}>⚠ {err}</p>}
        {preview && (
          <pre style={{
            whiteSpace: "pre-wrap", background: "#f8faf9", border: "1px solid #e8f0ec",
            borderRadius: 10, padding: "14px 16px", fontSize: 12, color: "#2d4a38",
            lineHeight: 1.6, margin: 0, fontFamily: "inherit", maxHeight: 360, overflow: "auto",
          }}>
            {preview}
          </pre>
        )}
      </div>
    </Modal>
  );
}

export default function TemplatesPage() {
  const [rows, setRows] = useState<TemplateRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<TemplateRow | null>(null);
  const [previewing, setPreviewing] = useState<TemplateRow | null>(null);

  const load = useCallback(() => {
    api<{ total: number; items: TemplateRow[] }>("/api/templates")
      .then((d) => { setRows(d.items); setError(null); })
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
        <TemplateFormModal
          title="Create Email Template"
          initial={{ name: "", description: "", additional_context: "", formatting_notes: "" }}
          onClose={() => setCreating(false)}
          onSave={async (data) => {
            await api("/api/templates", {
              method: "POST",
              body: JSON.stringify({
                name: data.name,
                description: data.description || undefined,
                additional_context: data.additional_context || undefined,
                formatting_notes: data.formatting_notes || undefined,
              }),
            });
            load();
          }}
        />
      )}
      {editing && (
        <TemplateFormModal
          title="Edit Email Template"
          initial={{
            name: editing.name,
            description: editing.description ?? "",
            additional_context: editing.additional_context ?? "",
            formatting_notes: editing.formatting_notes ?? "",
          }}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            await api(`/api/templates/${editing.id}`, {
              method: "PATCH",
              body: JSON.stringify({
                name: data.name,
                description: data.description || null,
                additional_context: data.additional_context || null,
                formatting_notes: data.formatting_notes || null,
              }),
            });
            load();
          }}
        />
      )}
      {previewing && <PreviewModal template={previewing} onClose={() => setPreviewing(null)} />}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>Email Templates</h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>
            Reusable context and formatting hints — appended to draft generation, not the core LLM prompt
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          style={{
            background: "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none",
            borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}
        >
          + New Template
        </button>
      </div>

      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "Description", "Context", "Formatting", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={t.id} style={{ borderTop: "1px solid #f0f7f3", background: i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                <td style={{ padding: "10px 14px", fontWeight: 600, color: "#0f3622" }}>{t.name}</td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", maxWidth: 180 }}>
                  {t.description ?? <span style={{ color: "#c0d8c8" }}>—</span>}
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", maxWidth: 200 }}>
                  {t.additional_context
                    ? <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.additional_context}</span>
                    : <span style={{ color: "#c0d8c8" }}>—</span>}
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", maxWidth: 200 }}>
                  {t.formatting_notes
                    ? <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.formatting_notes}</span>
                    : <span style={{ color: "#c0d8c8" }}>—</span>}
                </td>
                <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                  <button onClick={() => setPreviewing(t)} style={{ background: "#fffbeb", color: "#92400e", border: "1px solid #fde68a", borderRadius: 6, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6 }}>Preview</button>
                  <button onClick={() => setEditing(t)} style={{ background: "#e8f5ee", color: "#1a5c38", border: "none", borderRadius: 6, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6 }}>✏ Edit</button>
                  <button
                    onClick={async () => {
                      if (!confirm(`Delete template "${t.name}"?`)) return;
                      await api(`/api/templates/${t.id}`, { method: "DELETE" });
                      load();
                    }}
                    style={{ background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, padding: "5px 10px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                  >
                    🗑 Delete
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: "32px 16px", textAlign: "center", color: "#94b5a0" }}>
                  No templates yet — create one to use when generating drafts.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
