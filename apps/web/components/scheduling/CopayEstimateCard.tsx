"use client";

import { useState } from "react";
import { Calculator, RefreshCw, AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import {
  useCopayEstimate,
  useCalculateCopay,
  useOverrideCopay,
  dollarsToCents,
  centsToDollars,
  centsToUsd,
  type CopayLineItem,
  type CopayEstimate,
} from "@/lib/api/copay";

// ── Line-item flag badges ──────────────────────────────────────────────────────

function LineFlagBadges({ item }: { item: CopayLineItem }) {
  return (
    <span className="flex flex-wrap gap-1">
      {item.notCovered && (
        <Badge variant="outline" className="text-[10px] text-destructive border-destructive/40">
          Not covered
        </Badge>
      )}
      {item.needsManualEntry && (
        <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300">
          Manual entry
        </Badge>
      )}
      {item.isFrequencyExceeded && (
        <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300">
          Freq. exceeded
        </Badge>
      )}
      {item.isInWaitingPeriod && (
        <Badge variant="outline" className="text-[10px] text-amber-600 border-amber-300">
          Waiting period
        </Badge>
      )}
      {item.annualMaxCapApplied && (
        <Badge variant="secondary" className="text-[10px]">
          Max cap
        </Badge>
      )}
    </span>
  );
}

// ── Manual override editor ─────────────────────────────────────────────────────

function OverrideEditor({
  estimate,
  appointmentId,
}: {
  estimate: CopayEstimate;
  appointmentId: string;
}) {
  const [overrideDollars, setOverrideDollars] = useState(
    centsToDollars(estimate.overridePatientCents),
  );
  const [overrideNote, setOverrideNote] = useState(estimate.overrideNote ?? "");
  const [saveError, setSaveError] = useState<string | null>(null);
  const overrideMutation = useOverrideCopay(appointmentId);

  function handleSave() {
    setSaveError(null);
    let cents: number | null = null;
    if (overrideDollars.trim()) {
      cents = dollarsToCents(overrideDollars);
      if (cents === null) {
        setSaveError("Enter a valid dollar amount, or leave blank to clear.");
        return;
      }
    }
    const note = overrideNote.trim();
    overrideMutation.mutate(
      { overridePatientCents: cents, ...(note ? { overrideNote: note } : {}) },
      { onError: () => setSaveError("Failed to save override. Please try again.") },
    );
  }

  function handleClear() {
    setSaveError(null);
    setOverrideDollars("");
    setOverrideNote("");
    overrideMutation.mutate(
      { overridePatientCents: null },
      { onError: () => setSaveError("Failed to clear override. Please try again.") },
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <p className="text-xs font-medium">Manual override</p>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Patient owes ($)</Label>
          <Input
            className="h-8 text-sm"
            type="number"
            min="0"
            step="0.01"
            placeholder="Leave blank to clear"
            value={overrideDollars}
            onChange={(e) => setOverrideDollars(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Note (optional)</Label>
          <Input
            className="h-8 text-sm"
            placeholder="Reason for override"
            value={overrideNote}
            onChange={(e) => setOverrideNote(e.target.value)}
          />
        </div>
      </div>
      {saveError && <p className="text-xs text-destructive">{saveError}</p>}
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={handleSave}
          disabled={overrideMutation.isPending}
          className="h-7 text-xs"
        >
          {overrideMutation.isPending ? "Saving…" : "Save override"}
        </Button>
        {estimate.overridePatientCents !== null && (
          <Button
            size="sm"
            variant="ghost"
            onClick={handleClear}
            disabled={overrideMutation.isPending}
            className="h-7 text-xs"
          >
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Main card ──────────────────────────────────────────────────────────────────

export function CopayEstimateCard({ appointmentId }: { appointmentId: string }) {
  const { data: estimate, isLoading } = useCopayEstimate(appointmentId);
  const calculateMutation = useCalculateCopay(appointmentId);
  const [calcError, setCalcError] = useState<string | null>(null);

  function handleCalculate() {
    setCalcError(null);
    calculateMutation.mutate(undefined, {
      onError: (err) => {
        if (err instanceof ApiError && err.status === 422) {
          const body = err.body as { error?: { code?: string } };
          if (body?.error?.code === "NO_PROCEDURES") {
            setCalcError("Add procedures first before calculating an estimate.");
            return;
          }
        }
        if (err instanceof ApiError && err.status === 403) {
          setCalcError("Co-pay estimation isn't enabled for this practice.");
          return;
        }
        setCalcError("Failed to calculate estimate. Please try again.");
      },
    });
  }

  const effectivePatientOwes =
    estimate?.overridePatientCents != null
      ? estimate.overridePatientCents
      : estimate?.totalPatientOwesCents;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Calculator className="h-4 w-4" />
          Co-pay Estimate
        </CardTitle>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 gap-1 text-xs"
          disabled={calculateMutation.isPending || isLoading}
          onClick={handleCalculate}
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${calculateMutation.isPending ? "animate-spin" : ""}`}
          />
          {estimate ? "Recalculate" : "Calculate estimate"}
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

        {calcError && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {calcError}
          </div>
        )}

        {!isLoading && !estimate && !calcError && (
          <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            No estimate yet. Click &ldquo;Calculate estimate&rdquo; to run the co-pay engine.
          </p>
        )}

        {estimate && (
          <>
            {/* Per-procedure breakdown */}
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                    <th className="px-3 py-2">Code</th>
                    <th className="px-3 py-2 text-right">Fee</th>
                    <th className="px-3 py-2 text-right">Write-off</th>
                    <th className="px-3 py-2 text-right">Insurance</th>
                    <th className="px-3 py-2 text-right">Patient</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {estimate.lineItems.length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-3 py-3 text-center text-xs text-muted-foreground"
                      >
                        No line items
                      </td>
                    </tr>
                  )}
                  {estimate.lineItems.map((item) => (
                    <tr
                      key={item.procedureId}
                      className="border-b border-border last:border-0"
                    >
                      <td className="px-3 py-2 font-mono text-xs">{item.cdtCode}</td>
                      <td className="px-3 py-2 text-right">{centsToUsd(item.providerFeeCents)}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">
                        {centsToUsd(item.writeOffCents)}
                      </td>
                      <td className="px-3 py-2 text-right">{centsToUsd(item.insuranceOwesCents)}</td>
                      <td className="px-3 py-2 text-right font-medium">
                        {centsToUsd(item.patientOwesCents)}
                      </td>
                      <td className="px-3 py-2">
                        <LineFlagBadges item={item} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Visit totals */}
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs">
              <span className="text-muted-foreground">Provider fee</span>
              <span className="text-right">{centsToUsd(estimate.totalProviderFeeCents)}</span>
              <span className="text-muted-foreground">Write-off</span>
              <span className="text-right">{centsToUsd(estimate.totalWriteOffCents)}</span>
              <span className="text-muted-foreground">Insurance owes</span>
              <span className="text-right">{centsToUsd(estimate.totalInsuranceOwesCents)}</span>
              <span className="font-medium">Patient owes</span>
              <span className="text-right font-medium">
                {centsToUsd(effectivePatientOwes)}
                {estimate.overridePatientCents !== null && (
                  <Badge variant="secondary" className="ml-1 text-[10px]">
                    Override
                  </Badge>
                )}
              </span>
              {estimate.deductibleRemainingAfterCents !== null && (
                <>
                  <span className="text-muted-foreground">Deductible remaining after</span>
                  <span className="text-right">
                    {centsToUsd(estimate.deductibleRemainingAfterCents)}
                  </span>
                </>
              )}
              {estimate.annualMaxRemainingAfterCents !== null && (
                <>
                  <span className="text-muted-foreground">Annual max remaining after</span>
                  <span className="text-right">
                    {centsToUsd(estimate.annualMaxRemainingAfterCents)}
                  </span>
                </>
              )}
            </div>

            {/* Secondary insurance note */}
            {estimate.hasSecondaryInsurance && (
              <p className="text-xs text-muted-foreground">
                Secondary insurance: submit manually after primary EOB.
              </p>
            )}

            {/* Manual override editor. The key forces a remount (re-seeding the
                local input state) whenever a recalculation changes the override. */}
            <OverrideEditor
              key={`${estimate.id}:${estimate.overridePatientCents ?? "none"}`}
              estimate={estimate}
              appointmentId={appointmentId}
            />

            {/* Required caveat */}
            <p className="text-[10px] text-muted-foreground">
              Estimate, not a guarantee of payment.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
