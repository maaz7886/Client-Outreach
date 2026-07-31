"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type CollegeRow = {
  id: number; name: string; city: string; state: string;
  website: string | null; naac_grade: string | null; nirf_rank: number | null;
  type: string; contacts: number;
};

export default function CollegesPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<CollegeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api<{ total: number; items: CollegeRow[] }>(
        `/api/colleges?q=${encodeURIComponent(q)}&limit=100`
      )
        .then((d) => { setRows(d.items); setTotal(d.total); })
        .catch((e) => setError(String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

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
            background: "#fff", outline: "none", width: 220
          }}
        />
      </div>

      {/* Table */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", overflow: "hidden", boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f0f7f3" }}>
              {["Name", "City", "State", "Type", "NAAC", "NIRF Rank", "Contacts"].map((h) => (
                <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#3d6b4f", textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid #dceae2" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={c.id} style={{ borderTop: "1px solid #f0f7f3", background: i % 2 === 0 ? "#fff" : "#fafcfb" }}>
                <td style={{ padding: "10px 16px", fontWeight: 600, color: "#0f3622" }}>
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
                <td style={{ padding: "10px 16px", color: "#4a7a5c" }}>{c.city}</td>
                <td style={{ padding: "10px 16px", color: "#4a7a5c" }}>{c.state}</td>
                <td style={{ padding: "10px 16px" }}>
                  <span style={{ background: "#e8f5ee", color: "#1a5c38", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>
                    {c.type}
                  </span>
                </td>
                <td style={{ padding: "10px 16px" }}>
                  {c.naac_grade ? (
                    <span style={{ background: "#f0fdf4", color: "#15803d", borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 700 }}>
                      {c.naac_grade}
                    </span>
                  ) : <span style={{ color: "#c0d8c8" }}>—</span>}
                </td>
                <td style={{ padding: "10px 16px", color: "#4a7a5c" }}>{c.nirf_rank ?? "—"}</td>
                <td style={{ padding: "10px 16px" }}>
                  <span style={{ background: c.contacts > 0 ? "#e8f5ee" : "#f5f5f5", color: c.contacts > 0 ? "#1a5c38" : "#9ca3af", borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 700 }}>
                    {c.contacts}
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: "40px 16px", textAlign: "center", color: "#94b5a0" }}>
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
