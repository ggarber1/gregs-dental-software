import { PageHeader } from "@/components/layout/PageHeader";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface PortalSection {
  title: string;
  description: string;
}

const portalSections: PortalSection[] = [
  {
    title: "Appointments",
    description: "Upcoming appointments and visit details will appear here.",
  },
  {
    title: "Treatment Plans",
    description: "Active treatment plans and progress will appear here.",
  },
  {
    title: "Visit Summaries",
    description: "Past visit summaries and care notes will appear here.",
  },
  {
    title: "Medical & Insurance Updates",
    description: "Pre-visit medical history and insurance updates will appear here.",
  },
];

export default function PortalPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Patient Portal"
        description="Secure patient-facing workspace (shell only for now)."
      />

      <div className="grid gap-4 md:grid-cols-2">
        {portalSections.map((section) => (
          <Card key={section.title}>
            <CardHeader>
              <CardTitle className="text-lg">{section.title}</CardTitle>
              <CardDescription>{section.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Coming in Phase 5.2.</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
