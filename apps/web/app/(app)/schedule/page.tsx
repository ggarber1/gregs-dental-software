import { PageHeader } from "@/components/layout/PageHeader";

export default function SchedulePage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Schedule"
        description="Daily appointment schedule and operatory view"
      />
      <p className="text-sm text-muted-foreground">Coming in Module 1.6.</p>
    </div>
  );
}
