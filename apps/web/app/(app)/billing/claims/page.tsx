"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
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
import { useClaimsList, useResubmitClaim, useWriteOffClaim, type Claim } from "@/lib/api/claims";
import {
  centsToUsd,
  useInsuranceARWorklist,
  useAcceptUnderpayment,
  useReconciliationWorklist,
  useConfirmReconciliation,
  useARSummary,
  type ARCategory,
  type ReconciliationRow,
  type InsuranceARRow,
} from "@/lib/api/reports";

type Tab = "all" | ARCategory | "reconciled";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting", label: "Awaiting" },
  { key: "underpaid", label: "Underpaid" },
  { key: "problem", label: "Problem" },
  { key: "reconciled", label: "Reconciled" },
];

function statusVariant(status: Claim["status"]): "default" | "secondary" | "destructive" {
  if (status === "submitted" || status === "paid" || status === "acknowledged") return "default";
  if (
    status === "clearinghouse_rejected" ||
    status === "submission_failed" ||
    status === "denied"
  )
    return "destructive";
  return "secondary";
}

// ── All tab ──────────────────────────────────────────────────────────────────

function AllTab() {
  const { data, isLoading } = useClaimsList(undefined);
  const claims = data ?? [];

  if (isLoading) return <LoadingSpinner />;
  if (claims.length === 0) return <EmptyState message="No claims found." />;

  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>Claim #</TableHead>
          <TableHead>Payer</TableHead>
          <TableHead className="text-right">Charge</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Submitted</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {claims.map((c) => (
          <TableRow key={c.id}>
            <TableCell className="font-mono text-xs">{c.patientControlNumber}</TableCell>
            <TableCell className="text-muted-foreground">{c.payerId}</TableCell>
            <TableCell className="text-right">{centsToUsd(c.totalChargeCents)}</TableCell>
            <TableCell>
              <Badge variant={statusVariant(c.status)}>{c.status.replace(/_/g, " ")}</Badge>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {c.submittedAt ? c.submittedAt.slice(0, 10) : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </TableShell>
  );
}

// ── Insurance A/R tabs (Awaiting / Underpaid / Problem / Appealing) ──────────

function ARTab({ category }: { category: ARCategory }) {
  const { data: rows, isLoading } = useInsuranceARWorklist(category);
  const writeOff = useAcceptUnderpayment();
  const list = rows ?? [];

  if (isLoading) return <LoadingSpinner />;
  if (list.length === 0)
    return <EmptyState message={`No ${category.replace("_", " ")} claims.`} />;

  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>Claim #</TableHead>
          <TableHead>Patient</TableHead>
          <TableHead>Carrier</TableHead>
          <TableHead className="text-right">Billed</TableHead>
          <TableHead className="text-right">Est. ins.</TableHead>
          <TableHead className="text-right">Paid</TableHead>
          <TableHead>Days</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {list.map((r) => (
          <ARRow
            key={r.claimId}
            row={r}
            onWriteOff={() => writeOff.mutate(r.claimId)}
            writingOff={writeOff.isPending}
          />
        ))}
      </TableBody>
    </TableShell>
  );
}

function ARRow({
  row,
  onWriteOff,
  writingOff,
}: {
  row: InsuranceARRow;
  onWriteOff: () => void;
  writingOff: boolean;
}) {
  const resubmit = useResubmitClaim(row.claimId, row.appointmentId, row.patientId);
  const writeOffClaim = useWriteOffClaim(row.claimId, row.appointmentId, row.patientId);
  const [confirmingResubmit, setConfirmingResubmit] = useState(false);

  function handleResubmitConfirmed() {
    setConfirmingResubmit(false);
    resubmit.mutate();
  }

  return (
    <TableRow>
      <TableCell className="font-mono text-xs">{row.claimNumber}</TableCell>
      <TableCell>{row.patientName}</TableCell>
      <TableCell className="text-muted-foreground">{row.carrierName}</TableCell>
      <TableCell className="text-right">{centsToUsd(row.billedCents)}</TableCell>
      <TableCell className="text-right">{centsToUsd(row.estimatedInsuranceCents)}</TableCell>
      <TableCell className="text-right">{centsToUsd(row.insurancePaidCents)}</TableCell>
      <TableCell className="text-muted-foreground">{row.daysOut}d</TableCell>
      <TableCell>
        {row.category === "underpaid" && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setConfirmingResubmit(true)}
              disabled={resubmit.isPending}
              className="text-sm text-primary underline disabled:opacity-50"
            >
              Resubmit
            </button>
            <button
              type="button"
              onClick={onWriteOff}
              disabled={writingOff}
              className="text-sm text-muted-foreground underline disabled:opacity-50"
            >
              {writingOff ? "Writing off…" : "Write off"}
            </button>
          </div>
        )}
        {row.category === "problem" && row.status !== "appealing" && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setConfirmingResubmit(true)}
              disabled={resubmit.isPending}
              className="text-sm text-primary underline disabled:opacity-50"
            >
              Resubmit
            </button>
            <button
              type="button"
              onClick={() => writeOffClaim.mutate(undefined)}
              disabled={writeOffClaim.isPending}
              className="text-sm text-muted-foreground underline disabled:opacity-50"
            >
              {writeOffClaim.isPending ? "Writing off…" : "Write off"}
            </button>
          </div>
        )}
        {confirmingResubmit && (
          <div className="mt-1 rounded border border-amber-200 bg-amber-50 p-2 text-xs">
            <p className="mb-1.5 text-amber-800">
              Fix the issue in the patient or insurance record first, then confirm.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleResubmitConfirmed}
                disabled={resubmit.isPending}
                className="font-medium text-primary underline disabled:opacity-50"
              >
                {resubmit.isPending ? "Resubmitting…" : "Confirm resubmit"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmingResubmit(false)}
                className="text-muted-foreground underline"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        {row.reason && (
          <p className="mt-1 text-xs text-muted-foreground">{row.reason}</p>
        )}
      </TableCell>
    </TableRow>
  );
}

