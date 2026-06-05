"use client";

import { usePatientProcedures, formatCents } from "@/lib/api/procedures";

interface ProcedureHistoryTabProps {
  patientId: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function ProcedureHistoryTab({ patientId }: ProcedureHistoryTabProps) {
  const { data, isLoading } = usePatientProcedures(patientId);

  const items = data?.items ?? [];

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <h2 className="text-base font-semibold">Procedures</h2>

      {isLoading && (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No procedures recorded.
        </p>
      )}

      {!isLoading && items.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Procedure</th>
                <th className="px-3 py-2">Tooth/Surface</th>
                <th className="px-3 py-2 text-right">Fee</th>
                <th className="px-3 py-2 text-right">Patient est.</th>
              </tr>
            </thead>
            <tbody>
              {items.map((proc) => {
                const toothSurface = [proc.toothNumber, proc.surface]
                  .filter(Boolean)
                  .join(" / ");
                return (
                  <tr key={proc.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 text-muted-foreground">
                      {formatDate(proc.createdAt)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{proc.procedureCode ?? "—"}</td>
                    <td className="px-3 py-2">{proc.procedureName}</td>
                    <td className="px-3 py-2 text-muted-foreground">{toothSurface || "—"}</td>
                    <td className="px-3 py-2 text-right">{formatCents(proc.feeCents)}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">
                      {proc.patientEstCents != null ? formatCents(proc.patientEstCents) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
