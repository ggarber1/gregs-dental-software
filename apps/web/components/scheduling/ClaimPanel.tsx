"use client";

import { AlertTriangle, Send, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  PROBLEM_STATUSES,
  useAppointmentClaims,
  useResubmitClaim,
  useSubmitClaim,
  useWriteOffClaim,
  type Claim,
} from "@/lib/api/claims";
import { formatDenialReason } from "@/lib/carc-codes";
import { formatSubmissionError } from "@/lib/submission-error-hints";

function centsToUsd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusVariant(
  status: Claim["status"],
): "default" | "secondary" | "destructive" {
  if (
    status === "submitted" ||
    status === "paid" ||
    status === "acknowledged"
  )
    return "default";
  if (
    status === "clearinghouse_rejected" ||
    status === "submission_failed" ||
    status === "denied"
  )
    return "destructive";
  return "secondary";
}

function ReasonBlock({
  claim,
  cdtCodes,
}: {
  claim: Claim;
  cdtCodes: string[];
}) {
  if (!PROBLEM_STATUSES.has(claim.status)) return null;

  let reasonText: string;
  let fixIn: string | null = null;

  if (
    (claim.status === "clearinghouse_rejected" ||
      claim.status === "submission_failed") &&
    claim.submissionErrors &&
    claim.submissionErrors.length > 0
  ) {
    const parsed = formatSubmissionError(claim.submissionErrors[0]!);
    reasonText = parsed.plain;
    fixIn = parsed.fixIn;
  } else if (claim.denialCodes && claim.denialCodes.length > 0) {
    reasonText = formatDenialReason(claim.denialCodes, "Your carrier", cdtCodes);
  } else {
    reasonText = "Denied by carrier — check with carrier for details.";
  }

  const priorAttempts = claim.submissionHistory?.length ?? 0;

  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="space-y-1">
          <p className="font-medium text-destructive">
            {claim.status === "appealing"
              ? "Flagged for appeal"
              : "Action required"}
          </p>
          <p className="text-muted-foreground">{reasonText}</p>
          {fixIn && (
            <p className="text-xs text-muted-foreground">
              Fix in:{" "}
              <span className="font-medium text-foreground">{fixIn}</span>
            </p>
          )}
          {priorAttempts > 0 && (
            <p className="text-xs text-muted-foreground">
              Prior attempts: {priorAttempts}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ActionButtons({
  claim,
  appointmentId,
}: {
  claim: Claim;
  appointmentId: string;
}) {
  const resubmit = useResubmitClaim(claim.id, appointmentId, claim.patientId);
  const writeOff = useWriteOffClaim(claim.id, appointmentId, claim.patientId);
  const canResubmit = PROBLEM_STATUSES.has(claim.status) && !claim.insuranceReviewedAt;
  const canWriteOff =
    (claim.status === "denied" || claim.status === "appealing") &&
    !claim.insuranceReviewedAt;

  if (!canResubmit && !canWriteOff) return null;

  return (
    <div className="flex gap-2 pt-1">
      {canResubmit && (
        <Button
          size="sm"
          disabled={resubmit.isPending}
          onClick={() => resubmit.mutate()}
          title="Fix the issue shown above, then click Resubmit"
        >
          <Send className="mr-1 h-3 w-3" />
          {resubmit.isPending ? "Resubmitting…" : "Resubmit"}
        </Button>
      )}
      {canWriteOff && (
        <Button
          size="sm"
          variant="outline"
          disabled={writeOff.isPending}
          onClick={() => writeOff.mutate(undefined)}
          title="Write off remaining balance and close this claim"
        >
          <XCircle className="mr-1 h-3 w-3" />
          {writeOff.isPending ? "Writing off…" : "Write off"}
        </Button>
      )}
    </div>
  );
}

export function ClaimPanel({
  appointmentId,
  cdtCodes = [],
}: {
  appointmentId: string;
  cdtCodes?: string[];
}) {
  const { data: claims = [], isLoading } = useAppointmentClaims(appointmentId);
  const submit = useSubmitClaim(appointmentId);
  const latest = claims[0];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Insurance Claim</CardTitle>
        {!latest && (
          <Button
            size="sm"
            disabled={submit.isPending}
            onClick={() => submit.mutate()}
          >
            <Send className="mr-2 h-4 w-4" />
            Submit Claim
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {!isLoading && !latest && (
          <p className="text-muted-foreground">
            No claim submitted yet. Submitting bills this appointment&apos;s
            procedures to the patient&apos;s primary insurance.
          </p>
        )}
        {latest && (
          <div className="space-y-3">
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Status</span>
                <div className="flex items-center gap-2">
                  <Badge variant={statusVariant(latest.status)}>
                    {latest.status.replace(/_/g, " ")}
                  </Badge>
                  {latest.submissionAttempt > 1 && (
                    <span className="text-xs text-muted-foreground">
                      Attempt {latest.submissionAttempt}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Total charge</span>
                <span>{centsToUsd(latest.totalChargeCents)}</span>
              </div>
              {(latest.status === "paid" ||
                latest.status === "partially_paid" ||
                latest.status === "denied") && (
                <div className="space-y-1 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">
                      Insurance paid
                    </span>
                    <span>{centsToUsd(latest.insurancePaidCents ?? 0)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">
                      Patient responsibility
                    </span>
                    <span>
                      {centsToUsd(latest.patientResponsibilityCents ?? 0)}
                    </span>
                  </div>
                </div>
              )}
            </div>

            <ReasonBlock claim={latest} cdtCodes={cdtCodes} />
            <ActionButtons claim={latest} appointmentId={appointmentId} />
          </div>
        )}
        {submit.isError && (
          <p className="text-destructive">
            Submission failed. Check that the practice NPI, tax ID, taxonomy,
            and clearinghouse credentials are configured, and that the
            appointment has procedures.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
