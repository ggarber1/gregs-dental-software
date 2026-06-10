"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useAppointmentProcedures,
  useCdtCodeSearch,
  useCreateAppointmentProcedure,
  useDeleteAppointmentProcedure,
  formatCents,
  prefillFeeDollars,
  type CdtCode,
  type CreateAppointmentProcedureBody,
  type EstimateSource,
} from "@/lib/api/procedures";

interface ProceduresSectionProps {
  appointmentId: string;
}

interface DraftProcedure {
  procedureCode: string;
  procedureName: string;
  toothNumber: string;
  surface: string;
  fee: string;
  insuranceEst: string;
  patientEst: string;
  estimateSource: EstimateSource | "";
  notes: string;
}

const EMPTY_DRAFT: DraftProcedure = {
  procedureCode: "",
  procedureName: "",
  toothNumber: "",
  surface: "",
  fee: "",
  insuranceEst: "",
  patientEst: "",
  estimateSource: "",
  notes: "",
};

const ESTIMATE_SOURCE_OPTIONS: { value: EstimateSource; label: string }[] = [
  { value: "manual", label: "Manual" },
  { value: "eligibility", label: "Eligibility" },
  { value: "prior_eob", label: "Prior EOB" },
];

function dollarsToCents(value: string): number {
  return Math.round(parseFloat(value) * 100);
}

