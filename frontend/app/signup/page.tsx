"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signup, setToken } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await signup(orgName, email, password);
      setToken(res.access_token);
      router.push("/integrations");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto", padding: 24 }}>
      <h1 style={{ marginBottom: 24 }}>Create your organization</h1>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input
          type="text"
          placeholder="Organization name"
          value={orgName}
          onChange={(e) => setOrgName(e.target.value)}
          required
          style={{ padding: 10 }}
        />
        <input
          type="email"
          placeholder="Admin email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{ padding: 10 }}
        />
        <input
          type="password"
          placeholder="Password (min 8 chars)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          style={{ padding: 10 }}
        />
        {error && <p style={{ color: "#c53030" }}>{error}</p>}
        <button type="submit" disabled={loading} style={{ padding: 10 }}>
          {loading ? "Creating..." : "Create organization"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        Already have an org? <Link href="/login" style={{ textDecoration: "underline" }}>Log in</Link>
      </p>
    </div>
  );
}
