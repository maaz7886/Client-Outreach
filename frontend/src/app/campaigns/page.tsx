"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type CampaignRow = {
  id: number;
  name: string;
  list_id: number | null;
  list_name: string | null;
  recipient_count: number;
  started_at: string;
  completed_at: string | null;
  sent: number;
  failed: number;
  suppressed: number;
};

function formatDateTime(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function duration(started: string, completed: string | null) {
  if (!completed) return "In progress";
  const ms = new Date(completed).getTime() - new Date(started).getTime();
  if (ms < 1000) return "< 1s";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60_000)}m`;
}

export default function CampaignsPage() {
  const [rows, setRows] = useState<CampaignRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<{ total: number; items: CampaignRow[] }>("/api/campaigns?limit=100")
      .then((d) => { setRows(d.items); setTotal(d.total); setError(null); })
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
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f3622", margin: 0 }}>
          Campaign History
          <span style={{ fontSize: 14, fontWeight: 400, color: "#6b9e7e", marginLeft: 8 }}>
            {total} total
          </span>
        </h1>
        <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 2 }}>
          Every send operation is recorded with delivery results
        </p>
      </div>

      <div style={{
        background: "#fff", borderRadius: 14, border: "1px solid #dceae2",
        overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)",
      }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {[
                "Campaign", "List", "Recipients", "Started", "Completed", "Duration",
                "Sent", "Failed", "Suppressed",
              ].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700,
                    color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em",
                    borderBottom: "1px solid #dceae2", whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr
                key={c.id}
                style={{
                  borderTop: "1px solid #f0f7f3",
                  background: i % 2 === 0 ? "#fff" : "#fafcfb",
                }}
              >
                <td style={{ padding: "10px 14px", fontWeight: 600, color: "#0f3622", maxWidth: 220 }}>
                  {c.name}
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c" }}>
                  {c.list_name ?? <span style={{ color: "#c0d8c8" }}>All contacts</span>}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{
                    background: "#e8f5ee", color: "#1a5c38", borderRadius: 6,
                    padding: "2px 8px", fontSize: 12, fontWeight: 700,
                  }}>
                    {c.recipient_count}
                  </span>
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", whiteSpace: "nowrap" }}>
                  {formatDateTime(c.started_at)}
                </td>
                <td style={{ padding: "10px 14px", color: "#4a7a5c", whiteSpace: "nowrap" }}>
                  {formatDateTime(c.completed_at)}
                </td>
                <td style={{ padding: "10px 14px", color: "#6b9e7e", fontSize: 12 }}>
                  {duration(c.started_at, c.completed_at)}
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ color: "#15803d", fontWeight: 700 }}>{c.sent}</span>
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ color: c.failed > 0 ? "#dc2626" : "#94b5a0", fontWeight: 700 }}>
                    {c.failed}
                  </span>
                </td>
                <td style={{ padding: "10px 14px" }}>
                  <span style={{ color: c.suppressed > 0 ? "#d97706" : "#94b5a0", fontWeight: 700 }}>
                    {c.suppressed}
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ padding: "40px 16px", textAlign: "center", color: "#94b5a0" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>📨</div>
                  No campaigns yet — send emails from the Pipeline to create your first campaign record.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
