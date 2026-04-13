import { AlertTriangle, Pill, Stethoscope } from "lucide-react";

interface Props {
  allergies: string[];
  medicalAlerts: string[];
  medications: string[];
}

export function MedicalAlertsBar({ allergies, medicalAlerts, medications }: Props) {
  if (allergies.length === 0 && medicalAlerts.length === 0 && medications.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-2">
      {allergies.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm font-medium text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <span className="uppercase tracking-wide">Allergies:</span>{" "}
            {allergies.join(", ")}
          </span>
        </div>
      )}
      {medicalAlerts.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-yellow-400/40 bg-yellow-50 px-4 py-2 text-sm font-medium text-yellow-800">
          <Stethoscope className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <span className="uppercase tracking-wide">Conditions:</span>{" "}
            {medicalAlerts.join(", ")}
          </span>
        </div>
      )}
      {medications.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-blue-300/40 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-800">
          <Pill className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <span className="uppercase tracking-wide">Medications:</span>{" "}
            {medications.join(", ")}
          </span>
        </div>
      )}
    </div>
  );
}
