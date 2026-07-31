"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid credentials");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "80vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "100%", maxWidth: 420 }}>

        {/* Card */}
        <div style={{
          background: "#fff",
          borderRadius: 16,
          boxShadow: "0 4px 32px rgba(15,54,34,0.10)",
          border: "1px solid #d8ede2",
          overflow: "hidden"
        }}>
          {/* Card header */}
          <div style={{
            background: "linear-gradient(135deg, var(--brand-dark) 0%, var(--brand-green) 100%)",
            padding: "32px 32px 28px",
          }}>
            {/* Logo */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
              <div style={{
                width: 44, height: 44, borderRadius: 10,
                background: "rgba(255,255,255,0.15)",
                border: "1px solid rgba(255,255,255,0.25)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 18, fontWeight: 800, color: "#fff", letterSpacing: "-1px"
              }}>AI</div>
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 17, letterSpacing: "0.02em" }}>
                  AIValytics
                </div>
                <div style={{ color: "#7dd4a8", fontSize: 10, fontWeight: 500, letterSpacing: "0.15em", textTransform: "uppercase" }}>
                  BUILD · LEARN · DEPLOY
                </div>
              </div>
            </div>
            <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 700, margin: 0, lineHeight: 1.2 }}>
              Outreach CRM
            </h1>
            <p style={{ color: "#a8dfbe", fontSize: 13, marginTop: 4 }}>
              Sign in to manage your college campaigns
            </p>
          </div>

          {/* Form body */}
          <div style={{ padding: "28px 32px 32px" }}>
            <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>

              {/* Email */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#3d6b4f", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  Email address
                </label>
                <input
                  type="email"
                  required
                  autoFocus
                  placeholder="admin@aivalytics.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  style={{
                    width: "100%", boxSizing: "border-box",
                    border: "1.5px solid #cce0d4",
                    borderRadius: 8, padding: "10px 14px",
                    fontSize: 14, color: "#0f1a14",
                    background: "#f8faf9", outline: "none",
                    transition: "border-color 0.15s"
                  }}
                  onFocus={e => e.target.style.borderColor = "#1a5c38"}
                  onBlur={e => e.target.style.borderColor = "#cce0d4"}
                />
              </div>

              {/* Password */}
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#3d6b4f", marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  Password
                </label>
                <div style={{ position: "relative" }}>
                  <input
                    type={showPass ? "text" : "password"}
                    required
                    placeholder="••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{
                      width: "100%", boxSizing: "border-box",
                      border: "1.5px solid #cce0d4",
                      borderRadius: 8, padding: "10px 42px 10px 14px",
                      fontSize: 14, color: "#0f1a14",
                      background: "#f8faf9", outline: "none",
                      transition: "border-color 0.15s"
                    }}
                    onFocus={e => e.target.style.borderColor = "#1a5c38"}
                    onBlur={e => e.target.style.borderColor = "#cce0d4"}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    style={{
                      position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)",
                      background: "none", border: "none", cursor: "pointer",
                      color: "#6b9e7e", fontSize: 13, padding: 2
                    }}
                  >
                    {showPass ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              {/* Credentials hint */}
              <div style={{
                background: "#f0faf4",
                border: "1px solid #c8e8d4",
                borderRadius: 8, padding: "10px 14px",
                fontSize: 12, color: "#2d6b45"
              }}>
                <strong>Default credentials:</strong><br />
                Email: <code style={{ fontFamily: "monospace" }}>admin@aivalytics.com</code><br />
                Password: <code style={{ fontFamily: "monospace" }}>Admin1234</code>
              </div>

              {/* Error */}
              {error && (
                <div style={{
                  background: "#fff5f5", border: "1px solid #fecaca",
                  borderRadius: 8, padding: "10px 14px",
                  fontSize: 13, color: "#dc2626", display: "flex", alignItems: "center", gap: 8
                }}>
                  <span>⚠</span> {error}
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={busy}
                style={{
                  background: busy ? "#6b9e7e" : "linear-gradient(135deg, var(--brand-dark), var(--brand-green))",
                  color: "#fff", border: "none", borderRadius: 8,
                  padding: "12px 0", fontSize: 14, fontWeight: 700,
                  cursor: busy ? "not-allowed" : "pointer",
                  letterSpacing: "0.04em", textTransform: "uppercase",
                  transition: "opacity 0.15s", width: "100%",
                  boxShadow: busy ? "none" : "0 2px 12px rgba(15,54,34,0.25)"
                }}
              >
                {busy ? "Signing in…" : "Sign In →"}
              </button>
            </form>
          </div>
        </div>

        {/* Footer note */}
        <p style={{ textAlign: "center", marginTop: 16, fontSize: 12, color: "#6b9e7e" }}>
          AIValytics Outreach CRM · Build · Learn · Deploy
        </p>
      </div>
    </div>
  );
}
