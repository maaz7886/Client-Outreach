import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIValytics Outreach",
  description: "College outreach CRM — Build · Learn · Deploy",
};

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/pipeline", label: "⚙ Pipeline" },
  { href: "/colleges", label: "Colleges" },
  { href: "/contacts", label: "Contacts" },
  { href: "/drafts", label: "Approval Queue" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased" style={{ background: "var(--background)", color: "var(--foreground)" }}>
        {/* Top bar */}
        <header style={{ background: "var(--brand-dark)", borderBottom: "1px solid #0a2818" }}>
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-0">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-3 py-3 group">
              <div style={{
                width: 36, height: 36, borderRadius: 8,
                background: "linear-gradient(135deg,#2d7a50,#1a5c38)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, fontWeight: 800, color: "#fff", letterSpacing: "-1px",
                boxShadow: "0 2px 8px rgba(0,0,0,0.3)"
              }}>AI</div>
              <div>
                <span style={{ color: "#fff", fontWeight: 700, fontSize: 15, letterSpacing: "0.02em" }}>
                  AIValytics
                </span>
                <span style={{ color: "#6dbd94", fontWeight: 400, fontSize: 10, display: "block", letterSpacing: "0.15em", textTransform: "uppercase" }}>
                  BUILD · LEARN · DEPLOY
                </span>
              </div>
            </Link>

            {/* Nav */}
            <nav className="flex items-center gap-1">
              {nav.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  style={{ color: "#a8d5bc", fontSize: 13, fontWeight: 500, padding: "8px 14px", borderRadius: 6, transition: "all 0.15s" }}
                  className="hover:text-white hover:bg-white/10"
                >
                  {n.label}
                </Link>
              ))}
            </nav>

            {/* Right tag */}
            <div style={{
              background: "linear-gradient(135deg,#2d7a50,#1a5c38)",
              color: "#fff", fontSize: 11, fontWeight: 700,
              padding: "6px 14px", borderRadius: 6, letterSpacing: "0.08em",
              textTransform: "uppercase"
            }}>
              Outreach CRM
            </div>
          </div>
        </header>

        {/* Sub-nav strip */}
        <div style={{ background: "#fff", borderBottom: "1px solid #e2ede8" }}>
          <div className="mx-auto max-w-7xl px-6 py-2 flex items-center gap-4">
            <span style={{ fontSize: 11, fontWeight: 600, color: "#1a5c38", letterSpacing: "0.1em", textTransform: "uppercase" }}>
              ◆ College Outreach System
            </span>
            <div style={{ width: 1, height: 14, background: "#d0e8da" }} />
            <span style={{ fontSize: 11, color: "#6b9e7e" }}>AI-Powered · Compliance-First · Human-in-the-Loop</span>
          </div>
        </div>

        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>

        {/* Footer */}
        <footer style={{ borderTop: "1px solid #e2ede8", marginTop: 48, background: "#fff" }}>
          <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
            <span style={{ fontSize: 12, color: "#94b5a0" }}>© 2026 AIValytics — Outreach CRM</span>
            <span style={{ fontSize: 12, color: "#94b5a0" }}>BUILD · LEARN · DEPLOY</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
