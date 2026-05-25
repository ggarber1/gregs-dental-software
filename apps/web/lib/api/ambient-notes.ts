import { getAccessToken, getPracticeId } from "@/lib/auth/cookies";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AmbientNoteDraftResponse {
  draft: string;
  detectedTemplate: string | null;
}

export async function fetchAmbientNoteDraft(
  patientId: string,
  audio: Blob,
  templateHint?: string,
): Promise<AmbientNoteDraftResponse> {
  const form = new FormData();
  form.append("audio", audio, "audio.webm");

  const qs = templateHint
    ? `?template_hint=${encodeURIComponent(templateHint)}`
    : "";
  const url = `${API_BASE_URL}/api/v1/patients/${patientId}/ambient-note-draft${qs}`;

  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const practiceId = getPracticeId();
  if (practiceId) headers["X-Practice-ID"] = practiceId;

  // Do not set Content-Type — the browser sets it automatically with the
  // multipart boundary when body is a FormData instance.
  const res = await fetch(url, { method: "POST", headers, body: form });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Ambient note draft failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<AmbientNoteDraftResponse>;
}
