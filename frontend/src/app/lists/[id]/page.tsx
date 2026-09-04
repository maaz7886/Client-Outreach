"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, apiUpload } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type ContactRow = {
  id: number;
  full_name: string;
  role: string;
  college: string;
  college_id: number;
  email: string | null;
  designation: string | null;
  confidence: number;
  status: string;
  research_status: string;
  draft_status: string | null;
  last_contact_at: string | null;
  created_at: string | null;
};

type ListDetail = {
  id: number;
  name: string;
  description: string | null;
  contact_count: number;
  created_at: string;
  updated_at: string;
  contacts: ContactRow[];
};

type TemplateOption = {
  id: number;
  name: string;
  description: string | null;
};

type DraftResult = {
  drafted: number;
  lint_passed: number;
  lint_failed: number;
  list_id: number;
  list_name: string;
  eligible_contacts: number;
  template_id?: number;
  template_name?: string | null;
  errors?: string[];
};

type ListSummary = { id: number; name: string; contact_count: number };

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  VERIFIED:           { bg: "#d1fae5", color: "#065f46" },
  CONTACTED:          { bg: "#dbeafe", color: "#1e40af" },
  REPLIED_POSITIVE:   { bg: "#d1fae5", color: "#065f46" },
  REPLIED_NEGATIVE:   { bg: "#fee2e2", color: "#991b1b" },
  MEETING_SCHEDULED:  { bg: "#fef3c7", color: "#92400e" },
  WON:                { bg: "#d1fae5", color: "#065f46" },
  LOST:               { bg: "#f3f4f6", color: "#6b7280" },
  DISCOVERED:         { bg: "#f3f4f6", color: "#6b7280" },
  NEEDS_MANUAL_REVIEW:{ bg: "#fef3c7", color: "#92400e" },
};

const DRAFT_COLORS: Record<string, { bg: string; color: string }> = {
  DRAFT:    { bg: "#fef3c7", color: "#92400e" },
  APPROVED: { bg: "#d1fae5", color: "#065f46" },
  REJECTED: { bg: "#fee2e2", color: "#991b1b" },
  QUEUED:   { bg: "#dbeafe", color: "#1e40af" },
  SENT:     { bg: "#f0f9ff", color: "#0369a1" },
};

function badge(label: string, colorMap: Record<string, { bg: string; color: string }>, fallback = { bg: "#f3f4f6", color: "#6b7280" }) {
  const c = colorMap[label] ?? fallback;
  return (
    <span style={{ background: c.bg, color: c.color, borderRadius: 6, padding: "2px 9px", fontSize: 11, fontWeight: 700, whiteSpace: "nowrap" }}>
      {label.replace(/_/g, " ")}
    </span>
  );
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); }
  catch { return iso; }
}

const inputStyle: React.CSSProperties = {
  border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
  fontSize: 13, color: "#0f1a14", background: "#f8faf9", outline: "none", width: "100%", boxSizing: "border-box",
};

// ─── Modal wrapper ────────────────────────────────────────────────────────────

function Modal({ onClose, children, wide }: { onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.38)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: "#fff", borderRadius: 16, padding: 28,
        width: wide ? 680 : 480, maxWidth: "96vw", maxHeight: "90vh", overflowY: "auto",
        boxShadow: "0 8px 40px rgba(0,0,0,0.18)", border: "1px solid #dceae2",
      }}>
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
      <h2 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#0f3622" }}>{title}</h2>
      <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#6b9e7e" }}>✕</button>
    </div>
  );
}

// ─── View Contact Modal ───────────────────────────────────────────────────────

