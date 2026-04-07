import { PageHeader } from "@/components/layout/PageHeader";

export default function PatientsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Patients"
        description="Search and manage patient records"
      />
      <p className="text-sm text-muted-foreground">Coming in Module 1.6.</p>
    </div>
  );
}
