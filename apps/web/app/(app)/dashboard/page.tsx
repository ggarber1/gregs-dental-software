import { PageHeader } from "@/components/layout/PageHeader";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Dashboard"
        description="Practice overview and daily summary"
      />
      <p className="text-sm text-muted-foreground">Coming in a future module.</p>
    </div>
  );
}
