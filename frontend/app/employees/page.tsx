"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { Employee, isLoggedIn, listEmployees } from "@/lib/api";

export default function EmployeesPage() {
  const router = useRouter();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    listEmployees()
      .then(setEmployees)
      .finally(() => setLoading(false));
  }, [router]);

  const statusColor: Record<Employee["status"], string> = {
    active: "#c6f6d5",
    departing: "#feebc8",
    offboarded: "#e2e8f0",
  };

  return (
    <div>
      <Nav />
      <div style={{ maxWidth: 900, margin: "32px auto", padding: 24 }}>
        <h1 style={{ marginBottom: 4 }}>Employees</h1>
        <p style={{ color: "#4a5568", marginBottom: 24 }}>
          Synced from connected workspaces. {employees.length} total.
        </p>

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
