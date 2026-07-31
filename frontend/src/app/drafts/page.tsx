"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Draft = {
  id: number; contact: string; college: string; email: string | null;
  touch: number; chosen_subject: string | null; subject_options: string[] | null;
  body_text: string | null; lint: { ok: boolean; errors: string[]; warnings: string[] } | null;
};

export default function DraftsPage() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ items: Draft[] }>("/api/drafts?status=draft&limit=50")
      .then((d) => setDrafts(d.items))
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(load, [load]);

  async function act(id: number, action: "approve" | "reject") {
    setError(null);
    try {
      await api(`/api/drafts/${id}/${action}`, { method: "POST" });
      setNotice(`Draft #${id} ${action}d successfully`);
      setTimeout(() => setNotice(null), 3000);
      load();
    } catch (e) { setError(String(e)); }
  }

  async function saveEdit(draft: Draft, body: string, subject: string) {
    setError(null);
    try {
      await api(`/api/drafts/${draft.id}`, {
        method: "PATCH",
        body: JSON.stringify({ body_text: body, chosen_subject: subject }),
      });
      setNotice(`Draft #${draft.id} saved`);
      setTimeout(() => setNotice(null), 3000);
      load();
    } catch (e) { setError(String(e)); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>
            Approval Queue
            <span style={{ fontSize: 14, fontWeight: 400, color: "#6b9e7e", marginLeft: 8 }}>
              {drafts.length} pending
            </span>
          </h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>Review, edit, and approve email drafts before sending</p>
        </div>
        <div style={{
          background: drafts.length > 0 ? "#fef9c3" : "#e8f5ee",
          color: drafts.length > 0 ? "#92400e" : "#1a5c38",
          borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 700
        }}>
          {drafts.length > 0 ? `⚠ ${drafts.length} awaiting review` : "✓ Queue empty"}
        </div>
      </div>

      {error && (
        <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "12px 16px", fontSize: 13, color: "#dc2626" }}>
          ⚠ {error}
        </div>
      )}
      {notice && (
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "12px 16px", fontSize: 13, color: "#15803d" }}>
          ✓ {notice}
        </div>
      )}

      {drafts.length === 0 && (
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: "48px 24px", textAlign: "center", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>📭</div>
          <p style={{ color: "#4a7a5c", fontWeight: 600, fontSize: 16 }}>Queue is empty</p>
          <p style={{ color: "#94b5a0", fontSize: 13, marginTop: 4 }}>
            Run <code style={{ background: "#f0f7f3", padding: "2px 6px", borderRadius: 4 }}>draft-emails</code> to generate new drafts
          </p>
        </div>
      )}

      {drafts.map((d) => (
        <DraftCard key={d.id} draft={d} onAct={act} onSave={saveEdit} />
      ))}
    </div>
  );
}

function DraftCard({ draft, onAct, onSave }: {
  draft: Draft;
  onAct: (id: number, action: "approve" | "reject") => void;
  onSave: (draft: Draft, body: string, subject: string) => void;
}) {
  const [body, setBody] = useState(draft.body_text ?? "");
  const [subject, setSubject] = useState(draft.chosen_subject ?? "");
  const [editing, setEditing] = useState(false);
  const lintOk = draft.lint?.ok ?? false;

  useEffect(() => {
    setBody(draft.body_text ?? "");
    setSubject(draft.chosen_subject ?? "");
    setEditing(false);
  }, [draft]);

  return (
    <div style={{
      background: "#fff", borderRadius: 14,
      border: `1px solid ${lintOk ? "#dceae2" : "#fecaca"}`,
      boxShadow: "0 2px 8px rgba(15,54,34,0.05)",
      overflow: "hidden"
    }}>
      {/* Card header */}
      <div style={{ background: "#f0f7f3", padding: "14px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid #dceae2" }}>
        <div>
          <span style={{ fontWeight: 700, color: "#0f3622", fontSize: 14 }}>
            {draft.contact}
          </span>
          <span style={{ color: "#94b5a0", margin: "0 8px" }}>·</span>
          <span style={{ color: "#4a7a5c", fontSize: 13 }}>{draft.college}</span>
          {draft.touch > 1 && (
            <span style={{ background: "#dbeafe", color: "#1d4ed8", borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 600, marginLeft: 8 }}>
              Follow-up #{draft.touch - 1}
            </span>
          )}
          <p style={{ color: "#94b5a0", fontSize: 12, margin: "2px 0 0", fontFamily: "monospace" }}>
            {draft.email}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            background: lintOk ? "#d1fae5" : "#fee2e2",
            color: lintOk ? "#065f46" : "#991b1b",
            borderRadius: 20, padding: "4px 12px", fontSize: 11, fontWeight: 700
          }}>
            {lintOk ? "✓ Lint Pass" : "✗ Lint Fail"}
          </span>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: "18px 20px" }}>
        {!lintOk && draft.lint?.errors?.length ? (
          <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", marginBottom: 14 }}>
            {draft.lint.errors.map((e, i) => (
              <p key={i} style={{ fontSize: 12, color: "#dc2626", margin: "2px 0" }}>• {e}</p>
            ))}
          </div>
        ) : null}

        {editing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>Subject</label>
              <select value={subject} onChange={(e) => setSubject(e.target.value)}
                style={{ width: "100%", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px", fontSize: 13, outline: "none" }}>
                {(draft.subject_options ?? [subject]).map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 6 }}>Body</label>
              <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14}
                style={{ width: "100%", boxSizing: "border-box", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "10px 12px", fontFamily: "monospace", fontSize: 12, outline: "none", resize: "vertical" }} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => onSave(draft, body, subject)}
                style={{ background: "#0f3622", color: "#fff", border: "none", borderRadius: 8, padding: "8px 18px", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                💾 Save
              </button>
              <button onClick={() => setEditing(false)}
                style={{ background: "#f0f7f3", color: "#4a7a5c", border: "1px solid #cce0d4", borderRadius: 8, padding: "8px 18px", fontSize: 13, cursor: "pointer" }}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <p style={{ fontWeight: 700, color: "#0f3622", fontSize: 14, marginBottom: 10 }}>
              📧 {draft.chosen_subject}
            </p>
            <pre style={{
              whiteSpace: "pre-wrap", background: "#f8faf9",
              border: "1px solid #e8f0ec", borderRadius: 10,
              padding: "14px 16px", fontSize: 12, color: "#2d4a38",
              lineHeight: 1.6, marginBottom: 14, fontFamily: "inherit"
            }}>
              {draft.body_text}
            </pre>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => onAct(draft.id, "approve")}
                disabled={!lintOk}
                style={{
                  background: lintOk ? "linear-gradient(135deg,#0f3622,#1a5c38)" : "#e5e7eb",
                  color: lintOk ? "#fff" : "#9ca3af",
                  border: "none", borderRadius: 8, padding: "8px 18px",
                  fontSize: 13, fontWeight: 700, cursor: lintOk ? "pointer" : "not-allowed"
                }}>
                ✓ Approve
              </button>
              <button onClick={() => setEditing(true)}
                style={{ background: "#f0f7f3", color: "#1a5c38", border: "1px solid #cce0d4", borderRadius: 8, padding: "8px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                ✏ Edit
              </button>
              <button onClick={() => onAct(draft.id, "reject")}
                style={{ background: "#fff5f5", color: "#dc2626", border: "1px solid #fecaca", borderRadius: 8, padding: "8px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                ✗ Reject
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
