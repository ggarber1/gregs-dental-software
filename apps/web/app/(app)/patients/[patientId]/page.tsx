import { PageHeader } from "@/components/layout/PageHeader";

interface PatientDetailPageProps {
  params: Promise<{ patientId: string }>;
}

export default async function PatientDetailPage({ params }: PatientDetailPageProps) {
  const { patientId } = await params;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Patient Record" description={`Patient ID: ${patientId}`} />
      <p className="text-sm text-muted-foreground">Coming in Module 1.6.</p>
    </div>
  );
}