// ── Reconciled tab ────────────────────────────────────────────────────────────

function ReconciledTab({ mode }: { mode: "auto" | "confirm" }) {
  const { data: unconfirmed, isLoading: loadingUnconfirmed } = useReconciliationWorklist(
    mode === "confirm" ? false : undefined
  );
  const { data: confirmed, isLoading: loadingConfirmed } = useReconciliationWorklist(
    mode === "confirm" ? true : undefined
  );
  const confirm = useConfirmReconciliation();

  const pending = unconfirmed ?? [];
  const history = confirmed ?? [];
  const allRows = mode === "auto" ? (unconfirmed ?? []) : undefined;

  if (loadingUnconfirmed || loadingConfirmed) return <LoadingSpinner />;

  if (mode === "auto") {
    if ((allRows ?? []).length === 0)
      return <EmptyState message="No ERA settlements to review." />;
    return (
      <ReconTable
        rows={allRows ?? []}
        showConfirm={false}
        onConfirm={() => {}}
        confirming={false}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {pending.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium">Needs review</h3>
          <ReconTable
            rows={pending}
            showConfirm
            onConfirm={(id) => confirm.mutate(id)}
            confirming={confirm.isPending}
          />
        </div>
      )}
      {history.length > 0 && (
        <div>
          {pending.length > 0 && (
            <div className="my-4 border-t border-border" />
          )}
          <h3 className="mb-2 text-sm font-medium text-muted-foreground">Recent</h3>
          <ReconTable
            rows={history}
            showConfirm={false}
            onConfirm={() => {}}
            confirming={false}
          />
        </div>
      )}
      {pending.length === 0 && history.length === 0 && (
        <EmptyState message="No ERA settlements to review." />
      )}
    </div>
  );
}

