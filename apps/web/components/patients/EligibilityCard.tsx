"use client";

import { ShieldCheck, AlertTriangle, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePatientInsurance } from "@/lib/api/insurance";
import {
  usePatientEligibility,
  useCreateEligibilityCheck,
  type EligibilityCheck,
} from "@/lib/api/eligibility";

const STALENESS_NOTE =
  "* As of last payer update. May not reflect claims processed in the last 1–7 days.";

export function centsToUsd(cents: number | null): string {
  if (cents === null || cents === undefined) return "—";
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export function pctToPatientShare(fraction: number | null): string {
  if (fraction === null || fraction === undefined) return "—";
  return `${Math.round(fraction * 100)}%`;
}

function statusBadge(check: EligibilityCheck) {
  switch (check.status) {
    case "verified":
      return <Badge className="text-xs">Verified</Badge>;
    case "pending":
      return <Badge variant="secondary" className="text-xs">Pending</Badge>;
    case "not_supported":
      return (
        <Badge variant="outline" className="text-xs gap-1 text-amber-600 border-amber-300">
          <AlertTriangle className="h-3 w-3" /> Not supported
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="text-xs gap-1 text-destructive border-destructive/40">
          <AlertTriangle className="h-3 w-3" /> Failed
        </Badge>
      );
  }
}

function CheckRow({ check }: { check: EligibilityCheck }) {
  const verifiedLabel = check.verifiedAt
    ? new Date(check.verifiedAt).toLocaleString()
    : new Date(check.requestedAt).toLocaleString();
  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-medium text-sm">{check.planName ?? check.payerName ?? "Coverage"}</span>
        {statusBadge(check)}
      </div>
      <p className="text-xs text-muted-foreground">Verified as of {verifiedLabel}</p>

      {check.status === "verified" && (
        <>
          <p className="text-xs text-muted-foreground capitalize">
            Coverage: {check.coverageStatus ?? "unknown"}
          </p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <span className="text-muted-foreground">Deductible (ind.)</span>
            <span>{centsToUsd(check.deductibleIndividual)}</span>
            <span className="text-muted-foreground">Annual max remaining</span>
            <span>
              {check.annualMaxIndividualRemaining !== null
                ? `~${centsToUsd(check.annualMaxIndividualRemaining)}*`
                : "—"}
            </span>
            <span className="text-muted-foreground">Preventive (patient)</span>
            <span>{pctToPatientShare(check.coinsurancePreventive)}</span>
            <span className="text-muted-foreground">Basic (patient)</span>
            <span>{pctToPatientShare(check.coinsuranceBasic)}</span>
            <span className="text-muted-foreground">Major (patient)</span>
            <span>{pctToPatientShare(check.coinsuranceMajor)}</span>
          </div>
          <p className="text-[10px] text-muted-foreground">{STALENESS_NOTE}</p>
        </>
      )}

      {(check.status === "failed" || check.status === "not_supported") && check.failureReason && (
        <p className="text-xs text-destructive">{check.failureReason}</p>
      )}
    </div>
  );
}

export function EligibilityCard({ patientId }: { patientId: string }) {
  const { data: insuranceList = [] } = usePatientInsurance(patientId);
  const { data: checks = [], isLoading } = usePatientEligibility(patientId);
  const createCheck = useCreateEligibilityCheck(patientId);

  const checksByInsurance = new Map(checks.map((c) => [c.patientInsuranceId, c]));

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <ShieldCheck className="h-4 w-4" />
          Eligibility
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

        {!isLoading && insuranceList.length === 0 && (
          <p className="text-sm text-muted-foreground">No insurance on file.</p>
        )}

        {insuranceList.map((ins) => {
          const check = checksByInsurance.get(ins.id);
          return (
            <div key={ins.id} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium">
                  {ins.carrier} <span className="text-muted-foreground">({ins.priority})</span>
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1 text-xs"
                  disabled={createCheck.isPending}
                  onClick={() => createCheck.mutate({ patientInsuranceId: ins.id })}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${createCheck.isPending ? "animate-spin" : ""}`} />
                  {check ? "Re-verify" : "Verify now"}
                </Button>
              </div>
              {check ? (
                <CheckRow check={check} />
              ) : (
                <p className="text-xs text-muted-foreground rounded-md border border-dashed p-3">
                  Not checked yet.
                </p>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
