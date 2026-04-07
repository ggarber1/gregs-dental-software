import { PageHeader } from "@/components/layout/PageHeader";

export default function BillingPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Billing"
        description="Claims, co-pay estimation, and insurance verification"
      />
      <p className="text-sm text-muted-foreground">Coming in Module 1.6.</p>
    </div>
  );
}
