"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useIntakeFormDetail,
  useApplyIntakeForm,
} from "@/lib/api/intake";

interface IntakeReviewModalProps {
  intakeFormId: string;
  patientId: string;
  open: boolean;
  onClose: () => void;
  onApplied: () => void;
}

function Row({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  const display = Array.isArray(value)
    ? (value as string[]).join(", ") || "—"
    : String(value as string | number | boolean);
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{display || "—"}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">{children}</dl>
    </div>
  );
}

function IntakeResponses({ responses }: { responses: Record<string, unknown> }) {
  return (
    <div className="grid gap-5">
      <Section title="Personal">
        <Row label="First name" value={responses.firstName} />
        <Row label="Last name" value={responses.lastName} />
        <Row label="Date of birth" value={responses.dateOfBirth} />
        <Row label="Sex" value={responses.sex} />
        <Row label="Phone" value={responses.phone} />
        <Row label="Email" value={responses.email} />
        <Row label="Address" value={responses.addressLine1} />
        <Row label="Address line 2" value={responses.addressLine2} />
        <Row label="City" value={responses.city} />
        <Row label="State" value={responses.state} />
        <Row label="Zip" value={responses.zip} />
      </Section>
      <Section title="Medical history">
        <Row label="Conditions" value={responses.medicalConditions} />
        <Row label="Medications" value={responses.medications} />
        <Row label="Allergies" value={responses.allergies} />
      </Section>
      <Section title="Dental history">
        <Row label="Last dental visit" value={responses.lastDentalVisit} />
        <Row label="Previous dentist" value={responses.previousDentist} />
        <Row label="Chief complaint" value={responses.chiefComplaint} />
      </Section>
      <Section title="Insurance">
        <Row label="Carrier" value={responses.insuranceCarrier} />
        <Row label="Member ID" value={responses.insuranceMemberId} />
        <Row label="Group number" value={responses.insuranceGroupNumber} />
        <Row label="Holder name" value={responses.insuranceHolderName} />
        <Row label="Holder DOB" value={responses.insuranceHolderDob} />
        <Row label="Relationship" value={responses.relationshipToInsured} />
      </Section>
      <Section title="Consent">
        <Row label="HIPAA accepted" value={responses.hipaaConsentAccepted ? "Yes" : "No"} />
        <Row label="Signature" value={responses.hipaaConsentSignature} />
        <Row label="SMS opt-in" value={responses.smsOptIn ? "Yes" : "No"} />
      </Section>
    </div>
  );
}

export function IntakeReviewModal({
  intakeFormId,
  patientId,
  open,
  onClose,
  onApplied,
}: IntakeReviewModalProps) {
  const { data: form, isLoading } = useIntakeFormDetail(open ? intakeFormId : null);
  const { mutate: applyIntake, isPending: isApplying, error: applyError } = useApplyIntakeForm(patientId);

  function handleApply() {
    applyIntake(intakeFormId, {
      onSuccess: () => {
        onApplied();
        onClose();
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Review intake form
            {form && (
              <Badge variant="secondary" className="capitalize">
                {form.status}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        {isLoading && (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        )}

        {form && !isLoading && (
          <>
            {form.responses ? (
              <IntakeResponses responses={form.responses} />
            ) : (
              <p className="text-sm text-muted-foreground">No responses on file.</p>
            )}

            {applyError && (
              <p className="text-sm text-destructive">
                Failed to apply intake data. Please try again.
              </p>
            )}

            {form.status === "completed" && (
              <div className="mt-2 flex justify-end">
                <Button onClick={handleApply} disabled={isApplying}>
                  {isApplying ? "Applying…" : "Apply to patient record"}
                </Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
