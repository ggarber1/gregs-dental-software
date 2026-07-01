"use client";

import { RefreshCw, XCircle } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  usePatientClaims,
  useResubmitClaim,
  useWriteOffClaim,
  type Claim,
} from "@/lib/api/claims";
import { formatDenialReason } from "@/lib/carc-codes";
import { formatSubmissionError } from "@/lib/submission-error-hints";

function centsToUsd(cents: number | null): string {
  if (cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "paid") return "default";
  if (
    status === "denied" ||
    status === "clearinghouse_rejected" ||
    status === "submission_failed"
  )
    return "destructive";
  if (status === "appealing") return "secondary";
  return "outline";
}

const PROBLEM_STATUSES = new Set([
  "clearinghouse_rejected",
  "submission_failed",
  "denied",
  "appealing",
]);

function getReasonText(claim: Claim): string {
  if (
    (claim.status === "clearinghouse_rejected" ||
      claim.status === "submission_failed") &&
    claim.submissionErrors?.length
  ) {
    return formatSubmissionError(claim.submissionErrors[0]!).plain;
  }
  if (claim.denialCodes?.length) {
    return formatDenialReason(claim.denialCodes, "Carrier", []);
  }
  return "—";
}

function ClaimRow({ claim }: { claim: Claim }) {
  const resubmit = useResubmitClaim(claim.id, claim.appointmentId, claim.patientId);
  const writeOff = useWriteOffClaim(claim.id, claim.appointmentId, claim.patientId);
  const isProblem = PROBLEM_STATUSES.has(claim.status);
  const canWriteOff =
    (claim.status === "denied" || claim.status === "appealing") &&
    !claim.insuranceReviewedAt;
  const reason = getReasonText(claim);

  return (
    <TableRow>
      <TableCell className="text-xs text-muted-foreground">
        {new Date(claim.createdAt).toLocaleDateString()}
      </TableCell>
      <TableCell>
        <Link
          href={`/schedule?appointmentId=${claim.appointmentId}`}
          className="text-xs text-primary underline"
        >
          View appt
        </Link>
      </TableCell>
      <TableCell className="text-xs">{claim.payerId}</TableCell>
      <TableCell className="text-right text-xs">
        {centsToUsd(claim.totalChargeCents)}
      </TableCell>
      <TableCell className="text-right text-xs">
        {centsToUsd(claim.insurancePaidCents)}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-1">
          <Badge variant={statusVariant(claim.status)} className="text-xs">
            {claim.status.replace(/_/g, " ")}
          </Badge>
          {claim.submissionAttempt > 1 && (
            <span className="text-xs text-muted-foreground">
              ×{claim.submissionAttempt}
            </span>
          )}
        </div>
      </TableCell>
      <TableCell className="max-w-[260px] text-xs text-muted-foreground">
        {isProblem ? (
          <span title={reason}>
            {reason.length > 80 ? `${reason.slice(0, 80)}…` : reason}
          </span>
        ) : (
          "—"
        )}
      </TableCell>
      <TableCell>
        <div className="flex gap-1">
          {isProblem && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              disabled={resubmit.isPending}
              onClick={() => resubmit.mutate()}
            >
              <RefreshCw className="mr-1 h-3 w-3" />
              Resubmit
            </Button>
          )}
          {canWriteOff && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-xs"
              disabled={writeOff.isPending}
              onClick={() => writeOff.mutate(undefined)}
            >
              <XCircle className="mr-1 h-3 w-3" />
              Write off
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

export function ClaimsTab({ patientId }: { patientId: string }) {
  const { data: claims = [], isLoading } = usePatientClaims(patientId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (claims.length === 0) {
    return (
      <div className="rounded-lg border border-border py-16 text-center">
        <p className="text-sm text-muted-foreground">
          No claims on file for this patient.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Appointment</TableHead>
            <TableHead>Carrier</TableHead>
            <TableHead className="text-right">Billed</TableHead>
            <TableHead className="text-right">Ins. paid</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Reason</TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {claims.map((c) => (
            <ClaimRow key={c.id} claim={c} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
