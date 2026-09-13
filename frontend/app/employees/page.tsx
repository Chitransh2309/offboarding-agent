"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { Employee, SystemResyncResult, isLoggedIn, listEmployees, resyncEmployees } from "@/lib/api";

export default function EmployeesPage() {
  const router = useRouter();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResults, setSyncResults] = useState<SystemResyncResult[] | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  function loadEmployees() {
    return listEmployees().then(setEmployees);
  }

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    loadEmployees().finally(() => setLoading(false));
  }, [router]);

  async function handleResync() {
    setSyncing(true);
    setSyncError(null);
    setSyncResults(null);
    try {
      const { results } = await resyncEmployees();
      setSyncResults(results);
      await loadEmployees();
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : "Resync failed.");
    } finally {
      setSyncing(false);
    }
  }

  const statusColor: Record<Employee["status"], string> = {
    active: "#c6f6d5",
    departing: "#feebc8",
    offboarded: "#e2e8f0",
  };

  return (
    <div>
      <Nav />
      <div style={{ maxWidth: 900, margin: "32px auto", padding: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Employees</h1>
            <p style={{ color: "#4a5568", marginBottom: 24 }}>
              Synced from connected workspaces. {employees.length} total.
            </p>
          </div>
          <button onClick={handleResync} disabled={syncing} style={{ padding: "8px 14px" }}>
            {syncing ? "Syncing..." : "Resync"}
          </button>
        </div>

        {syncError && <p style={{ color: "#c53030", marginBottom: 16 }}>{syncError}</p>}
        {syncResults && (
          <div style={{ background: "#f7fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: 12, marginBottom: 16, fontSize: 13 }}>
            {syncResults.length === 0 ? (
              <p>No connected systems to sync.</p>
            ) : (
              syncResults.map((r) => (
                <p key={r.system} style={{ margin: "2px 0" }}>
                  <b>{r.system}</b>: {r.discovered} new, {r.linked} matched, {r.skipped} skipped
                </p>
              ))
            )}
          </div>
        )}

        {loading ? (
          <p>Loading...</p>
        ) : employees.length === 0 ? (
          <p>
            No employees yet — connect an app on the{" "}
            <a href="/integrations" style={{ textDecoration: "underline" }}>
              Integrations
            </a>{" "}
            page to sync your workspace roster.
          </p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #e2e8f0" }}>
                <th style={{ padding: 8 }}>Name</th>
                <th style={{ padding: 8 }}>Email</th>
                <th style={{ padding: 8 }}>Department</th>
                <th style={{ padding: 8 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => (
                <tr key={e.id} style={{ borderBottom: "1px solid #edf2f7" }}>
                  <td style={{ padding: 8 }}>
                    <a href={`/employees/${e.id}`} style={{ textDecoration: "underline" }}>
                      {e.full_name}
                    </a>
                  </td>
                  <td style={{ padding: 8 }}>{e.company_email}</td>
                  <td style={{ padding: 8 }}>{e.department ?? "—"}</td>
                  <td style={{ padding: 8 }}>
                    <span
                      style={{
                        fontSize: 12,
                        padding: "2px 8px",
                        borderRadius: 999,
                        background: statusColor[e.status],
                        color: "#000",
                      }}
                    >
                      {e.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