export function ProceduresSection({ appointmentId }: ProceduresSectionProps) {
  const { data, isLoading } = useAppointmentProcedures(appointmentId);
  const createProcedure = useCreateAppointmentProcedure(appointmentId);
  const deleteProcedure = useDeleteAppointmentProcedure(appointmentId);

  const [draft, setDraft] = useState<DraftProcedure>(EMPTY_DRAFT);
  const [codeQuery, setCodeQuery] = useState("");
  const [showCodeDropdown, setShowCodeDropdown] = useState(false);
  const { data: codeResults } = useCdtCodeSearch(codeQuery);

  const items = data?.items ?? [];
  const totals = data?.totals;

  function setField<K extends keyof DraftProcedure>(field: K, value: DraftProcedure[K]) {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }

  function handleCodeChange(value: string) {
    setField("procedureCode", value);
    setCodeQuery(value);
    setShowCodeDropdown(true);
  }

  function selectCdtCode(code: CdtCode) {
    setDraft((prev) => ({
      ...prev,
      procedureCode: code.code,
      procedureName: code.description,
      fee: prefillFeeDollars(prev.fee, code.resolvedFeeCents),
    }));
    setShowCodeDropdown(false);
  }

  // Both procedureCode and procedureName are required for a valid submit — this
  // guarantees the backend's "cdtCodeId OR procedureCode" invariant holds.
  const canSubmit =
    Boolean(draft.procedureCode.trim()) &&
    Boolean(draft.procedureName.trim()) &&
    Boolean(draft.fee.trim()) &&
    !createProcedure.isPending;

  async function handleAdd() {
    if (!canSubmit) return;
    const body: CreateAppointmentProcedureBody = {
      procedureCode: draft.procedureCode.trim(),
      procedureName: draft.procedureName.trim(),
      feeCents: dollarsToCents(draft.fee),
    };
    if (draft.toothNumber.trim()) body.toothNumber = draft.toothNumber.trim();
    if (draft.surface.trim()) body.surface = draft.surface.trim();
    if (draft.insuranceEst.trim()) body.insuranceEstCents = dollarsToCents(draft.insuranceEst);
    if (draft.patientEst.trim()) body.patientEstCents = dollarsToCents(draft.patientEst);
    if (draft.estimateSource) body.estimateSource = draft.estimateSource;
    if (draft.notes.trim()) body.notes = draft.notes.trim();

    await createProcedure.mutateAsync(body);
    setDraft(EMPTY_DRAFT);
    setCodeQuery("");
  }

  return (
    <div className="space-y-3">
      {/* Procedures table */}
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Procedure</th>
              <th className="px-3 py-2">Tooth/Surface</th>
              <th className="px-3 py-2 text-right">Fee</th>
              <th className="px-3 py-2 text-right">Ins. est.</th>
              <th className="px-3 py-2 text-right">Pt. est.</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-center text-muted-foreground">
                  No procedures recorded
                </td>
              </tr>
            )}
            {items.map((proc) => {
              const toothSurface = [proc.toothNumber, proc.surface]
                .filter(Boolean)
                .join(" / ");
              return (
                <tr key={proc.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-mono text-xs">{proc.procedureCode ?? "—"}</td>
                  <td className="px-3 py-2">{proc.procedureName}</td>
                  <td className="px-3 py-2 text-muted-foreground">{toothSurface || "—"}</td>
                  <td className="px-3 py-2 text-right">{formatCents(proc.feeCents)}</td>
                  <td className="px-3 py-2 text-right text-muted-foreground">
                    {proc.insuranceEstCents != null ? formatCents(proc.insuranceEstCents) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right text-muted-foreground">
                    {proc.patientEstCents != null ? formatCents(proc.patientEstCents) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => deleteProcedure.mutate(proc.id)}
                      disabled={deleteProcedure.isPending}
                      aria-label={`Remove ${proc.procedureName}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Totals strip */}
      {totals && (
        <p className="text-xs text-muted-foreground">
          Fee total: {formatCents(totals.feeCentsTotal)} · Insurance est:{" "}
          {formatCents(totals.insuranceEstCentsTotal)} · Patient est:{" "}
          {formatCents(totals.patientEstCentsTotal)}
        </p>
      )}

      {/* Add procedure form */}
      <div className="rounded-md border border-border p-3">
        <p className="mb-2 text-sm font-medium">Add procedure</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="relative space-y-1">
            <Label className="text-xs">CDT code *</Label>
            <Input
              className="h-8 text-sm"
              placeholder="D2391"
              value={draft.procedureCode}
              onChange={(e) => handleCodeChange(e.target.value)}
              onFocus={() => draft.procedureCode && setShowCodeDropdown(true)}
              onBlur={() => setTimeout(() => setShowCodeDropdown(false), 150)}
              autoComplete="off"
            />
            {showCodeDropdown && (codeResults?.length ?? 0) > 0 && (
              <div className="absolute z-50 mt-1 max-h-48 w-72 overflow-auto rounded-md border bg-popover p-1 shadow-md">
                {codeResults!.map((code) => (
                  <button
                    key={code.id}
                    type="button"
                    className="flex w-full flex-col items-start gap-0.5 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                    onClick={() => selectCdtCode(code)}
                  >
                    <span className="font-mono text-xs font-medium">{code.code}</span>
                    <span className="text-muted-foreground">{code.description}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="col-span-2 space-y-1 sm:col-span-3">
            <Label className="text-xs">Procedure name *</Label>
            <Input
              className="h-8 text-sm"
              placeholder="Resin composite, 1 surface"
              value={draft.procedureName}
              onChange={(e) => setField("procedureName", e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Tooth #</Label>
            <Input
              className="h-8 text-sm"
              placeholder="14"
              value={draft.toothNumber}
              onChange={(e) => setField("toothNumber", e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Surface</Label>
            <Input
              className="h-8 text-sm"
              placeholder="MOD"
              value={draft.surface}
              onChange={(e) => setField("surface", e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Fee ($) *</Label>
            <Input
              className="h-8 text-sm"
              type="number"
              min="0"
              step="0.01"
              placeholder="250.00"
              value={draft.fee}
              onChange={(e) => setField("fee", e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Ins. est. ($)</Label>
            <Input
              className="h-8 text-sm"
              type="number"
              min="0"
              step="0.01"
              placeholder="150.00"
              value={draft.insuranceEst}
              onChange={(e) => setField("insuranceEst", e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Pt. est. ($)</Label>
            <Input
              className="h-8 text-sm"
              type="number"
              min="0"
              step="0.01"
              placeholder="100.00"
              value={draft.patientEst}
              onChange={(e) => setField("patientEst", e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Estimate source</Label>
            <Select
              value={draft.estimateSource}
              onValueChange={(v) => setField("estimateSource", v as EstimateSource)}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue placeholder="Optional" />
              </SelectTrigger>
              <SelectContent>
                {ESTIMATE_SOURCE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2 space-y-1 sm:col-span-4">
            <Label className="text-xs">Notes</Label>
            <Textarea
              className="text-sm"
              rows={2}
              placeholder="Optional notes…"
              value={draft.notes}
              onChange={(e) => setField("notes", e.target.value)}
            />
          </div>
        </div>
        <div className="mt-2">
          <Button size="sm" onClick={() => void handleAdd()} disabled={!canSubmit}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {createProcedure.isPending ? "Adding…" : "Add procedure"}
          </Button>
        </div>
      </div>
    </div>
  );
}
