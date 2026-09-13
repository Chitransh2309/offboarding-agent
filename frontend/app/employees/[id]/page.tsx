"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { EmployeeDetail, getEmployee, isLoggedIn } from "@/lib/api";

export default function EmployeeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    getEmployee(id)
      .then(setEmployee)
      .finally(() => setLoading(false));
  }, [id, router]);

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

  return (
    <div>
      <Nav />
      <div style={{ maxWidth: 800, margin: "32px auto", padding: 24 }}>
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
                <td style={{ padding: 8 }}>{g.resource_name ?? "—"}</td>
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
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
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
      </div>
    </div>
  );
}
