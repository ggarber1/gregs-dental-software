import { PageHeader } from "@/components/layout/PageHeader";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Practice configuration and user management"
      />
      <p className="text-sm text-muted-foreground">Coming in a future module.</p>
    </div>
  );
}
