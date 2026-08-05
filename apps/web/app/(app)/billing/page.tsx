"use client";

import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { centsToUsd, useARSummary } from "@/lib/api/reports";

function SummaryCard({
  title,
  value,
  subtitle,
  href,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="flex flex-col gap-1 rounded-lg border border-border p-5 hover:bg-muted/40 transition-colors"
    >
      <span className="text-sm text-muted-foreground">{title}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {subtitle && (
        <span className="text-xs text-muted-foreground">{subtitle}</span>
      )}
    </Link>
  );
}

export default function BillingPage() {
  const { data: summary, isLoading } = useARSummary();

  if (isLoading || !summary) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <PageHeader title="Billing" description="Practice A/R overview" />
        <div className="h-32 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader title="Billing" description="Practice A/R overview" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          title="Insurance A/R"
          value={centsToUsd(summary.insuranceArTotalCents)}
          subtitle="Awaiting + underpaid"
          href="/billing/claims?tab=awaiting"
        />
        <SummaryCard
          title="Claims Needing Attention"
          value={summary.claimsNeedingAttention}
          subtitle="Denied · rejected · appealing"
          href="/billing/claims?tab=problem"
        />
        <SummaryCard
          title="Patient A/R"
          value={centsToUsd(summary.patientArTotalCents)}
          subtitle="Statements coming soon"
          href="/billing/claims"
        />
        {summary.eraReconciliationMode === "confirm" &&
          summary.reconciliationPendingCount > 0 && (
            <SummaryCard
              title="Reconciliation Pending"
              value={summary.reconciliationPendingCount}
              subtitle="ERA settlements to confirm"
              href="/billing/claims?tab=reconciled"
            />
          )}
      </div>
    </div>
  );
}