function ViewContactModal({ contact, onClose }: { contact: ContactRow; onClose: () => void }) {
  const fields: { label: string; value: string | null | undefined }[] = [
    { label: "Full Name", value: contact.full_name },
    { label: "Role", value: contact.role },
    { label: "Designation", value: contact.designation },
    { label: "College", value: contact.college },
    { label: "Email", value: contact.email },
    { label: "Status", value: contact.status },
    { label: "Research Status", value: contact.research_status },
    { label: "Draft Status", value: contact.draft_status },
    { label: "Confidence", value: `${contact.confidence}%` },
    { label: "Last Contacted", value: formatDate(contact.last_contact_at) },
    { label: "Created Date", value: formatDate(contact.created_at) },
  ];
  return (
    <Modal onClose={onClose}>
      <ModalHeader title={`👤 ${contact.full_name}`} onClose={onClose} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        {fields.map(({ label, value }) => (
          <div key={label} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>
            <span style={{ fontSize: 13, color: "#0f1a14", fontWeight: 500 }}>{value || "—"}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
        <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
          Close
        </button>
      </div>
    </Modal>
  );
}

// ─── Edit Contact Modal ───────────────────────────────────────────────────────

const ROLES = [
  "TPO", "PLACEMENT_DIRECTOR", "TRAINING_OFFICER", "HOD", "DEAN",
  "DIRECTOR", "PRINCIPAL", "VICE_PRINCIPAL", "INNOVATION_CELL_HEAD",
  "ECELL_HEAD", "INCUBATION_HEAD", "AI_CS_DEPT_HEAD", "OTHER",
];

const STATUSES = [
  "VERIFIED", "NEEDS_MANUAL_REVIEW", "MEETING_SCHEDULED", "WON", "LOST",
  "REPLIED_POSITIVE", "REPLIED_NEGATIVE",
];

function EditContactModal({ contact, onClose, onSaved }: {
  contact: ContactRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [fullName, setFullName] = useState(contact.full_name);
  const [email, setEmail] = useState(contact.email ?? "");
  const [role, setRole] = useState(contact.role);
  const [status, setStatus] = useState(contact.status);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!fullName.trim()) { setErr("Full name is required."); return; }
    setSaving(true); setErr(null);
    try {
      await api(`/api/contacts/${contact.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fullName.trim(),
          email: email.trim() || null,
          role: role,
          status: status,
        }),
      });
      onSaved();
      onClose();
    } catch (e) { setErr(String(e)); }
    finally { setSaving(false); }
  }

  const labelStyle: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", display: "block", marginBottom: 5 };
  const selectStyle = { ...inputStyle };

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="✏ Edit Contact" onClose={onClose} />
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <label style={labelStyle}>Full Name *</label>
          <input style={inputStyle} value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Email</label>
          <input style={inputStyle} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="contact@college.ac.in" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label style={labelStyle}>Role</label>
            <select style={selectStyle} value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Status</label>
            <select style={selectStyle} value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
            </select>
          </div>
        </div>
        {err && (
          <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626" }}>
            ⚠ {err}
          </div>
        )}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 }}>
          <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={save} disabled={saving} style={{ background: saving ? "#6b9e7e" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer" }}>
            {saving ? "Saving…" : "💾 Save Changes"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Delete Contact Modal ─────────────────────────────────────────────────────

function DeleteContactModal({ contact, onClose, onDeleted }: {
  contact: ContactRow;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    setBusy(true); setErr(null);
    try {
      await api(`/api/contacts/${contact.id}`, { method: "DELETE" });
      onDeleted();
      onClose();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="🗑 Delete Contact" onClose={onClose} />
      <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "14px 16px", fontSize: 13, color: "#7f1d1d", lineHeight: 1.6, marginBottom: 16 }}>
        <strong>Permanently delete contact:</strong><br />
        <span style={{ fontWeight: 700 }}>{contact.full_name}</span> &lt;{contact.email ?? "no email"}&gt;<br />
        <span style={{ fontSize: 12, color: "#991b1b" }}>This also deletes all their drafts and messages. This cannot be undone.</span>
      </div>
      {err && <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626", marginBottom: 12 }}>⚠ {err}</div>}
      <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
        <button onClick={confirm} disabled={busy} style={{ background: busy ? "#fca5a5" : "#dc2626", color: "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: busy ? "not-allowed" : "pointer" }}>
          {busy ? "Deleting…" : "Yes, Delete"}
        </button>
      </div>
    </Modal>
  );
}

// ─── Move/Copy Modal ──────────────────────────────────────────────────────────

function MoveOrCopyModal({ contactIds, sourceListId, mode, allLists, onClose, onDone }: {
  contactIds: number[];
  sourceListId: number;
  mode: "move" | "copy";
  allLists: ListSummary[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [targetId, setTargetId] = useState<number | "">(
    allLists.find((l) => l.id !== sourceListId)?.id ?? ""
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const otherLists = allLists.filter((l) => l.id !== sourceListId);

  async function confirm() {
    if (!targetId) { setErr("Select a target list."); return; }
    setBusy(true); setErr(null);
    try {
      const endpoint = mode === "move" ? "bulk-move" : "bulk-copy";
      await api(`/api/lists/${sourceListId}/contacts/${endpoint}`, {
        method: "POST",
        body: JSON.stringify({ contact_ids: contactIds, target_list_id: targetId }),
      });
      onDone();
      onClose();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal onClose={onClose}>
      <ModalHeader title={mode === "move" ? "📦 Move Contacts" : "📋 Copy Contacts"} onClose={onClose} />
      <p style={{ fontSize: 13, color: "#4a7a5c", marginBottom: 14 }}>
        {mode === "move" ? "Move" : "Copy"} <strong>{contactIds.length}</strong> selected contact{contactIds.length === 1 ? "" : "s"} to:
      </p>
      {otherLists.length === 0 ? (
        <p style={{ fontSize: 13, color: "#92400e", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "10px 12px" }}>
          No other lists available. Create another list first.
        </p>
      ) : (
        <select
          style={inputStyle}
          value={targetId}
          onChange={(e) => setTargetId(Number(e.target.value))}
        >
          {otherLists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.contact_count} contacts)</option>)}
        </select>
      )}
      {err && <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626", marginTop: 12 }}>⚠ {err}</div>}
      <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 18 }}>
        <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
        <button onClick={confirm} disabled={busy || !targetId || otherLists.length === 0} style={{ background: busy ? "#6b9e7e" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: busy ? "not-allowed" : "pointer" }}>
          {busy ? "Working…" : mode === "move" ? "📦 Move" : "📋 Copy"}
        </button>
      </div>
    </Modal>
  );
}

// ─── Add Existing Contact Modal ───────────────────────────────────────────────

function AddExistingContactModal({ listId, onClose, onAdded }: {
  listId: number;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ id: number; full_name: string; college: string; email: string | null }[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api<{ items: { id: number; full_name: string; college: string; email: string | null }[] }>(
        `/api/contacts?limit=30`
      );
      const q = query.toLowerCase();
      setResults(res.items.filter((c) =>
        c.full_name.toLowerCase().includes(q) ||
        (c.email ?? "").toLowerCase().includes(q) ||
        c.college.toLowerCase().includes(q)
      ));
    } catch (e) { setErr(String(e)); }
    finally { setSearching(false); }
  }

  function toggle(id: number) {
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  async function addSelected() {
    if (!selected.length) return;
    setBusy(true); setErr(null);
    try {
      await api(`/api/lists/${listId}/contacts/add-existing`, {
        method: "POST",
        body: JSON.stringify({ contact_ids: selected }),
      });
      onAdded();
      onClose();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal onClose={onClose} wide>
      <ModalHeader title="➕ Add Existing Contact" onClose={onClose} />
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          style={{ ...inputStyle, flex: 1 }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Search by name, email, or college…"
        />
        <button onClick={search} disabled={searching} style={{ background: "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "8px 18px", fontSize: 13, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}>
          {searching ? "…" : "Search"}
        </button>
      </div>
      {results.length > 0 && (
        <div style={{ border: "1px solid #dceae2", borderRadius: 10, overflow: "hidden", marginBottom: 14 }}>
          <div style={{ background: "#f0f7f3", padding: "8px 14px", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            {results.length} result{results.length === 1 ? "" : "s"} — check to add
          </div>
          {results.map((c) => (
            <label key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", borderTop: "1px solid #f0f7f3", cursor: "pointer", background: selected.includes(c.id) ? "#f0fdf4" : "#fff" }}>
              <input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} />
              <div>
                <span style={{ fontWeight: 600, color: "#0f3622", fontSize: 13 }}>{c.full_name}</span>
                <span style={{ color: "#6b9e7e", fontSize: 12, marginLeft: 8 }}>{c.college}</span>
                {c.email && <span style={{ color: "#94b5a0", fontSize: 11, display: "block" }}>{c.email}</span>}
              </div>
            </label>
          ))}
        </div>
      )}
      {err && <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626", marginBottom: 12 }}>⚠ {err}</div>}
      <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
        <button onClick={addSelected} disabled={busy || !selected.length} style={{ background: !selected.length ? "#e5e7eb" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: !selected.length ? "#9ca3af" : "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: !selected.length ? "not-allowed" : "pointer" }}>
          {busy ? "Adding…" : `➕ Add ${selected.length || ""} Selected`}
        </button>
      </div>
    </Modal>
  );
}

// ─── Import CSV for this list ─────────────────────────────────────────────────

function ImportCsvModal({ listId, listName, onClose, onImported }: {
  listId: number;
  listName: string;
  onClose: () => void;
  onImported: () => void;
}) {
  const [csvText, setCsvText] = useState("");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setCsvFile(file);
    if (file) file.text().then(setCsvText);
  }

  async function doImport() {
    if (!csvText) { setErr("Upload a CSV file first."); return; }
    setBusy(true); setErr(null); setResult(null);
    try {
      const res = await api<{ contacts_added: number; contacts_skipped: number; message: string }>(
        "/api/contacts/import-csv",
        {
          method: "POST",
          body: JSON.stringify({ csv_text: csvText, list_id: listId }),
        }
      );
      setResult(`✓ ${res.message} Added: ${res.contacts_added}, Skipped: ${res.contacts_skipped}`);
      onImported();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="📥 Import CSV to this List" onClose={onClose} />
      <p style={{ fontSize: 13, color: "#4a7a5c", marginBottom: 14 }}>
        Importing into: <strong>{listName}</strong>. Duplicates are reused — only the list association is added.
      </p>
      <label style={{ display: "flex", flexDirection: "column", alignItems: "center", border: "2px dashed #6dbd94", borderRadius: 10, padding: "20px 16px", cursor: "pointer", background: csvFile ? "#f0fdf4" : "#fafcfb", gap: 6, marginBottom: 14 }}>
        <span style={{ fontSize: 28 }}>{csvFile ? "✅" : "📂"}</span>
        <span style={{ fontWeight: 700, color: "#1a5c38", fontSize: 13 }}>{csvFile ? csvFile.name : "Click to choose CSV"}</span>
        <span style={{ fontSize: 11, color: "#6b9e7e" }}>college_name, city, state, website, tpo_name, tpo_email, director_name, director_email</span>
        <input type="file" accept=".csv,.txt" onChange={handleFile} style={{ display: "none" }} />
      </label>
      {err && <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#dc2626", marginBottom: 12 }}>⚠ {err}</div>}
      {result && <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#15803d", marginBottom: 12 }}>{result}</div>}
      <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
        <button onClick={onClose} style={{ background: "#f0f7f3", color: "#3d6b4f", border: "1.5px solid #cce0d4", borderRadius: 8, padding: "9px 20px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Close</button>
        <button onClick={doImport} disabled={busy || !csvText} style={{ background: busy || !csvText ? "#e5e7eb" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: busy || !csvText ? "#9ca3af" : "#fff", border: "none", borderRadius: 8, padding: "9px 24px", fontSize: 13, fontWeight: 700, cursor: busy || !csvText ? "not-allowed" : "pointer" }}>
          {busy ? "Importing…" : "📥 Import"}
        </button>
      </div>
    </Modal>
  );
}

// ─── Generate Drafts panel ────────────────────────────────────────────────────

function GenerateDraftsPanel({ listId, listName, templates }: {
  listId: number;
  listName: string;
  templates: TemplateOption[];
}) {
  const [templateId, setTemplateId] = useState<string>("none");
  const [limit, setLimit] = useState("50");
  const [drafting, setDrafting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  async function generate() {
    setDrafting(true); setResult(null); setIsError(false);
    try {
      const params = new URLSearchParams({ limit: limit || "50" });
      if (templateId !== "none") params.set("template_id", templateId);
      const res = await api<DraftResult>(
        `/api/lists/${listId}/draft-emails?${params.toString()}`,
        { method: "POST" },
      );
      if (res.eligible_contacts === 0) {
        setIsError(false);
        setResult(`No eligible contacts — "${listName}" has no contacts with VERIFIED or CONTACTED status.`);
      } else {
        const tmplLabel = res.template_name ? ` using template "${res.template_name}"` : "";
        const errNote = res.errors?.length
          ? ` (${res.errors.length} failed: ${res.errors[0]}${res.errors.length > 1 ? "…" : ""})`
          : "";
        setResult(
          `✓ Generated ${res.drafted} draft${res.drafted === 1 ? "" : "s"} for "${listName}"${tmplLabel} — ` +
          `${res.lint_passed} passed lint, ${res.lint_failed} need editing.${errNote}`,
        );
        if (res.errors?.length) setIsError(true);
      }
    } catch (e) {
      setIsError(true);
      setResult(e instanceof Error ? e.message : String(e));
    } finally {
      setDrafting(false);
    }
  }

  return (
    <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
      <div style={{ background: "linear-gradient(135deg,#0f3622,#1a5c38)", padding: "16px 22px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>✍️</span>
          <div>
            <h2 style={{ color: "#fff", fontSize: 15, fontWeight: 800, margin: 0 }}>Generate Drafts</h2>
            <p style={{ color: "#a8dfbe", fontSize: 12, margin: "2px 0 0" }}>AI writes a personalised outreach email for every eligible contact in this list</p>
          </div>
        </div>
      </div>

      <div style={{ padding: "18px 22px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "12px 16px", fontSize: 12, color: "#15803d", lineHeight: 1.6 }}>
          <strong>Only contacts already in this list are processed.</strong> No CSV upload needed.
          Works for contacts with <strong>VERIFIED</strong> or <strong>CONTACTED</strong> status.
          Drafts that are already approved/sent are left unchanged; DRAFT or REJECTED drafts are regenerated.
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, flex: "1 1 200px", minWidth: 180 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>Email Template (optional)</label>
            <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} style={{ border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px", fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none" }}>
              <option value="none">— No template (default prompt) —</option>
              {templates.map((t) => (
                <option key={t.id} value={String(t.id)}>{t.name}{t.description ? ` — ${t.description}` : ""}</option>
              ))}
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, width: 110 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>Limit</label>
            <input type="number" min={1} max={200} value={limit} onChange={(e) => setLimit(e.target.value)}
              style={{ border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px", fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none", width: "100%" }} />
          </div>
          <button onClick={generate} disabled={drafting}
            style={{ background: drafting ? "#6b9e7e" : "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "9px 26px", fontSize: 13, fontWeight: 700, cursor: drafting ? "not-allowed" : "pointer", whiteSpace: "nowrap", alignSelf: "flex-end" }}>
            {drafting ? "Generating…" : "✍️ Generate Drafts"}
          </button>
        </div>

        {result && (
          <div style={{ background: isError ? "#fff5f5" : "#f0fdf4", border: `1px solid ${isError ? "#fecaca" : "#bbf7d0"}`, borderRadius: 10, padding: "12px 16px", fontSize: 13, color: isError ? "#dc2626" : "#15803d", lineHeight: 1.6 }}>
            {isError ? "⚠ " : ""}{result}
            {!isError && (
              <div style={{ marginTop: 8 }}>
                <a href="/drafts" style={{ display: "inline-block", background: "#15803d", color: "#fff", borderRadius: 8, padding: "6px 16px", fontSize: 12, fontWeight: 700, textDecoration: "none" }}>
                  → Open Approval Queue
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ListDetailPage() {
  const params = useParams();
  const router = useRouter();
  const listId = Number(params.id);

  const [list, setList] = useState<ListDetail | null>(null);
  const [templates, setTemplates] = useState<TemplateOption[]>([]);
  const [allLists, setAllLists] = useState<ListSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Selection state
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // Modal state
  const [viewContact, setViewContact] = useState<ContactRow | null>(null);
  const [editContact, setEditContact] = useState<ContactRow | null>(null);
  const [deleteContact, setDeleteContact] = useState<ContactRow | null>(null);
  const [showAddExisting, setShowAddExisting] = useState(false);
  const [showImportCsv, setShowImportCsv] = useState(false);
  const [bulkAction, setBulkAction] = useState<"move" | "copy" | null>(null);

  const load = useCallback(() => {
    api<ListDetail>(`/api/lists/${listId}`)
      .then((d) => { setList(d); setError(null); setSelected(new Set()); })
      .catch((e) => setError(String(e)));
  }, [listId]);

  useEffect(() => {
    load();
    api<{ total: number; items: TemplateOption[] }>("/api/templates")
      .then((d) => setTemplates(d.items)).catch(() => null);
    api<{ total: number; items: ListSummary[] }>("/api/lists")
      .then((d) => setAllLists(d.items)).catch(() => null);
  }, [load]);

  function showNotice(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(null), 4000);
  }

  // ── Selection helpers ──
  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function selectAll() {
    setSelected(new Set((list?.contacts ?? []).map((c) => c.id)));
  }
  function clearAll() { setSelected(new Set()); }

  // ── Bulk remove from list ──
  async function bulkRemoveFromList() {
    if (!selected.size) return;
    try {
      const res = await api<{ removed: number }>(`/api/lists/${listId}/contacts/bulk-remove`, {
        method: "POST",
        body: JSON.stringify({ contact_ids: Array.from(selected) }),
      });
      showNotice(`✓ Removed ${res.removed} contact${res.removed === 1 ? "" : "s"} from this list.`);
      load();
    } catch (e) { setError(String(e)); }
  }

  // ── Remove single contact from list ──
  async function removeFromList(contactId: number) {
    try {
      await api(`/api/lists/${listId}/contacts/${contactId}`, { method: "DELETE" });
      showNotice("✓ Contact removed from this list.");
      load();
    } catch (e) { setError(String(e)); }
  }

  // ── Export CSV ──
  function exportCsv() {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const url = `${base}/api/lists/${listId}/export-csv`;
    const a = document.createElement("a");
    a.href = token ? `${url}?token=${encodeURIComponent(token)}` : url;
    a.download = "";
    // Use fetch with auth header for proper download
    fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => r.blob())
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        a.href = blobUrl;
        a.download = `${list?.name ?? "list"}_contacts.csv`;
        a.click();
        URL.revokeObjectURL(blobUrl);
      })
      .catch((e) => setError(String(e)));
  }

  if (error) return (
    <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 12, padding: 20, color: "#dc2626" }}>⚠ {error}</div>
  );
  if (!list) return (
    <div style={{ color: "#6b9e7e", padding: 32, textAlign: "center", fontSize: 14 }}>Loading…</div>
  );

  const verifiedCount = list.contacts.filter((c) => c.status === "VERIFIED" || c.status === "CONTACTED").length;
  const selectedArr = Array.from(selected);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Modals */}
      {viewContact && <ViewContactModal contact={viewContact} onClose={() => setViewContact(null)} />}
      {editContact && (
        <EditContactModal
          contact={editContact}
          onClose={() => setEditContact(null)}
          onSaved={() => { load(); showNotice("✓ Contact updated."); }}
        />
      )}
      {deleteContact && (
        <DeleteContactModal
          contact={deleteContact}
          onClose={() => setDeleteContact(null)}
          onDeleted={() => { load(); showNotice("✓ Contact deleted."); }}
        />
      )}
      {showAddExisting && (
        <AddExistingContactModal
          listId={listId}
          onClose={() => setShowAddExisting(false)}
          onAdded={() => { load(); showNotice("✓ Contacts added to list."); }}
        />
      )}
      {showImportCsv && (
        <ImportCsvModal
          listId={listId}
          listName={list.name}
          onClose={() => setShowImportCsv(false)}
          onImported={() => { load(); showNotice("✓ CSV imported."); }}
        />
      )}
      {bulkAction && (
        <MoveOrCopyModal
          contactIds={selectedArr}
          sourceListId={listId}
          mode={bulkAction}
          allLists={allLists}
          onClose={() => setBulkAction(null)}
          onDone={() => { load(); showNotice(`✓ Contacts ${bulkAction === "move" ? "moved" : "copied"}.`); }}
        />
      )}

      {/* Breadcrumb + header */}
      <div>
        <button
          onClick={() => router.push("/lists")}
          style={{ background: "none", border: "none", cursor: "pointer", color: "#6b9e7e", fontSize: 12, fontWeight: 600, padding: 0, marginBottom: 8, display: "flex", alignItems: "center", gap: 4 }}
        >
          ← Back to Lists
        </button>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>{list.name}</h1>
          <span style={{ fontSize: 13, color: "#6b9e7e" }}>
            {list.contact_count} contact{list.contact_count === 1 ? "" : "s"}
            {verifiedCount > 0 && ` · ${verifiedCount} eligible for drafts`}
          </span>
        </div>
        {list.description && (
          <p style={{ color: "#4a7a5c", fontSize: 13, marginTop: 4, marginBottom: 0 }}>{list.description}</p>
        )}
        <p style={{ color: "#94b5a0", fontSize: 11, marginTop: 4, marginBottom: 0 }}>
          Created {formatDate(list.created_at)} · Updated {formatDate(list.updated_at)}
        </p>
      </div>

      {/* Notices */}
      {notice && (
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "12px 16px", fontSize: 13, color: "#15803d" }}>
          {notice}
        </div>
      )}

      {/* Generate Drafts panel */}
      <GenerateDraftsPanel listId={list.id} listName={list.name} templates={templates} />

      {/* Contacts table */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>

        {/* Table header + toolbar */}
        <div style={{ padding: "14px 18px", borderBottom: "1px solid #dceae2" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, color: "#0f3622", margin: 0, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Contacts in this list
              </h2>
              <span style={{ fontSize: 12, color: "#6b9e7e" }}>{list.contact_count} total</span>
              {selected.size > 0 && (
                <span style={{ background: "#dbeafe", color: "#1e40af", borderRadius: 6, padding: "2px 10px", fontSize: 12, fontWeight: 700 }}>
                  {selected.size} selected
                </span>
              )}
            </div>

            {/* Toolbar buttons */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {selected.size > 0 ? (
                <>
                  <button onClick={() => setBulkAction("move")}
                    style={{ background: "#fef3c7", color: "#92400e", border: "1px solid #fde68a", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                    📦 Move Selected
                  </button>
                  <button onClick={() => setBulkAction("copy")}
                    style={{ background: "#dbeafe", color: "#1e40af", border: "1px solid #bfdbfe", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                    📋 Copy Selected
                  </button>
                  <button onClick={bulkRemoveFromList}
                    style={{ background: "#fee2e2", color: "#dc2626", border: "1px solid #fecaca", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                    🗑 Remove From List
                  </button>
                  <button onClick={clearAll}
                    style={{ background: "#f0f7f3", color: "#4a7a5c", border: "1px solid #cce0d4", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
                    ✕ Clear
                  </button>
                </>
              ) : (
                <>
                  <button onClick={() => setShowAddExisting(true)}
                    style={{ background: "#e8f5ee", color: "#1a5c38", border: "1px solid #cce0d4", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                    ➕ Add Contact
                  </button>
                  <button onClick={() => setShowImportCsv(true)}
                    style={{ background: "#e8f5ee", color: "#1a5c38", border: "1px solid #cce0d4", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                    📥 Import CSV
                  </button>
                  <button onClick={exportCsv}
                    style={{ background: "#e8f5ee", color: "#1a5c38", border: "1px solid #cce0d4", borderRadius: 6, padding: "6px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                    📤 Export CSV
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Table */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ background: "#f0f7f3" }}>
                <th style={{ padding: "9px 14px", textAlign: "center", width: 40, borderBottom: "1px solid #dceae2" }}>
                  <input
                    type="checkbox"
                    checked={list.contacts.length > 0 && selected.size === list.contacts.length}
                    onChange={(e) => e.target.checked ? selectAll() : clearAll()}
                    title="Select all"
                  />
                </th>
                {["Name", "Email", "Designation", "College", "Status", "Research", "Draft", "Last Contacted", "Created", "Actions"].map((h) => (
                  <th key={h} style={{ padding: "9px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2", whiteSpace: "nowrap" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.contacts.map((c, i) => (
                <tr key={c.id} style={{ borderTop: "1px solid #f0f7f3", background: selected.has(c.id) ? "#f0fdf4" : i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                  <td style={{ padding: "8px 14px", textAlign: "center" }}>
                    <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleSelect(c.id)} />
                  </td>
                  <td style={{ padding: "8px 12px", fontWeight: 600, color: "#0f3622", whiteSpace: "nowrap" }}>
                    {c.full_name}
                    <div style={{ fontSize: 10, color: "#94b5a0", fontWeight: 400 }}>{c.role.replace(/_/g, " ")}</div>
                  </td>
                  <td style={{ padding: "8px 12px", color: "#4a7a5c", whiteSpace: "nowrap" }}>
                    {c.email
                      ? <a href={`mailto:${c.email}`} style={{ color: "#1a5c38", textDecoration: "none" }}>{c.email}</a>
                      : <span style={{ color: "#c0d8c8" }}>—</span>
                    }
                  </td>
                  <td style={{ padding: "8px 12px", color: "#4a7a5c" }}>
                    {c.designation ?? <span style={{ color: "#c0d8c8" }}>—</span>}
                  </td>
                  <td style={{ padding: "8px 12px", color: "#4a7a5c", whiteSpace: "nowrap" }}>{c.college}</td>
                  <td style={{ padding: "8px 12px" }}>{badge(c.status, STATUS_COLORS)}</td>
                  <td style={{ padding: "8px 12px" }}>
                    {badge(c.research_status ?? "PENDING", {
                      DONE:     { bg: "#d1fae5", color: "#065f46" },
                      IN_PROGRESS: { bg: "#dbeafe", color: "#1e40af" },
                      PENDING:  { bg: "#f3f4f6", color: "#6b7280" },
                      FAILED:   { bg: "#fee2e2", color: "#991b1b" },
                      WEBSITE_UNAVAILABLE: { bg: "#fef3c7", color: "#92400e" },
                    })}
                  </td>
                  <td style={{ padding: "8px 12px" }}>
                    {c.draft_status
                      ? badge(c.draft_status, DRAFT_COLORS)
                      : <span style={{ color: "#c0d8c8", fontSize: 11 }}>None</span>
                    }
                  </td>
                  <td style={{ padding: "8px 12px", color: "#6b9e7e", whiteSpace: "nowrap", fontSize: 11 }}>
                    {formatDate(c.last_contact_at)}
                  </td>
                  <td style={{ padding: "8px 12px", color: "#6b9e7e", whiteSpace: "nowrap", fontSize: 11 }}>
                    {formatDate(c.created_at)}
                  </td>
                  <td style={{ padding: "8px 12px", whiteSpace: "nowrap" }}>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button onClick={() => setViewContact(c)}
                        title="View"
                        style={{ background: "#f0f7f3", color: "#1a5c38", border: "1px solid #cce0d4", borderRadius: 5, padding: "4px 8px", fontSize: 11, cursor: "pointer" }}>👁</button>
                      <button onClick={() => setEditContact(c)}
                        title="Edit"
                        style={{ background: "#f0f7f3", color: "#1a5c38", border: "1px solid #cce0d4", borderRadius: 5, padding: "4px 8px", fontSize: 11, cursor: "pointer" }}>✏</button>
                      <button onClick={() => removeFromList(c.id)}
                        title="Remove from this list"
                        style={{ background: "#fef3c7", color: "#92400e", border: "1px solid #fde68a", borderRadius: 5, padding: "4px 8px", fontSize: 11, cursor: "pointer" }}>📤</button>
                      <button onClick={() => setDeleteContact(c)}
                        title="Delete contact"
                        style={{ background: "#fee2e2", color: "#dc2626", border: "1px solid #fecaca", borderRadius: 5, padding: "4px 8px", fontSize: 11, cursor: "pointer" }}>🗑</button>
                    </div>
                  </td>
                </tr>
              ))}
              {list.contacts.length === 0 && (
                <tr>
                  <td colSpan={11} style={{ padding: "36px 16px", textAlign: "center", color: "#94b5a0" }}>
                    <div style={{ fontSize: 28, marginBottom: 8 }}>👥</div>
                    No contacts in this list yet.
                    <br />
                    <button onClick={() => setShowAddExisting(true)} style={{ marginTop: 10, background: "linear-gradient(135deg,#0f3622,#1a5c38)", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                      ➕ Add Contacts
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
