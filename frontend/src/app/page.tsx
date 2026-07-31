"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

type Stats = {
  colleges: number; contacts: number; emails_sent: number;
  open_rate: number; click_rate: number; reply_rate: number;
  positive: number; meetings: number; won: number;
  funnel: Record<string, number>;
  colleges_by_state: Record<string, number>;
};

const FUNNEL_ORDER = [
  "DISCOVERED", "VERIFIED", "NEEDS_MANUAL_REVIEW", "CONTACTED",
  "REPLIED_POSITIVE", "MEETING_SCHEDULED", "WON",
];

const FUNNEL_COLORS: Record<string, string> = {
  DISCOVERED: "#94b5a0",
  VERIFIED: "#4caf7d",
  NEEDS_MANUAL_REVIEW: "#f59e0b",
  CONTACTED: "#3b82f6",
  REPLIED_POSITIVE: "#8b5cf6",
  MEETING_SCHEDULED: "#ec4899",
  WON: "#1a5c38",
};

function StatCard({ label, value, sub, icon }: { label: string; value: string | number; sub?: string; icon: string }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 12,
      border: "1px solid #dceae2",
      padding: "20px 22px",
      boxShadow: "0 2px 8px rgba(15,54,34,0.05)"
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <p style={{ fontSize: 11, fontWeight: 600, color: "#6b9e7e", textTransform: "uppercase", letterSpacing: "0.08em", margin: 0 }}>
            {label}
          </p>
          <p style={{ fontSize: 28, fontWeight: 800, color: "#0f3622", margin: "4px 0 0", lineHeight: 1 }}>
            {value}
          </p>
          {sub && <p style={{ fontSize: 11, color: "#94b5a0", marginTop: 4 }}>{sub}</p>}
        </div>
        <span style={{
          fontSize: 22, width: 40, height: 40, borderRadius: 10,
          background: "#e8f5ee", display: "flex", alignItems: "center", justifyContent: "center"
        }}>{icon}</span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    api<Stats>("/api/stats").then(setStats).catch((e) => setError(String(e)));
  }, [router]);

  if (error) return (
    <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 12, padding: 24, color: "#dc2626" }}>
      ⚠ {error}
    </div>
  );

  if (!stats) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300 }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: 40, height: 40, border: "3px solid #1a5c38", borderTopColor: "transparent", borderRadius: "50%", margin: "0 auto 12px", animation: "spin 0.8s linear infinite" }} />
        <p style={{ color: "#6b9e7e", fontSize: 14 }}>Loading dashboard…</p>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
  const maxState = Math.max(1, ...Object.values(stats.colleges_by_state));
  const maxFunnel = Math.max(1, ...FUNNEL_ORDER.map((s) => stats.funnel[s] ?? 0));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>

      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 800, color: "#0f3622", margin: 0 }}>
            Campaign Dashboard
          </h1>
          <p style={{ color: "#6b9e7e", fontSize: 13, marginTop: 4 }}>
            Real-time overview of your college outreach pipeline
          </p>
        </div>
        <div style={{
          background: "linear-gradient(135deg, #0f3622, #1a5c38)",
          color: "#fff", borderRadius: 8, padding: "8px 16px",
          fontSize: 12, fontWeight: 600, letterSpacing: "0.06em"
        }}>
          ◆ LIVE DATA
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 14 }}>
        <StatCard label="Colleges" value={stats.colleges} sub="in database" icon="🏫" />
        <StatCard label="Contacts" value={stats.contacts} sub="decision-makers" icon="👤" />
        <StatCard label="Emails Sent" value={stats.emails_sent} sub="outreach messages" icon="📧" />
        <StatCard label="Open Rate" value={pct(stats.open_rate)} sub="engagement" icon="📬" />
        <StatCard label="Reply Rate" value={pct(stats.reply_rate)} sub="responses" icon="💬" />
        <StatCard label="Meetings" value={stats.meetings} sub="scheduled" icon="🤝" />
        <StatCard label="Won" value={stats.won} sub="partnerships" icon="🏆" />
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>

        {/* Funnel */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: 24, boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, color: "#0f3622", margin: "0 0 18px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            📊 Outreach Funnel
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {FUNNEL_ORDER.map((stage) => {
              const v = stats.funnel[stage] ?? 0;
              const pct = maxFunnel > 0 ? (v / maxFunnel) * 100 : 0;
              return (
                <div key={stage} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ width: 160, fontSize: 11, color: "#4a7a5c", flexShrink: 0, fontWeight: 500 }}>
                    {stage.replaceAll("_", " ")}
                  </span>
                  <div style={{ flex: 1, height: 18, background: "#f0f7f3", borderRadius: 6, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 6,
                      background: FUNNEL_COLORS[stage] ?? "#1a5c38",
                      width: `${pct}%`,
                      transition: "width 0.6s ease",
                      minWidth: v > 0 ? 4 : 0
                    }} />
                  </div>
                  <span style={{ width: 28, fontSize: 12, fontWeight: 700, color: "#0f3622", textAlign: "right" }}>{v}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* States */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #dceae2", padding: 24, boxShadow: "0 2px 8px rgba(15,54,34,0.05)" }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, color: "#0f3622", margin: "0 0 18px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            🗺 Colleges by State
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {Object.entries(stats.colleges_by_state)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 12)
              .map(([state, count]) => (
                <div key={state} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ width: 160, fontSize: 11, color: "#4a7a5c", flexShrink: 0, fontWeight: 500 }}>
                    {state}
                  </span>
                  <div style={{ flex: 1, height: 18, background: "#f0f7f3", borderRadius: 6, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 6,
                      background: "linear-gradient(90deg, #1a5c38, #2d7a50)",
                      width: `${(count / maxState) * 100}%`,
                      transition: "width 0.6s ease",
                      minWidth: count > 0 ? 4 : 0
                    }} />
                  </div>
                  <span style={{ width: 28, fontSize: 12, fontWeight: 700, color: "#0f3622", textAlign: "right" }}>{count}</span>
                </div>
              ))}
            {Object.keys(stats.colleges_by_state).length === 0 && (
              <p style={{ fontSize: 13, color: "#94b5a0", textAlign: "center", padding: "20px 0" }}>
                No data yet — import colleges with the CLI
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Rates row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
        {[
          { label: "Open Rate", value: stats.open_rate, color: "#3b82f6" },
          { label: "Click Rate", value: stats.click_rate, color: "#8b5cf6" },
          { label: "Positive Replies", value: stats.positive, color: "#1a5c38", raw: true },
        ].map(({ label, value, color, raw }) => (
          <div key={label} style={{
            background: "#fff", borderRadius: 12, border: "1px solid #dceae2",
            padding: "18px 22px", boxShadow: "0 2px 8px rgba(15,54,34,0.05)"
          }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "#6b9e7e", textTransform: "uppercase", letterSpacing: "0.08em", margin: 0 }}>
              {label}
            </p>
            <p style={{ fontSize: 32, fontWeight: 800, color, margin: "6px 0 0" }}>
              {raw ? value : pct(value as number)}
            </p>
            {!raw && (
              <div style={{ marginTop: 8, height: 6, background: "#f0f7f3", borderRadius: 4 }}>
                <div style={{ height: "100%", borderRadius: 4, background: color, width: `${Math.min((value as number) * 100, 100)}%` }} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
