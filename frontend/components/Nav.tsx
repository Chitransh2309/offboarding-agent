"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    clearToken();
    router.push("/login");
  }

  const linkStyle = (path: string): React.CSSProperties => ({
    padding: "8px 14px",
    borderRadius: 6,
    background: pathname === path ? "#2b6cb0" : "transparent",
    color: pathname === path ? "#fff" : "inherit",
  });

  return (
    <nav
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: "12px 24px",
        borderBottom: "1px solid #e2e8f0",
      }}
    >
      <strong style={{ marginRight: 16 }}>Offboarding Agent</strong>
      <Link href="/integrations" style={linkStyle("/integrations")}>
        Integrations
      </Link>
      <Link href="/employees" style={linkStyle("/employees")}>
        Employees
      </Link>
      <button onClick={logout} style={{ marginLeft: "auto", padding: "8px 14px" }}>
        Log out
      </button>
    </nav>
  );
}
