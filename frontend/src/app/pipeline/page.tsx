"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────
type TabId = "import" | "manual";

interface CollegeRow {
  college_name: string;
  city: string;
  state: string;
  website: string;
  tpo_name: string;
  tpo_email: string;
  director_name: string;
  director_email: string;
}

const EMPTY_ROW = (): CollegeRow => ({
  college_name: "", city: "", state: "", website: "",
  tpo_name: "", tpo_email: "", director_name: "", director_email: "",
});

interface ImportResult {
  ok: boolean;
  colleges_processed: number;
  contacts_added: number;
  contacts_skipped: number;
  message: string;
  list_id?: number;
  list_name?: string;
  contacts_associated?: number;
}

type ListOption = "new" | "existing";

interface ListSummary {
  id: number;
  name: string;
  contact_count: number;
}

type SenderProfileOption = {
  id: number;
  name: string;
  display_name: string;
  email_address: string;
  enabled: boolean;
};

type DefaultSenderInfo = {
  display_name: string;
  email_address: string;
  configured: boolean;
  label: string;
};

type TemplateOption = {
  id: number;
  name: string;
  description: string | null;
};

// ─── Sample CSV content ───────────────────────────────────────────────────────
const SAMPLE_CSV = `college_name,city,state,website,tpo_name,tpo_email,director_name,director_email
IIT Bombay,Mumbai,Maharashtra,https://www.iitb.ac.in,Dr. Rajesh Kumar,tpo@iitb.ac.in,Prof. Subhasis Chaudhuri,director@iitb.ac.in
VIT Vellore,Vellore,Tamil Nadu,https://vit.ac.in,Mr. Arun Sharma,placements@vit.ac.in,Dr. G. Viswanathan,vc@vit.ac.in
Pune University,Pune,Maharashtra,https://unipune.ac.in,Ms. Priya Nair,tpo@unipune.ac.in,Dr. Nitin Karmalkar,vc@unipune.ac.in
NIT Trichy,Tiruchirappalli,Tamil Nadu,https://www.nitt.edu,Dr. Senthil Kumar,tpo@nitt.edu,Prof. Mini Shaji Thomas,director@nitt.edu
BITS Pilani,Pilani,Rajasthan,https://www.bits-pilani.ac.in,Mr. Vivek Singh,careers@bits-pilani.ac.in,Prof. Souvik Bhattacharyya,vchancellor@bits-pilani.ac.in
`;

// ─── Pipeline step explanations ───────────────────────────────────────────────
const PIPELINE_STEPS = [
  {
    number: 1, icon: "📥", color: "#3b82f6", title: "Import Contacts",
    what: "You upload a list of colleges with their TPO (Training & Placement Officer) and Director names and emails.",
    how: "The system creates college records and contact records in the database. Duplicates are automatically skipped.",
    output: "College and contact records saved. Each contact starts with status VERIFIED (confidence 95%).",
    time: "Instant",
  },
  {
    number: 2, icon: "✍️", color: "#f59e0b", title: "Generate Drafts",
    what: "You select a list and optional email template, then the AI writes a personalized outreach email for each verified contact in that list.",
    how: "Groq LLM generates a warm, professional email body + 5 subject line options. Templates add extra context/formatting without changing the core prompt. Automatically checks for spam words, proper length, and unsubscribe footer.",
    output: "Email drafts appear in the Approval Queue with lint pass/fail status.",
    time: "1-3 seconds per contact",
  },
  {
    number: 3, icon: "✅", color: "#10b981", title: "Review & Approve",
    what: "You review every email before it is sent. You can edit the subject, edit the body, approve, or reject.",
    how: "Go to the Approval Queue page. Only APPROVED drafts will be sent — nothing goes out without your explicit approval.",
    output: "Approved drafts move to QUEUED status, ready to send.",
    time: "30 seconds per draft",
  },
  {
    number: 4, icon: "🚀", color: "#ef4444", title: "Send Emails",
    what: "You select a list and sender profile, then send approved emails. SMTP credentials stay in .env — only From Name and From Email change.",
    how: "Rate-limited by daily/hourly caps. Suppression list checked — unsubscribed/bounced contacts are never emailed. Each email has a signed unsubscribe link.",
    output: "Emails delivered. Opens, clicks, bounces, and replies tracked on the Dashboard.",
    time: "~2 seconds per email",
  },
  {
    number: 5, icon: "🔄", color: "#8b5cf6", title: "Auto Follow-ups",
    what: "If a contact doesn't reply, the system automatically drafts a follow-up email for your approval.",
    how: "Day 3 → Follow-up 1. Day 7 → Follow-up 2. Day 14 → Final follow-up. Any reply or unsubscribe stops the sequence. Hard cap: 4 total emails per contact (enforced in the database).",
    output: "Follow-up drafts appear in the Approval Queue. Same approve-before-send flow.",
    time: "Automatic (runs daily at 9am)",
  },
];

