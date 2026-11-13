// Single place for backend access. Only VITE_API_BASE_URL is exposed to the browser.
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}