function ReconTable({
  rows,
  showConfirm,
  onConfirm,
  confirming,
}: {
  rows: ReconciliationRow[];
  showConfirm: boolean;
  onConfirm: (claimId: string) => void;
  confirming: boolean;
}) {
  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>Claim #</TableHead>
          <TableHead>Patient</TableHead>
          <TableHead>Carrier</TableHead>
          <TableHead className="text-right">Billed</TableHead>
          <TableHead className="text-right">Est. ins.</TableHead>
          <TableHead className="text-right">Paid</TableHead>
          <TableHead className="text-right">Variance</TableHead>
          <TableHead className="text-right">Patient bal.</TableHead>
          {showConfirm && <TableHead />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.claimId}>
            <TableCell className="font-mono text-xs">{r.claimNumber}</TableCell>
            <TableCell>{r.patientName}</TableCell>
            <TableCell className="text-muted-foreground">{r.carrierName}</TableCell>
            <TableCell className="text-right">{centsToUsd(r.billedCents)}</TableCell>
            <TableCell className="text-right">
              {centsToUsd(r.estimatedInsuranceCents)}
            </TableCell>
            <TableCell className="text-right">{centsToUsd(r.insurancePaidCents)}</TableCell>
            <TableCell className="text-right">
              {r.varianceCents !== null ? (
                <span
                  className={
                    r.varianceCents > 0
                      ? "text-green-600"
                      : r.varianceCents < 0
                        ? "text-amber-600"
                        : ""
                  }
                >
                  {r.varianceCents > 0 ? "+" : ""}
                  {centsToUsd(r.varianceCents)}
                  {r.varianceCents > 0 && (
                    <Badge className="ml-1 text-xs" variant="secondary">
                      Overpaid
                    </Badge>
                  )}
                </span>
              ) : (
                <span className="text-muted-foreground">No estimate</span>
              )}
            </TableCell>
            <TableCell className="text-right">
              <span className={r.patientBalanceCents < 0 ? "text-green-600" : ""}>
                {centsToUsd(r.patientBalanceCents)}
                {r.patientBalanceCents < 0 && (
                  <Badge className="ml-1 text-xs" variant="secondary">
                    Credit
                  </Badge>
                )}
              </span>
            </TableCell>
            {showConfirm && (
              <TableCell>
                <button
                  type="button"
                  onClick={() => onConfirm(r.claimId)}
                  disabled={confirming}
                  className="text-sm text-primary underline disabled:opacity-50"
                >
                  Confirm
                </button>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </TableShell>
  );
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border">
      <Table>{children}</Table>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-border py-16 text-center">
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function ClaimsPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeTab = (searchParams.get("tab") as Tab | null) ?? "all";
  const { data: summary } = useARSummary();

  const mode = summary?.eraReconciliationMode ?? "auto";
  const pendingCount =
    mode === "confirm" ? (summary?.reconciliationPendingCount ?? 0) : 0;

  function setTab(tab: Tab) {
    router.push(`/billing/claims?tab=${tab}`);
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <Link
        href="/billing"
        className="self-start text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        ← Billing
      </Link>
      <PageHeader title="Claims" description="Insurance claims and A/R management." />

      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={[
              "relative px-4 py-2 text-sm transition-colors",
              activeTab === key
                ? "border-b-2 border-primary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            ].join(" ")}
          >
            {label}
            {key === "reconciled" && pendingCount > 0 && (
              <span className="ml-1.5 rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {activeTab === "all" && <AllTab />}
      {(activeTab === "awaiting" ||
        activeTab === "underpaid" ||
        activeTab === "problem") && <ARTab category={activeTab} />}
      {activeTab === "reconciled" && <ReconciledTab mode={mode} />}
    </div>
  );
}

export default function ClaimsPage() {
  return (
    <Suspense>
      <ClaimsPageInner />
    </Suspense>
  );
}
