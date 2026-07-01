"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  centsToUsd,
  useAcceptUnderpayment,
  useFlagForAppeal,
  useInsuranceARSummary,
  useInsuranceARWorklist,
  type ARCategory,
} from "@/lib/api/reports";
import { useResubmitClaim, useWriteOffClaim } from "@/lib/api/claims";

function ProblemRowActions({
  claimId,
  appointmentId,
  patientId,
  status,
}: {
  claimId: string;
  appointmentId: string;
  patientId: string;
  status: string;
}) {
  const resubmit = useResubmitClaim(claimId, appointmentId, patientId);
  const writeOff = useWriteOffClaim(claimId, appointmentId, patientId);
  const canWriteOff = status === "denied" || status === "appealing";

  return (
    <div className="flex gap-2">
      <button
        type="button"
        title="Correct the issue shown, then resubmit to send a new claim to the carrier"
        onClick={() => resubmit.mutate()}
        disabled={resubmit.isPending}
        className="text-sm text-primary underline disabled:opacity-50"
      >
        {resubmit.isPending ? "Resubmitting…" : "Resubmit"}
      </button>
      {canWriteOff && (
        <button
          type="button"
          onClick={() => writeOff.mutate(undefined)}
          disabled={writeOff.isPending}
          className="ml-1 text-sm text-muted-foreground underline disabled:opacity-50"
        >
          {writeOff.isPending ? "Writing off…" : "Write off"}
        </button>
      )}
    </div>
  );
}

const CATEGORIES: { key: ARCategory; label: string }[] = [
  { key: "awaiting", label: "Awaiting carrier" },
  { key: "underpaid", label: "Underpaid" },
  { key: "problem", label: "Problem" },
  { key: "appealing", label: "Appealing" },
];

export default function InsuranceARPage() {
  const [category, setCategory] = useState<ARCategory>("awaiting");
  const { data: rows, isLoading } = useInsuranceARWorklist(category);
  const { data: summary } = useInsuranceARSummary();
  const accept = useAcceptUnderpayment();
  const appeal = useFlagForAppeal();
  const list = rows ?? [];

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="Insurance A/R"
        description="Outstanding insurance claims that need attention — chase, accept, or appeal."
      />

      {summary && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Carrier</TableHead>
                <TableHead className="text-right">0–30</TableHead>
                <TableHead className="text-right">31–60</TableHead>
                <TableHead className="text-right">61–90</TableHead>
                <TableHead className="text-right">90+</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Expected</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.carriers.map((c) => (
                <TableRow key={c.payerId}>
                  <TableCell>{c.carrierName}</TableCell>
                  <TableCell className="text-right">{centsToUsd(c.buckets.b0_30)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(c.buckets.b31_60)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(c.buckets.b61_90)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(c.buckets.b90_plus)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(c.totalBilledCents)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(c.expectedCents)}</TableCell>
                </TableRow>
              ))}
              <TableRow className="font-medium">
                <TableCell>TOTAL</TableCell>
                <TableCell className="text-right">{centsToUsd(summary.totals.buckets.b0_30)}</TableCell>
                <TableCell className="text-right">{centsToUsd(summary.totals.buckets.b31_60)}</TableCell>
                <TableCell className="text-right">{centsToUsd(summary.totals.buckets.b61_90)}</TableCell>
                <TableCell className="text-right">{centsToUsd(summary.totals.buckets.b90_plus)}</TableCell>
                <TableCell className="text-right">{centsToUsd(summary.totals.totalBilledCents)}</TableCell>
                <TableCell className="text-right">{centsToUsd(summary.totals.expectedCents)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}

      <div className="flex gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => setCategory(c.key)}
            className={
              "rounded-md px-3 py-1.5 text-sm " +
              (category === c.key
                ? "bg-primary text-primary-foreground"
                : "border border-input bg-background")
            }
          >
            {c.label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {!isLoading && list.length === 0 && (
        <div className="rounded-lg border border-border py-16 text-center">
          <p className="text-sm text-muted-foreground">Nothing here.</p>
        </div>
      )}

      {!isLoading && list.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Claim #</TableHead>
                <TableHead>Patient</TableHead>
                <TableHead>Carrier</TableHead>
                <TableHead className="text-right">Billed</TableHead>
                <TableHead className="text-right">Est. ins.</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead className="text-right">Days</TableHead>
                <TableHead>Status</TableHead>
                {category === "underpaid" && <TableHead>Actions</TableHead>}
                {(category === "problem" || category === "appealing") && (
                  <TableHead>Actions</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((r) => (
                <TableRow key={r.claimId}>
                  <TableCell className="font-mono text-xs">{r.claimNumber}</TableCell>
                  <TableCell>{r.patientName}</TableCell>
                  <TableCell className="text-muted-foreground">{r.carrierName}</TableCell>
                  <TableCell className="text-right">{centsToUsd(r.billedCents)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(r.estimatedInsuranceCents)}</TableCell>
                  <TableCell className="text-right">{centsToUsd(r.insurancePaidCents)}</TableCell>
                  <TableCell className="text-right">{r.daysOut}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{r.status.replace(/_/g, " ")}</Badge>
                    {r.reason && (
                      <span className="ml-2 text-xs text-muted-foreground">{r.reason}</span>
                    )}
                    {r.category === "underpaid" && r.shortfallCents != null && (
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        est {centsToUsd(r.estimatedInsuranceCents)} · paid{" "}
                        {centsToUsd(r.insurancePaidCents)} · −
                        {centsToUsd(r.shortfallCents)}
                      </div>
                    )}
                  </TableCell>
                  {category === "underpaid" && (
                    <TableCell className="whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => accept.mutate(r.claimId)}
                        disabled={accept.isPending}
                        className="text-sm text-primary underline disabled:opacity-50"
                      >
                        Accept
                      </button>
                      <button
                        type="button"
                        title="Triage flag only — does not submit to the carrier"
                        onClick={() => appeal.mutate(r.claimId)}
                        disabled={appeal.isPending}
                        className="ml-3 text-sm text-primary underline disabled:opacity-50"
                      >
                        Flag for appeal
                      </button>
                    </TableCell>
                  )}
                  {(category === "problem" || category === "appealing") && (
                    <TableCell>
                      <ProblemRowActions
                        claimId={r.claimId}
                        appointmentId={r.appointmentId}
                        patientId={r.patientId}
                        status={r.status}
                      />
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
