"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type ContactRow = {
  id: number; full_name: string; role: string; college: string;
  email: string | null; confidence: number; status: string; notes: string | null;
};

const FILTERS = ["", "VERIFIED", "NEEDS_MANUAL_REVIEW", "CONTACTED",
  "REPLIED_POSITIVE", "MEETING_SCHEDULED", "WON", "LOST"];

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
};

function confidenceColor(c: number) {
  if (c >= 80) return "#15803d";
  if (c >= 60) return "#d97706";
  return "#dc2626";
}

export default function ContactsPage() {
  const [filter, setFilter] = useState("");
  const [rows, setRows] = useState<ContactRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const qs = filter ? `?status=${filter.toLowerCase()}&limit=100` : "?limit=100";
    api<{ total: number; items: ContactRow[] }>(`/api/contacts${qs}`)
      .then((d) => { setRows(d.items); setTotal(d.total); })
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
      {/* Header */}
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
          style={{
            border: "1.5px solid #cce0d4", borderRadius: 8,
            padding: "8px 14px", fontSize: 13, color: "#0f1a14",
            background: "#fff", outline: "none", cursor: "pointer"
          }}
        >
          {FILTERS.map((f) => (
            <option key={f} value={f}>{f === "" ? "All statuses" : f.replaceAll("_", " ")}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "Role", "College", "Email", "Confidence", "Status", "Actions"].map((h) => (
                <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2" }}>
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
                  <td style={{ padding: "10px 16px", fontWeight: 600, color: "#0f3622" }}>{c.full_name}</td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ background: "#e8f5ee", color: "#1a5c38", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>
                      {c.role.replaceAll("_", " ")}
                    </span>
                  </td>
                  <td style={{ padding: "10px 16px", color: "#4a7a5c" }}>{c.college}</td>
                  <td style={{ padding: "10px 16px", color: "#4a7a5c", fontFamily: "monospace", fontSize: 12 }}>
                    {c.email ?? <span style={{ color: "#c0d8c8" }}>not found</span>}
                  </td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ fontWeight: 700, color: confidenceColor(c.confidence), fontSize: 13 }}>
                      {c.confidence}%
                    </span>
                  </td>
                  <td style={{ padding: "10px 16px" }}>
                    <span style={{ background: ss.bg, color: ss.color, borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600 }}>
                      {c.status.replaceAll("_", " ")}
                    </span>
                  </td>
                  <td style={{ padding: "10px 16px", display: "flex", gap: 6 }}>
                    {c.status === "REPLIED_POSITIVE" && (
                      <button onClick={() => setStatus(c.id, "meeting_scheduled")}
                        style={{ background: "#ede9fe", color: "#6d28d9", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                        📅 Meeting
                      </button>
                    )}
                    {c.status === "MEETING_SCHEDULED" && (
                      <>
                        <button onClick={() => setStatus(c.id, "won")}
                          style={{ background: "#d1fae5", color: "#065f46", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                          🏆 Won
                        </button>
                        <button onClick={() => setStatus(c.id, "lost")}
                          style={{ background: "#f3f4f6", color: "#6b7280", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                          Lost
                        </button>
                      </>
                    )}
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