// ─── Main component ───────────────────────────────────────────────────────────
export default function PipelinePage() {
  const [tab, setTab] = useState<TabId>("import");
  // CSV tab state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<string[][]>([]);
  const [csvText, setCsvText] = useState("");
  const [listOption, setListOption] = useState<ListOption>("new");
  const [existingLists, setExistingLists] = useState<ListSummary[]>([]);
  const [selectedListId, setSelectedListId] = useState<number | null>(null);
  const [newListName, setNewListName] = useState("");
  const [newListDescription, setNewListDescription] = useState("");
  // Manual tab state
  const [rows, setRows] = useState<CollegeRow[]>([EMPTY_ROW()]);
  // Shared state
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  // Draft generation state
  const [drafting, setDrafting] = useState(false);
  const [draftListId, setDraftListId] = useState<number | null>(null);
  const [draftTemplateId, setDraftTemplateId] = useState<string>("none");
  const [emailTemplates, setEmailTemplates] = useState<TemplateOption[]>([]);
  const [draftResult, setDraftResult] = useState<string | null>(null);
  // Send state
  const [sendListId, setSendListId] = useState<number | null>(null);
  const [sendLimit, setSendLimit] = useState("");
  const [sendProfileId, setSendProfileId] = useState<string>("default");
  const [senderProfiles, setSenderProfiles] = useState<SenderProfileOption[]>([]);
  const [defaultSender, setDefaultSender] = useState<DefaultSenderInfo | null>(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState(true);
  // SMTP status
  const [smtpStatus, setSmtpStatus] = useState<{
    configured: boolean; smtp_host: string; sender_email: string; missing: string[];
    default_sender?: DefaultSenderInfo;
  } | null>(null);

  // Load SMTP status on mount
  useEffect(() => {
    api<{
      configured: boolean; smtp_host: string; sender_email: string; missing: string[];
      default_sender?: DefaultSenderInfo;
    }>("/api/pipeline/smtp-status")
      .then(setSmtpStatus)
      .catch(() => null);
    api<{ default: DefaultSenderInfo; items: SenderProfileOption[] }>("/api/sender-profiles")
      .then((d) => {
        setDefaultSender(d.default);
        setSenderProfiles(d.items.filter((p) => p.enabled));
      })
      .catch(() => null);
    api<{ total: number; items: TemplateOption[] }>("/api/templates")
      .then((d) => setEmailTemplates(d.items))
      .catch(() => null);
  }, []);

  // Load existing lists for CSV import and draft generation
  useEffect(() => {
    api<{ total: number; items: ListSummary[] }>("/api/lists")
      .then((d) => {
        setExistingLists(d.items);
        if (d.items.length > 0) {
          setSelectedListId((prev) => prev ?? d.items[0].id);
          setDraftListId((prev) => prev ?? d.items[0].id);
          setSendListId((prev) => prev ?? d.items[0].id);
        }
      })
      .catch(() => null);
  }, []);

  // ── CSV helpers ─────────────────────────────────────────────────────────────
  function handleCsvFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setCsvFile(file);
    setImportResult(null);
    setImportError(null);
    if (!file) { setCsvPreview([]); setCsvText(""); return; }
    file.text().then((text) => {
      setCsvText(text);
      const lines = text.trim().split("\n").slice(0, 6).map((l) => l.split(","));
      setCsvPreview(lines);
    });
  }

  function downloadSampleCsv() {
    const blob = new Blob([SAMPLE_CSV], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "aivalytics_outreach_sample.csv";
    a.click();
  }

  // ── Manual helpers ───────────────────────────────────────────────────────────
  function updateRow(i: number, field: keyof CollegeRow, val: string) {
    setRows((prev) => prev.map((r, idx) => idx === i ? { ...r, [field]: val } : r));
  }
  function addRow() { setRows((p) => [...p, EMPTY_ROW()]); }
  function removeRow(i: number) { setRows((p) => p.filter((_, idx) => idx !== i)); }

  // ── Import ───────────────────────────────────────────────────────────────────
  async function doImport() {
    setImporting(true);
    setImportResult(null);
    setImportError(null);
    try {
      let result: ImportResult;
      if (tab === "import") {
        if (!csvText) throw new Error("Please select a CSV file first.");
        const payload: Record<string, unknown> = { csv_text: csvText };
        if (listOption === "new") {
          if (!newListName.trim()) throw new Error("Enter a name for the new list.");
          payload.new_list_name = newListName.trim();
          if (newListDescription.trim()) {
            payload.new_list_description = newListDescription.trim();
          }
        } else {
          if (!selectedListId) throw new Error("Select an existing list.");
          payload.list_id = selectedListId;
        }
        result = await api<ImportResult>("/api/contacts/import-csv", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } else {
        const validRows = rows.filter((r) => r.college_name.trim());
        if (!validRows.length) throw new Error("Add at least one college.");
        result = await api<ImportResult>("/api/contacts/import", {
          method: "POST",
          body: JSON.stringify({ rows: validRows }),
        });
      }
      setImportResult(result);
    } catch (e) {
      setImportError(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  }

  // ── Generate drafts ──────────────────────────────────────────────────────────
  async function generateDrafts() {
    if (!draftListId) {
      setDraftResult("⚠ Select a list first, or create one on the Lists page.");
      return;
    }
    setDrafting(true);
    setDraftResult(null);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (draftTemplateId !== "none") params.set("template_id", draftTemplateId);
      const res = await api<{
        drafted: number; lint_passed: number; lint_failed: number;
        list_name: string; eligible_contacts: number;
        template_name?: string;
      }>(`/api/lists/${draftListId}/draft-emails?${params.toString()}`, { method: "POST" });
      const listLabel = res.list_name ? ` for "${res.list_name}"` : "";
      const templateLabel = res.template_name ? ` using template "${res.template_name}"` : "";
      setDraftResult(
        `✓ Generated ${res.drafted} draft${res.drafted === 1 ? "" : "s"}${listLabel}${templateLabel} — ` +
        `${res.lint_passed} passed lint, ${res.lint_failed} need editing.`
      );
    } catch (e) {
      setDraftResult(`⚠ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setDrafting(false);
    }
  }

  // ── Send approved drafts ─────────────────────────────────────────────────────
  async function sendEmails() {
    if (!sendListId) {
      setSendResult("⚠ Select a list first.");
      return;
    }
    setSending(true);
    setSendResult(null);
    try {
      const params = new URLSearchParams();
      if (dryRun) params.set("dry_run", "true");
      if (sendLimit.trim()) params.set("limit", String(Number(sendLimit)));
      if (sendProfileId !== "default") params.set("sender_profile_id", sendProfileId);
      const qs = params.toString() ? `?${params.toString()}` : "";
      if (dryRun) {
        const res = await api<{
          dry_run: boolean; ready_to_send: number; list_name: string; quota_remaining: number;
        }>(`/api/lists/${sendListId}/send${qs}`, { method: "POST" });
        setSendResult(
          `DRY RUN: ${res.ready_to_send} approved draft(s) in "${res.list_name}" ready to send. ` +
          `Quota remaining: ${res.quota_remaining}. Toggle off dry-run to actually send.`
        );
      } else {
        const liveParams = new URLSearchParams();
        if (sendLimit.trim()) liveParams.set("limit", String(Number(sendLimit)));
        if (sendProfileId !== "default") liveParams.set("sender_profile_id", sendProfileId);
        const liveQs = liveParams.toString() ? `?${liveParams.toString()}` : "";
        const res = await api<{
          sent: number; suppressed: number; failed: number; quota_remaining: number;
          list_name: string; campaign_id?: number; campaign_name?: string;
          from_name?: string; from_email?: string; sender_label?: string;
        }>(`/api/lists/${sendListId}/send${liveQs}`, { method: "POST" });
        const parts = [`✓ Sent ${res.sent} email(s) from "${res.list_name}". Quota remaining: ${res.quota_remaining}`];
        if (res.from_name && res.from_email) {
          parts.push(`From: ${res.from_name} <${res.from_email}>`);
        }
        if (res.suppressed > 0) parts.push(`${res.suppressed} suppressed (unsubscribed/bounced)`);
        if (res.failed > 0) parts.push(`⚠ ${res.failed} failed — check server logs`);
        if (res.campaign_name) parts.push(`Campaign: ${res.campaign_name}`);
        setSendResult(parts.join(" · "));
      }
    } catch (e) {
      setSendResult(`⚠ Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSending(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>

      {/* ── Page header ── */}
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: "#0f3622", margin: 0 }}>
          Pipeline — How it works
        </h1>
        <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 4 }}>
          Upload your college list with TPO & Director details — we'll handle the rest.
        </p>
      </div>

      {/* ── Pipeline flow overview ── */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: "22px 26px" }}>
        <h2 style={{ fontSize: 13, fontWeight: 700, color: "#0f3622", margin: "0 0 18px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          What happens step by step
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.number} style={{ display: "flex", gap: 0 }}>
              {/* Left column — number + connector */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 48, flexShrink: 0 }}>
                <div style={{
                  width: 38, height: 38, borderRadius: "50%", background: step.color,
                  color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: 800, fontSize: 15, flexShrink: 0, zIndex: 1
                }}>{step.number}</div>
                {i < PIPELINE_STEPS.length - 1 && (
                  <div style={{ width: 2, flex: 1, background: "#e2ede8", minHeight: 20 }} />
                )}
              </div>
              {/* Right column — content */}
              <div style={{ paddingLeft: 16, paddingBottom: i < PIPELINE_STEPS.length - 1 ? 24 : 0, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                  <span style={{ fontSize: 18 }}>{step.icon}</span>
                  <span style={{ fontWeight: 700, color: "#0f3622", fontSize: 15 }}>{step.title}</span>
                  <span style={{ fontSize: 11, color: "#94b5a0", background: "#f0f7f3", padding: "2px 8px", borderRadius: 20 }}>
                    ⏱ {step.time}
                  </span>
                </div>
                <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                  {[
                    { label: "📌 What", text: step.what },
                    { label: "⚙ How", text: step.how },
                    { label: "📤 Output", text: step.output },
                  ].map(({ label, text }) => (
                    <div key={label} style={{ background: "#f8faf9", borderRadius: 8, padding: "10px 12px", border: "1px solid #e8f0ec" }}>
                      <p style={{ fontSize: 10, fontWeight: 700, color: "#3d6b4f", margin: "0 0 4px", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
                      <p style={{ fontSize: 12, color: "#4a7a5c", margin: 0, lineHeight: 1.6 }}>{text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Step 1: Import section ── */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden" }}>
        {/* Header */}
        <div style={{ background: "linear-gradient(135deg,#0f3622,#1a5c38)", padding: "18px 26px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 22 }}>📥</span>
            <div>
              <h2 style={{ color: "#fff", fontSize: 17, fontWeight: 800, margin: 0 }}>
                Step 1 — Import Your College List
              </h2>
              <p style={{ color: "#a8dfbe", fontSize: 12, margin: "2px 0 0" }}>
                Upload a CSV or enter colleges manually — with TPO & Director details
              </p>
            </div>
          </div>
        </div>

        <div style={{ padding: "22px 26px", display: "flex", flexDirection: "column", gap: 18 }}>

          {/* Tab switcher */}
          <div style={{ display: "flex", gap: 0, background: "#f0f7f3", borderRadius: 10, padding: 4, width: "fit-content" }}>
            {([["import", "📄 Upload CSV"], ["manual", "✏️ Enter Manually"]] as [TabId, string][]).map(([id, label]) => (
              <button key={id} onClick={() => { setTab(id); setImportResult(null); setImportError(null); }}
                style={{
                  background: tab === id ? "#0f3622" : "transparent",
                  color: tab === id ? "#fff" : "#4a7a5c",
                  border: "none", borderRadius: 8, padding: "8px 20px",
                  fontSize: 13, fontWeight: 700, cursor: "pointer", transition: "all 0.2s"
                }}>{label}</button>
            ))}
          </div>

          {/* CSV tab */}
          {tab === "import" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Sample download */}
              <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "14px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <p style={{ fontWeight: 700, color: "#15803d", fontSize: 13, margin: 0 }}>📋 Download sample CSV</p>
                  <p style={{ color: "#4ade80", fontSize: 12, margin: "2px 0 0" }}>
                    Columns: college_name, city, state, website, tpo_name, tpo_email, director_name, director_email
                  </p>
                </div>
                <button onClick={downloadSampleCsv} style={{
                  background: "#15803d", color: "#fff", border: "none", borderRadius: 8,
                  padding: "8px 18px", fontSize: 13, fontWeight: 700, cursor: "pointer",
                  whiteSpace: "nowrap"
                }}>⬇ Download Sample</button>
              </div>

              {/* Upload box */}
              <label style={{
                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                border: "2px dashed #6dbd94", borderRadius: 12, padding: "28px 20px",
                cursor: "pointer", background: csvFile ? "#f0fdf4" : "#fafcfb",
                transition: "all 0.2s", gap: 8
              }}>
                <span style={{ fontSize: 36 }}>{csvFile ? "✅" : "📂"}</span>
                <span style={{ fontWeight: 700, color: "#1a5c38", fontSize: 14 }}>
                  {csvFile ? csvFile.name : "Click to choose your CSV file"}
                </span>
                <span style={{ fontSize: 12, color: "#6b9e7e" }}>
                  {csvFile ? `${(csvFile.size / 1024).toFixed(1)} KB` : "or drag & drop here"}
                </span>
                <input type="file" accept=".csv,.txt" onChange={handleCsvFile} style={{ display: "none" }} />
              </label>

              {/* Preview */}
              {csvPreview.length > 0 && (
                <div style={{ borderRadius: 10, border: "1px solid #dceae2", overflow: "hidden" }}>
                  <p style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", background: "#f0f7f3", padding: "8px 14px", margin: 0, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    Preview (first 5 rows)
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                      <tbody>
                        {csvPreview.map((row, ri) => (
                          <tr key={ri} style={{ background: ri === 0 ? "#f0f7f3" : ri % 2 === 0 ? "#fff" : "#fafcfb" }}>
                            {row.map((cell, ci) => (
                              <td key={ci} style={{ padding: "6px 12px", borderBottom: "1px solid #f0f7f3", fontWeight: ri === 0 ? 700 : 400, color: ri === 0 ? "#0f3622" : "#4a7a5c", whiteSpace: "nowrap" }}>
                                {cell.replace(/"/g, "")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* List assignment */}
              {csvText && (
                <div style={{ background: "#f8faf9", border: "1px solid #dceae2", borderRadius: 12, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
                  <div>
                    <p style={{ fontWeight: 700, color: "#0f3622", fontSize: 14, margin: "0 0 4px" }}>Assign imported contacts to a list</p>
                    <p style={{ fontSize: 12, color: "#6b9e7e", margin: 0 }}>
                      Duplicate contacts are reused — only the list association is added.
                    </p>
                  </div>

                  <div style={{ display: "flex", gap: 0, background: "#f0f7f3", borderRadius: 10, padding: 4, width: "fit-content" }}>
                    {([["new", "➕ Create New List"], ["existing", "📋 Add to Existing List"]] as [ListOption, string][]).map(([id, label]) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setListOption(id)}
                        style={{
                          background: listOption === id ? "#0f3622" : "transparent",
                          color: listOption === id ? "#fff" : "#4a7a5c",
                          border: "none", borderRadius: 8, padding: "8px 16px",
                          fontSize: 12, fontWeight: 700, cursor: "pointer",
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>

                  {listOption === "new" ? (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          New list name *
                        </label>
                        <input
                          value={newListName}
                          onChange={(e) => setNewListName(e.target.value)}
                          placeholder="e.g. Karnataka TPOs — Aug 2026"
                          style={{
                            border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
                            fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
                          }}
                        />
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          Description (optional)
                        </label>
                        <input
                          value={newListDescription}
                          onChange={(e) => setNewListDescription(e.target.value)}
                          placeholder="What is this list for?"
                          style={{
                            border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
                            fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
                          }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 5, maxWidth: 420 }}>
                      <label style={{ fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        Select list *
                      </label>
                      {existingLists.length > 0 ? (
                        <select
                          value={selectedListId ?? ""}
                          onChange={(e) => setSelectedListId(Number(e.target.value))}
                          style={{
                            border: "1.5px solid #cce0d4", borderRadius: 8, padding: "8px 12px",
                            fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
                          }}
                        >
                          {existingLists.map((lst) => (
                            <option key={lst.id} value={lst.id}>
                              {lst.name} ({lst.contact_count} contact{lst.contact_count === 1 ? "" : "s"})
                            </option>
                          ))}
                        </select>
                      ) : (
                        <p style={{ fontSize: 12, color: "#92400e", margin: 0, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "10px 12px" }}>
                          No lists yet — switch to &quot;Create New List&quot; or create one on the Lists page first.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Manual tab */}
          {tab === "manual" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <p style={{ fontSize: 13, color: "#6b9e7e", margin: 0 }}>
                Fill in college and contact details. Add as many rows as you need.
              </p>
              {/* Column headers */}
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr 2fr 2fr 2fr 2fr 40px", gap: 6 }}>
                {["College Name*", "City", "State", "Website", "TPO Name", "TPO Email", "Director Name", "Director Email", ""].map((h) => (
                  <div key={h} style={{ fontSize: 10, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", padding: "0 4px" }}>{h}</div>
                ))}
              </div>
              {/* Rows */}
              {rows.map((row, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 2fr 2fr 2fr 2fr 2fr 40px", gap: 6, alignItems: "center" }}>
                  {([
                    ["college_name", "e.g. IIT Bombay", true],
                    ["city", "Mumbai", false],
                    ["state", "Maharashtra", false],
                    ["website", "https://...", false],
                    ["tpo_name", "Dr. Sharma", false],
                    ["tpo_email", "tpo@college.ac.in", false],
                    ["director_name", "Prof. Gupta", false],
                    ["director_email", "dir@college.ac.in", false],
                  ] as [keyof CollegeRow, string, boolean][]).map(([field, ph, required]) => (
                    <input key={field}
                      value={row[field]}
                      onChange={(e) => updateRow(i, field, e.target.value)}
                      placeholder={ph}
                      required={required}
                      style={{
                        border: "1.5px solid #cce0d4", borderRadius: 6, padding: "6px 8px",
                        fontSize: 12, outline: "none", width: "100%", boxSizing: "border-box",
                        background: required && !row[field] ? "#fff8f8" : "#fff"
                      }}
                    />
                  ))}
                  <button onClick={() => removeRow(i)} disabled={rows.length === 1}
                    style={{ background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: 6, width: 32, height: 32, cursor: rows.length === 1 ? "not-allowed" : "pointer", fontSize: 16, opacity: rows.length === 1 ? 0.4 : 1 }}>
                    ×
                  </button>
                </div>
              ))}
              <button onClick={addRow} style={{
                background: "#e8f5ee", color: "#1a5c38", border: "1.5px dashed #6dbd94",
                borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600,
                cursor: "pointer", width: "fit-content"
              }}>
                + Add Another College
              </button>
            </div>
          )}

          {/* Result / Error */}
          {importResult && (
            <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "14px 18px" }}>
              <p style={{ fontWeight: 700, color: "#15803d", fontSize: 14, margin: "0 0 4px" }}>✓ Import Successful</p>
              <p style={{ fontSize: 13, color: "#166534", margin: 0 }}>{importResult.message}</p>
              <p style={{ fontSize: 12, color: "#4ade80", margin: "4px 0 0" }}>
                Colleges processed: {importResult.colleges_processed} · Contacts added: {importResult.contacts_added} · Skipped (duplicates): {importResult.contacts_skipped}
                {importResult.list_name && (
                  <> · Assigned to list: <strong>{importResult.list_name}</strong> ({importResult.contacts_associated ?? 0} contact{(importResult.contacts_associated ?? 0) === 1 ? "" : "s"})</>
                )}
              </p>
              {importResult.list_id && (
                <a href="/lists" style={{ display: "inline-block", marginTop: 8, background: "#15803d", color: "#fff", borderRadius: 8, padding: "6px 16px", fontSize: 12, fontWeight: 700, textDecoration: "none" }}>
                  → View Lists
                </a>
              )}
            </div>
          )}
          {importError && (
            <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "14px 18px" }}>
              <p style={{ fontWeight: 700, color: "#dc2626", fontSize: 13, margin: 0 }}>⚠ {importError}</p>
            </div>
          )}

          {/* Import button */}
          <button onClick={doImport} disabled={importing}
            style={{
              background: importing ? "#6b9e7e" : "linear-gradient(135deg,#0f3622,#1a5c38)",
              color: "#fff", border: "none", borderRadius: 10, padding: "12px 28px",
              fontSize: 14, fontWeight: 800, cursor: importing ? "not-allowed" : "pointer",
              boxShadow: "0 2px 12px rgba(15,54,34,0.25)", width: "fit-content",
              letterSpacing: "0.04em"
            }}>
            {importing ? "⟳ Importing…" : "📥 Import to Database"}
          </button>
        </div>
      </div>

      {/* ── Step 2: Generate Drafts ── */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden" }}>
        <div style={{ background: "linear-gradient(135deg,#92400e,#d97706)", padding: "18px 26px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 22 }}>✍️</span>
            <div>
              <h2 style={{ color: "#fff", fontSize: 17, fontWeight: 800, margin: 0 }}>Step 2 — Generate Personalized Emails</h2>
              <p style={{ color: "#fde68a", fontSize: 12, margin: "2px 0 0" }}>Select a list and optional template — AI writes a custom email for each verified contact</p>
            </div>
          </div>
        </div>
        <div style={{ padding: "22px 26px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              { icon: "🎯", title: "Personalized", desc: "Each email mentions the college name, city, and the contact's specific role (TPO/Director)" },
              { icon: "✅", title: "Lint-checked", desc: "Auto-checks for spam words, correct length, unsubscribe footer, and no placeholder text" },
              { icon: "📝", title: "5 Subject Options", desc: "The AI generates 5 subject line variations — you pick the best one in the Approval Queue" },
              { icon: "🔒", title: "Grounded Only", desc: "The email only uses facts you provided — no hallucinated claims about the college" },
            ].map(({ icon, title, desc }) => (
              <div key={title} style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: "12px 16px" }}>
                <p style={{ fontWeight: 700, color: "#92400e", fontSize: 13, margin: "0 0 4px" }}>{icon} {title}</p>
                <p style={{ fontSize: 12, color: "#78350f", margin: 0, lineHeight: 1.6 }}>{desc}</p>
              </div>
            ))}
          </div>

          {draftResult && (
            <div style={{
              background: draftResult.startsWith("✓") ? "#f0fdf4" : draftResult.startsWith("⚠") ? "#fffbeb" : "#f0fdf4",
              border: `1px solid ${draftResult.startsWith("✓") ? "#bbf7d0" : draftResult.startsWith("⚠") ? "#fde68a" : "#bbf7d0"}`,
              borderRadius: 10, padding: "12px 16px",
            }}>
              <p style={{
                fontSize: 13,
                color: draftResult.startsWith("✓") ? "#15803d" : draftResult.startsWith("⚠") ? "#92400e" : "#15803d",
                margin: 0, fontFamily: "monospace",
              }}>{draftResult}</p>
              {draftResult.startsWith("✓") && (
                <a href="/drafts" style={{ display: "inline-block", marginTop: 8, background: "#15803d", color: "#fff", borderRadius: 8, padding: "6px 16px", fontSize: 12, fontWeight: 700, textDecoration: "none" }}>
                  → Open Approval Queue
                </a>
              )}
            </div>
          )}

          <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8, maxWidth: 420 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#92400e", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Select list *
            </label>
            {existingLists.length > 0 ? (
              <select
                value={draftListId ?? ""}
                onChange={(e) => setDraftListId(Number(e.target.value))}
                style={{
                  border: "1.5px solid #fde68a", borderRadius: 8, padding: "8px 12px",
                  fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
                }}
              >
                {existingLists.map((lst) => (
                  <option key={lst.id} value={lst.id}>
                    {lst.name} ({lst.contact_count} contact{lst.contact_count === 1 ? "" : "s"})
                  </option>
                ))}
              </select>
            ) : (
              <p style={{ fontSize: 12, color: "#92400e", margin: 0 }}>
                No lists yet — import contacts into a list in Step 1, or create one on the{" "}
                <a href="/lists" style={{ color: "#b45309", fontWeight: 700 }}>Lists</a> page.
              </p>
            )}
            <p style={{ fontSize: 11, color: "#78350f", margin: 0, lineHeight: 1.5 }}>
              Only VERIFIED contacts in this list without an existing draft will be processed.
            </p>
          </div>

          <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8, maxWidth: 420 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#92400e", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Email template (optional)
            </label>
            <select
              value={draftTemplateId}
              onChange={(e) => setDraftTemplateId(e.target.value)}
              style={{
                border: "1.5px solid #fde68a", borderRadius: 8, padding: "8px 12px",
                fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
              }}
            >
              <option value="none">No template — default generation</option>
              {emailTemplates.map((t) => (
                <option key={t.id} value={String(t.id)}>
                  {t.name}{t.description ? ` — ${t.description}` : ""}
                </option>
              ))}
            </select>
            <p style={{ fontSize: 11, color: "#78350f", margin: 0, lineHeight: 1.5 }}>
              Templates add context/formatting to the prompt. Manage on the{" "}
              <a href="/templates" style={{ color: "#b45309", fontWeight: 700 }}>Templates</a> page.
            </p>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button onClick={generateDrafts} disabled={drafting || !draftListId}
              style={{
                background: drafting ? "#e5e7eb" : "linear-gradient(135deg,#92400e,#d97706)",
                color: drafting ? "#9ca3af" : "#fff",
                border: "none", borderRadius: 10, padding: "12px 28px",
                fontSize: 14, fontWeight: 800, cursor: drafting ? "not-allowed" : "pointer",
                boxShadow: drafting ? "none" : "0 2px 12px rgba(217,119,6,0.3)"
              }}>
              {drafting ? "⟳ Generating…" : "✍️ Generate Email Drafts"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Steps 3–5: Quick links ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        {/* Step 3 — Approve */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: "20px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#10b981", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 14 }}>3</div>
            <span style={{ fontSize: 16 }}>✅</span>
            <span style={{ fontWeight: 700, color: "#0f3622", fontSize: 14 }}>Review & Approve</span>
          </div>
          <p style={{ fontSize: 12, color: "#6b9e7e", margin: 0, lineHeight: 1.6 }}>
            Read every AI-written email, edit subject or body if needed, then click Approve. Only approved emails will be sent — nothing goes out without your sign-off.
          </p>
          <a href="/drafts" style={{ background: "#10b981", color: "#fff", borderRadius: 8, padding: "8px 14px", fontSize: 12, fontWeight: 700, textDecoration: "none", textAlign: "center" }}>
            → Open Approval Queue
          </a>
        </div>

        {/* Step 4 — Send */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: "20px", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#ef4444", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 14 }}>4</div>
            <span style={{ fontSize: 16 }}>🚀</span>
            <span style={{ fontWeight: 700, color: "#0f3622", fontSize: 14 }}>Send Emails</span>
          </div>
          <p style={{ fontSize: 12, color: "#6b9e7e", margin: 0, lineHeight: 1.6 }}>
            Select a list, sender profile, and send approved drafts. SMTP credentials stay in .env — only From Name and From Email change.
          </p>
          {/* SMTP config status */}
          {smtpStatus && (
            <div style={{
              background: smtpStatus.configured ? "#f0fdf4" : "#fff5f5",
              border: `1px solid ${smtpStatus.configured ? "#bbf7d0" : "#fecaca"}`,
              borderRadius: 8, padding: "8px 12px", fontSize: 11
            }}>
              {smtpStatus.configured ? (
                <span style={{ color: "#15803d", fontWeight: 600 }}>
                  ✓ SMTP ready — {smtpStatus.smtp_host} · from {smtpStatus.sender_email}
                </span>
              ) : (
                <span style={{ color: "#dc2626", fontWeight: 600 }}>
                  ⚠ SMTP not fully configured — missing: {smtpStatus.missing.join(", ")}
                </span>
              )}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#991b1b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Select list *
            </label>
            {existingLists.length > 0 ? (
              <select
                value={sendListId ?? ""}
                onChange={(e) => setSendListId(Number(e.target.value))}
                style={{
                  border: "1.5px solid #fecaca", borderRadius: 8, padding: "8px 12px",
                  fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
                }}
              >
                {existingLists.map((lst) => (
                  <option key={lst.id} value={lst.id}>
                    {lst.name} ({lst.contact_count} contact{lst.contact_count === 1 ? "" : "s"})
                  </option>
                ))}
              </select>
            ) : (
              <p style={{ fontSize: 12, color: "#92400e", margin: 0 }}>
                No lists yet — create one on the{" "}
                <a href="/lists" style={{ color: "#b45309", fontWeight: 700 }}>Lists</a> page.
              </p>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#991b1b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Sender profile *
            </label>
            <select
              value={sendProfileId}
              onChange={(e) => setSendProfileId(e.target.value)}
              style={{
                border: "1.5px solid #fecaca", borderRadius: 8, padding: "8px 12px",
                fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
              }}
            >
              <option value="default">
                {defaultSender
                  ? `${defaultSender.label}: ${defaultSender.display_name} <${defaultSender.email_address || "not configured"}>`
                  : "Default (.env)"}
              </option>
              {senderProfiles.map((p) => (
                <option key={p.id} value={String(p.id)}>
                  {p.name}: {p.display_name} &lt;{p.email_address}&gt;
                </option>
              ))}
            </select>
            <p style={{ fontSize: 11, color: "#78350f", margin: 0, lineHeight: 1.5 }}>
              Manage profiles on the{" "}
              <a href="/senders" style={{ color: "#b45309", fontWeight: 700 }}>Senders</a> page.
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, maxWidth: 160 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: "#991b1b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Max emails (optional)
            </label>
            <input
              type="number"
              min={1}
              value={sendLimit}
              onChange={(e) => setSendLimit(e.target.value)}
              placeholder="Default: 25"
              style={{
                border: "1.5px solid #fecaca", borderRadius: 8, padding: "8px 12px",
                fontSize: 13, color: "#0f1a14", background: "#fff", outline: "none",
              }}
            />
          </div>
          {/* Dry run toggle */}
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <div onClick={() => setDryRun(!dryRun)} style={{
              width: 40, height: 22, borderRadius: 11, background: dryRun ? "#fde68a" : "#ef4444",
              position: "relative", transition: "background 0.2s", cursor: "pointer", flexShrink: 0
            }}>
              <div style={{
                width: 18, height: 18, borderRadius: "50%", background: "#fff",
                position: "absolute", top: 2, left: dryRun ? 2 : 20, transition: "left 0.2s"
              }} />
            </div>
            <span style={{ fontSize: 12, fontWeight: 600, color: dryRun ? "#92400e" : "#dc2626" }}>
              {dryRun ? "🔒 Dry Run (safe preview)" : "🔴 LIVE — will actually send"}
            </span>
          </label>
          {sendResult && (
            <div style={{
              background: sendResult.startsWith("✓") ? "#f0fdf4" : sendResult.startsWith("⚠") ? "#fff5f5" : "#fffbeb",
              border: `1px solid ${sendResult.startsWith("✓") ? "#bbf7d0" : sendResult.startsWith("⚠") ? "#fecaca" : "#fde68a"}`,
              borderRadius: 8, padding: "8px 12px"
            }}>
              <p style={{
                fontSize: 11,
                color: sendResult.startsWith("✓") ? "#15803d" : sendResult.startsWith("⚠") ? "#dc2626" : "#92400e",
                margin: 0, fontFamily: "monospace", whiteSpace: "pre-wrap"
              }}>{sendResult}</p>
              {sendResult.startsWith("✓") && sendResult.includes("Campaign:") && (
                <a href="/campaigns" style={{ display: "inline-block", marginTop: 6, fontSize: 11, fontWeight: 700, color: "#15803d" }}>
                  → View Campaign History
                </a>
              )}
            </div>
          )}
          <button onClick={sendEmails} disabled={sending || !sendListId}
            style={{
              background: sending ? "#e5e7eb" : dryRun ? "linear-gradient(135deg,#92400e,#d97706)" : "linear-gradient(135deg,#991b1b,#ef4444)",
              color: sending ? "#9ca3af" : "#fff", border: "none", borderRadius: 8,
              padding: "9px 14px", fontSize: 12, fontWeight: 700,
              cursor: sending ? "not-allowed" : "pointer"
            }}>
            {sending ? "⟳ Running…" : dryRun ? "🔍 Preview Queue" : "🚀 Send Now"}
          </button>
        </div>

        {/* Step 5 — Track */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: "20px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#8b5cf6", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 14 }}>5</div>
            <span style={{ fontSize: 16 }}>📊</span>
            <span style={{ fontWeight: 700, color: "#0f3622", fontSize: 14 }}>Track Results</span>
          </div>
          <p style={{ fontSize: 12, color: "#6b9e7e", margin: 0, lineHeight: 1.6 }}>
            Every open, click, reply, and bounce is tracked. View the full funnel — from colleges discovered to meetings won — on the dashboard.
          </p>
          <div style={{ fontSize: 12, color: "#6b9e7e", background: "#f8f0ff", padding: "8px 12px", borderRadius: 8, border: "1px solid #e9d5ff" }}>
            <strong style={{ color: "#6d28d9" }}>Auto follow-ups:</strong> Day 3, 7, and 14 — drafted automatically, appear in Approval Queue for your review.
          </div>
          <a href="/" style={{ background: "#8b5cf6", color: "#fff", borderRadius: 8, padding: "8px 14px", fontSize: 12, fontWeight: 700, textDecoration: "none", textAlign: "center" }}>
            → View Dashboard
          </a>
        </div>
      </div>

    </div>
  );
}
