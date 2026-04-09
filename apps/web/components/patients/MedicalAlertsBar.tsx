import { AlertTriangle } from "lucide-react";

interface Props {
  allergies: string[];
  medicalAlerts: string[];
}

export function MedicalAlertsBar({ allergies, medicalAlerts }: Props) {
  if (allergies.length === 0 && medicalAlerts.length === 0) return null;

  const hasAllergies = allergies.length > 0;

  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-4 py-3 text-sm font-medium ${
        hasAllergies
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-yellow-400/40 bg-yellow-50 text-yellow-800"
      }`}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        {hasAllergies && (
          <span>
            <span className="uppercase tracking-wide">Allergies:</span>{" "}
            {allergies.join(", ")}
          </span>
        )}
        {medicalAlerts.length > 0 && (
          <span>
            <span className="uppercase tracking-wide">Alerts:</span>{" "}
            {medicalAlerts.join(", ")}
          </span>
        )}
      </div>
    </div>
  );
}
