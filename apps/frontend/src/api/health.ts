export type HealthStatus = "alive" | "ready" | "degraded" | "not_ready";
export type ComponentStatus =
  "ready" | "degraded" | "not_configured" | "unavailable";

export interface ServiceHealth {
  schema_version: "1.0";
  service: string;
  version: string;
  status: HealthStatus;
  components: Record<string, ComponentStatus>;
  error_code?: string;
}

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) return configured;
  return import.meta.env.PROD ? "/api" : "http://localhost:8000";
}

export async function getLiveness(
  signal?: AbortSignal,
): Promise<ServiceHealth> {
  const response = await fetch(`${getApiBaseUrl()}/health/live`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error("Backend health request failed");
  }

  return (await response.json()) as ServiceHealth;
}
