"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import {
  AccessGrant,
  Employee,
  EmployeeDetail,
  OffboardingRun,
  ReassignmentAction,
  confirmReassignment,
  getEmployee,
  isLoggedIn,
  listEmployees,
  listReassignments,
  startOffboardingRun,
} from "@/lib/api";

function resourceCell(g: AccessGrant) {
  if (g.system === "slack" && g.grant_type === "channel_member") {
    return (
      <a
        href={`https://slack.com/app_redirect?channel=${g.external_id}`}
        target="_blank"
        rel="noreferrer"
        style={{ textDecoration: "underline" }}
      >
        {g.resource_name ?? g.external_id}
      </a>
    );
  }
  return <>{g.resource_name ?? "—"}</>;
}

export default function EmployeeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [allEmployees, setAllEmployees] = useState<Employee[]>([]);

  const [environment, setEnvironment] = useState<"sandbox" | "production">("production");
  const [run, setRun] = useState<OffboardingRun | null>(null);
  const [reassignments, setReassignments] = useState<ReassignmentAction[]>([]);
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    getEmployee(id)
      .then(setEmployee)
      .finally(() => setLoading(false));
    listEmployees().then(setAllEmployees);
  }, [id, router]);

  async function handleStartOffboarding() {
    if (!employee) return;
    setStarting(true);
    setRunError(null);
    try {
      const newRun = await startOffboardingRun(employee.id, environment);
      setRun(newRun);
      setReassignments(await listReassignments(newRun.id));
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Failed to start offboarding run.");
    } finally {
      setStarting(false);
    }
  }

  async function handleConfirm(reassignmentId: string, ownerId: string) {
    const updated = await confirmReassignment(reassignmentId, ownerId);
    setReassignments((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  if (loading) {
    return (
      <div>
        <Nav />
        <p style={{ padding: 24 }}>Loading...</p>
      </div>
    );
  }

  if (!employee) {
    return (
      <div>
        <Nav />
        <p style={{ padding: 24 }}>Employee not found.</p>
      </div>
    );
  }

  const grantById = new Map(employee.access_grants.map((g) => [g.id, g]));
  const workItemById = new Map(employee.work_items.map((w) => [w.id, w]));
  const otherEmployees = allEmployees.filter((e) => e.id !== employee.id);

  return (
    <div>
      <Nav />
      <div style={{ maxWidth: 900, margin: "32px auto", padding: 24 }}>
        <a href="/employees" style={{ fontSize: 13, textDecoration: "underline" }}>
          &larr; Employees
        </a>
        <h1 style={{ margin: "8px 0 4px" }}>{employee.full_name}</h1>
        <p style={{ color: "#4a5568", marginBottom: 24 }}>
          {employee.company_email} — {employee.department ?? "no department"} — {employee.status}
        </p>

        <h3 style={{ marginBottom: 8 }}>Active access grants ({employee.access_grants.length})</h3>
        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #e2e8f0" }}>
              <th style={{ padding: 8 }}>System</th>
              <th style={{ padding: 8 }}>Type</th>
              <th style={{ padding: 8 }}>Resource</th>
              <th style={{ padding: 8 }}>Role</th>
            </tr>
          </thead>
          <tbody>
            {employee.access_grants.map((g) => (
              <tr key={g.id} style={{ borderBottom: "1px solid #edf2f7" }}>
                <td style={{ padding: 8 }}>{g.system}</td>
                <td style={{ padding: 8 }}>{g.grant_type}</td>
                <td style={{ padding: 8 }}>{resourceCell(g)}</td>
                <td style={{ padding: 8 }}>{g.role ?? "—"}</td>
              </tr>
            ))}
            {employee.access_grants.length === 0 && (
              <tr>
                <td colSpan={4} style={{ padding: 8, color: "#718096" }}>
                  No access synced yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <h3 style={{ marginBottom: 8 }}>Open work items ({employee.work_items.length})</h3>
        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 32 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #e2e8f0" }}>
              <th style={{ padding: 8 }}>System</th>
              <th style={{ padding: 8 }}>Title</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Skill tags</th>
            </tr>
          </thead>
          <tbody>
            {employee.work_items.map((w) => (
              <tr key={w.id} style={{ borderBottom: "1px solid #edf2f7" }}>
                <td style={{ padding: 8 }}>{w.system}</td>
                <td style={{ padding: 8 }}>
                  {w.url ? (
                    <a href={w.url} target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>
                      {w.title ?? w.url}
                    </a>
                  ) : (
                    w.title ?? "—"
                  )}
                </td>
                <td style={{ padding: 8 }}>{w.status}</td>
                <td style={{ padding: 8 }}>{w.skill_tags?.join(", ") ?? "—"}</td>
              </tr>
            ))}
            {employee.work_items.length === 0 && (
              <tr>
                <td colSpan={4} style={{ padding: 8, color: "#718096" }}>
                  No open work items synced yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <h3 style={{ marginBottom: 8 }}>Offboarding</h3>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16 }}>
          <select
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as "sandbox" | "production")}
            disabled={!!run}
            style={{ padding: 8 }}
          >
            <option value="production">production</option>
            <option value="sandbox">sandbox</option>
          </select>
          <button onClick={handleStartOffboarding} disabled={starting || !!run} style={{ padding: "8px 14px" }}>
            {starting ? "Starting..." : run ? "Run started" : "Start Offboarding"}
          </button>
        </div>

        {runError && <p style={{ color: "#c53030", marginBottom: 16 }}>{runError}</p>}

        {run && (
          <div style={{ marginBottom: 32 }}>
            <p style={{ marginBottom: 8 }}>
              <b>Run status:</b> {run.status}
            </p>
            {run.narrative && (
              <p style={{ background: "#f7fafc", border: "1px solid #e2e8f0", padding: 12, borderRadius: 6, marginBottom: 16 }}>
                {run.narrative}
              </p>
            )}

            <h4 style={{ marginBottom: 8 }}>Revocation results</h4>
            <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "2px solid #e2e8f0" }}>
                  <th style={{ padding: 8 }}>Grant</th>
                  <th style={{ padding: 8 }}>Revoke</th>
                  <th style={{ padding: 8 }}>Verify</th>
                  <th style={{ padding: 8 }}>Error</th>
                </tr>
              </thead>
              <tbody>
                {run.revocation_actions.map((a) => {
                  const grant = grantById.get(a.access_grant_id);
                  return (
                    <tr key={a.id} style={{ borderBottom: "1px solid #edf2f7" }}>
                      <td style={{ padding: 8 }}>
                        {grant ? `${grant.system} — ${grant.resource_name ?? grant.grant_type}` : a.access_grant_id}
                      </td>
                      <td style={{ padding: 8 }}>{a.revoke_status}</td>
                      <td style={{ padding: 8 }}>{a.verify_status}</td>
                      <td style={{ padding: 8, color: "#c53030" }}>{a.error_message ?? "—"}</td>
                    </tr>
                  );
                })}
                {run.revocation_actions.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ padding: 8, color: "#718096" }}>
                      No active access grants to revoke.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            {reassignments.length > 0 && (
              <>
                <h4 style={{ marginBottom: 8 }}>Reassignment suggestions</h4>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "2px solid #e2e8f0" }}>
                      <th style={{ padding: 8 }}>Work item</th>
                      <th style={{ padding: 8 }}>Suggested owner</th>
                      <th style={{ padding: 8 }}>Justification</th>
                      <th style={{ padding: 8 }}>Confirm as</th>
                      <th style={{ padding: 8 }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reassignments.map((r) => {
                      const item = workItemById.get(r.work_item_id);
                      const suggested = allEmployees.find((e) => e.id === r.suggested_owner_id);
                      const isConfirmed = r.confirmed_owner_id !== null;
                      return (
                        <ReassignmentRow
                          key={r.id}
                          reassignment={r}
                          itemTitle={item?.title ?? r.work_item_id}
                          suggestedName={suggested?.full_name ?? "no candidate found"}
                          candidates={otherEmployees}
                          isConfirmed={isConfirmed}
                          onConfirm={(ownerId) => handleConfirm(r.id, ownerId)}
                        />
                      );
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ReassignmentRow({
  reassignment,
  itemTitle,
  suggestedName,
  candidates,
  isConfirmed,
  onConfirm,
}: {
  reassignment: ReassignmentAction;
  itemTitle: string;
  suggestedName: string;
  candidates: Employee[];
  isConfirmed: boolean;
  onConfirm: (ownerId: string) => void;
}) {
  const [selected, setSelected] = useState(reassignment.suggested_owner_id ?? "");

  return (
    <tr style={{ borderBottom: "1px solid #edf2f7" }}>
      <td style={{ padding: 8 }}>{itemTitle}</td>
      <td style={{ padding: 8 }}>{suggestedName}</td>
      <td style={{ padding: 8, fontSize: 13, color: "#4a5568" }}>{reassignment.justification ?? "—"}</td>
      <td style={{ padding: 8 }}>
        {isConfirmed ? (
          candidates.find((c) => c.id === reassignment.confirmed_owner_id)?.full_name ?? "confirmed"
        ) : (
          <div style={{ display: "flex", gap: 6 }}>
            <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{ padding: 4 }}>
              <option value="" disabled>
                choose owner
              </option>
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name}
                </option>
              ))}
            </select>
            <button onClick={() => selected && onConfirm(selected)} disabled={!selected} style={{ padding: "4px 10px" }}>
              Confirm
            </button>
          </div>
        )}
      </td>
      <td style={{ padding: 8 }}>
        {reassignment.reassign_status} / {reassignment.verify_status}
      </td>
    </tr>
  );
}
