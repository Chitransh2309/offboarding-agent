const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const TOKEN_KEY = "offboarding_agent_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return getToken() !== null;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    // Bypasses ngrok's free-tier browser-warning interstitial, which
    // otherwise intercepts background fetch() calls (no page navigation
    // to click "Visit Site" through) and returns an HTML page with no
    // CORS headers — surfaces in the browser as a CORS error, not what
    // it actually is.
    "ngrok-skip-browser-warning": "true",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

// --- Auth ---

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function signup(organization_name: string, admin_email: string, admin_password: string) {
  return request<TokenResponse>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ organization_name, admin_email, admin_password }),
  });
}

export function login(email: string, password: string) {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// --- Integrations ---

export type SystemType = "github" | "slack" | "notion" | "linear";

export interface IntegrationConnection {
  id: string;
  system: SystemType;
  environment: "sandbox" | "production";
  status: "active" | "revoked" | "expired" | "invalid";
  connected_at: string;
}

export function listIntegrations() {
  return request<IntegrationConnection[]>("/integrations");
}

export function getAuthorizeUrl(system: SystemType) {
  return request<{ authorize_url: string }>(`/integrations/${system}/authorize-url`);
}

export function connectArga(api_key: string) {
  return request<void>("/integrations/arga/connect", {
    method: "POST",
    body: JSON.stringify({ api_key }),
  });
}

export function provisionSandbox(ttl_minutes = 120, scenario_prompt?: string) {
  return request<IntegrationConnection[]>("/integrations/sandbox/provision", {
    method: "POST",
    body: JSON.stringify({ ttl_minutes, scenario_prompt }),
  });
}

export function setNotionReportSettings(reports_parent_page_id: string) {
  return request<void>("/integrations/notion/report-settings", {
    method: "PATCH",
    body: JSON.stringify({ reports_parent_page_id }),
  });
}

export interface NotionPage {
  id: string;
  title: string;
}

export function listNotionSharedPages() {
  return request<NotionPage[]>("/integrations/notion/shared-pages");
}

// --- Employees ---

export interface Employee {
  id: string;
  full_name: string;
  company_email: string;
  department: string | null;
  manager_id: string | null;
  status: "active" | "departing" | "offboarded";
}

export interface AccessGrant {
  id: string;
  system: SystemType;
  grant_type: string;
  external_id: string;
  resource_name: string | null;
  role: string | null;
  status: "active" | "revoked" | "revoke_failed";
  last_synced_at: string | null;
}

export interface WorkItem {
  id: string;
  system: SystemType;
  item_type: string;
  title: string | null;
  url: string | null;
  status: "open" | "in_progress" | "blocked" | "closed";
  skill_tags: string[] | null;
}

export interface EmployeeDetail extends Employee {
  access_grants: AccessGrant[];
  work_items: WorkItem[];
}

export function listEmployees() {
  return request<Employee[]>("/employees");
}

export function getEmployee(id: string) {
  return request<EmployeeDetail>(`/employees/${id}`);
}

export interface SystemResyncResult {
  system: SystemType;
  discovered: number;
  linked: number;
  skipped: number;
}

export function resyncEmployees() {
  return request<{ results: SystemResyncResult[] }>("/employees/resync", { method: "POST" });
}

// --- Offboarding ---

export interface OffboardingRun {
  id: string;
  employee_id: string;
  environment: "sandbox" | "production";
  status: "in_progress" | "completed" | "completed_with_errors" | "failed";
  initiated_at: string;
  completed_at: string | null;
  revocation_actions: {
    id: string;
    access_grant_id: string;
    revoke_status: string;
    verify_status: string;
    error_message: string | null;
  }[];
  narrative: string | null;
  notion_report_url: string | null;
}

export function startOffboardingRun(employee_id: string, environment: "sandbox" | "production") {
  return request<OffboardingRun>("/offboarding/runs", {
    method: "POST",
    body: JSON.stringify({ employee_id, environment }),
  });
}

export function getOffboardingRun(id: string) {
  return request<OffboardingRun>(`/offboarding/runs/${id}`);
}

// --- Reassignments ---

export interface ReassignmentAction {
  id: string;
  work_item_id: string;
  suggested_owner_id: string | null;
  suggested_by: "llm" | "human";
  justification: string | null;
  confirmed_owner_id: string | null;
  reassign_status: "pending" | "success" | "failed";
  verify_status: "pending" | "verified" | "still_present" | "error";
  error_message: string | null;
}

export function listReassignments(runId: string) {
  return request<ReassignmentAction[]>(`/reassignments/${runId}`);
}

export function confirmReassignment(reassignmentId: string, confirmed_owner_id: string) {
  return request<ReassignmentAction>(`/reassignments/${reassignmentId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ confirmed_owner_id }),
  });
}
