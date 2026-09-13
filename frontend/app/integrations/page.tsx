"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Nav from "@/components/Nav";
import {
  IntegrationConnection,
  SystemType,
  getAuthorizeUrl,
  isLoggedIn,
  listIntegrations,
  setNotionReportSettings,
} from "@/lib/api";

const SYSTEMS: { key: SystemType; label: string; description: string }[] = [
  { key: "github", label: "GitHub", description: "Org membership, repo access, issues & PRs" },
  { key: "slack", label: "Slack", description: "Workspace/channel membership" },
  { key: "notion", label: "Notion", description: "Page ownership & access (read-only revoke)" },
  { key: "linear", label: "Linear", description: "Workspace membership, assigned issues" },
];

function Banner() {
  const params = useSearchParams();
  const connected = params.get("connected");
  const error = params.get("error");
  const detail = params.get("detail");
  const syncError = params.get("sync_error");
  const discovered = params.get("discovered");
  const linked = params.get("linked");
  const skipped = params.get("skipped");

  if (error) {
    return (
      <div style={{ background: "#fed7d7", padding: 12, borderRadius: 6, marginBottom: 16 }}>
        Failed to connect {error}: {detail}
      </div>
    );
  }
  if (connected) {
    return (
      <div style={{ background: "#c6f6d5", padding: 12, borderRadius: 6, marginBottom: 16 }}>
        Connected {connected}.
        {syncError
          ? ` Sync failed: ${syncError}`
          : ` Synced employees — ${discovered} new, ${linked} matched to existing, ${skipped} skipped (no email available).`}
      </div>
    );
  }
  return null;
}

function NotionReportSettingsForm() {
  const [pageId, setPageId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    if (!pageId.trim()) return;
    setSaving(true);
    setSaved(false);
    try {
      await setNotionReportSettings(pageId.trim());
      setSaved(true);
    } catch {
      alert("Could not save — check the page id and that Notion is connected.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #edf2f7" }}>
      <p style={{ fontSize: 12, color: "#4a5568", marginBottom: 6 }}>
        Parent page for auto-generated offboarding reports (share this page with the Notion
        integration first):
      </p>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          value={pageId}
          onChange={(e) => setPageId(e.target.value)}
          placeholder="Notion page ID"
          style={{ flex: 1, padding: 6, fontSize: 12 }}
        />
        <button onClick={handleSave} disabled={saving} style={{ padding: "6px 10px", fontSize: 12 }}>
          {saving ? "Saving..." : saved ? "Saved" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default function IntegrationsPage() {
  const router = useRouter();
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingSystem, setConnectingSystem] = useState<SystemType | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    listIntegrations()
      .then(setConnections)
      .finally(() => setLoading(false));
  }, [router]);

  async function handleConnect(system: SystemType) {
    setConnectingSystem(system);
    try {
      const { authorize_url } = await getAuthorizeUrl(system);
      window.location.href = authorize_url;
    } catch {
      setConnectingSystem(null);
      alert(`Could not start ${system} connect flow — check that its client id/secret are set in the backend .env.`);
    }
  }

  function statusFor(system: SystemType): IntegrationConnection | undefined {
    return connections.find((c) => c.system === system && c.environment === "production");
  }

  return (
    <div>
      <Nav />
      <div style={{ maxWidth: 800, margin: "32px auto", padding: 24 }}>
        <h1 style={{ marginBottom: 4 }}>Integrations</h1>
        <p style={{ color: "#4a5568", marginBottom: 24 }}>
          Connect your org&apos;s real accounts. Connecting also syncs the workspace&apos;s
          members into the employee directory.
        </p>

        <Suspense fallback={null}>
          <Banner />
        </Suspense>

        {loading ? (
          <p>Loading...</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {SYSTEMS.map(({ key, label, description }) => {
              const connection = statusFor(key);
              return (
                <div
                  key={key}
                  style={{
                    border: "1px solid #e2e8f0",
                    borderRadius: 8,
                    padding: 16,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                    <div>
                      <h3 style={{ marginBottom: 4 }}>{label}</h3>
                      <p style={{ color: "#4a5568", fontSize: 13, marginBottom: 12 }}>{description}</p>
                    </div>
                    {connection && (
                      <span
                        style={{
                          fontSize: 12,
                          padding: "2px 8px",
                          borderRadius: 999,
                          background: connection.status === "active" ? "#c6f6d5" : "#fed7d7",
                          color: "#22543d",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {connection.status}
                      </span>
                    )}
                  </div>
                  {connection ? (
                    <p style={{ fontSize: 12, color: "#718096", marginBottom: 8 }}>
                      Connected {new Date(connection.connected_at).toLocaleString()}
                    </p>
                  ) : null}
                  <button
                    onClick={() => handleConnect(key)}
                    disabled={connectingSystem === key}
                    style={{ padding: "8px 14px" }}
                  >
                    {connectingSystem === key
                      ? "Redirecting..."
                      : connection
                        ? "Reconnect"
                        : "Connect"}
                  </button>
                  {key === "notion" && connection && <NotionReportSettingsForm />}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
