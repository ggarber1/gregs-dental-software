"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useIntakeFormDetail,
  useApplyIntakeForm,
} from "@/lib/api/intake";
import { useUpdatePatient, type UpdatePatientBody, type Sex } from "@/lib/api/patients";

// ── Read-only display helpers ─────────────────────────────────────────────────

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
        <Row label="Marital status" value={responses.maritalStatus} />
        <Row label="Emergency contact" value={responses.emergencyContactName} />
        <Row label="Emergency phone" value={responses.emergencyContactPhone} />
        <Row label="Occupation" value={responses.occupation} />
        <Row label="Employer" value={responses.employer} />
        <Row label="Referred by" value={responses.referralSource} />
      </Section>
      <Section title="Medical history">
        <Row label="Conditions" value={responses.medicalConditions} />
        <Row label="Medications" value={responses.medications} />
        <Row label="Allergies" value={responses.allergies} />
      </Section>
      <Section title="Dental history">
        <Row label="Last dental visit" value={responses.lastDentalVisit} />
        <Row label="Last X-rays" value={responses.lastXrayDate} />
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

// ── Edit form types ───────────────────────────────────────────────────────────

interface EditFields {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  sex: Sex | "";
  phone: string;
  email: string;
  addressLine1: string;
  addressLine2: string;
  city: string;
  state: string;
  zip: string;
  allergiesRaw: string;
  medicalAlertsRaw: string;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function responsesToEditFields(responses: Record<string, unknown>): EditFields {
  const conditions = Array.isArray(responses.medicalConditions)
    ? (responses.medicalConditions as string[])
    : [];
  const medications = Array.isArray(responses.medications)
    ? (responses.medications as string[])
    : [];
  const allergies = Array.isArray(responses.allergies)
    ? (responses.allergies as string[])
    : [];

  return {
    firstName: str(responses.firstName),
    lastName: str(responses.lastName),
    dateOfBirth: str(responses.dateOfBirth),
    sex: (responses.sex as Sex) ?? "",
    phone: str(responses.phone),
    email: str(responses.email),
    addressLine1: str(responses.addressLine1),
    addressLine2: str(responses.addressLine2),
    city: str(responses.city),
    state: str(responses.state),
    zip: str(responses.zip),
    allergiesRaw: allergies.join(", "),
    medicalAlertsRaw: [...conditions, ...medications].join(", "),
  };
}

function splitComma(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// ── Edit form UI ──────────────────────────────────────────────────────────────

function EditField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

function IntakeEditForm({
  fields,
  onChange,
  responses,
}: {
  fields: EditFields;
  onChange: (patch: Partial<EditFields>) => void;
  responses: Record<string, unknown>;
}) {
  return (
    <div className="grid gap-5">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Personal
        </p>
        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <EditField label="First name">
              <Input
                value={fields.firstName}
                onChange={(e) => onChange({ firstName: e.target.value })}
              />
            </EditField>
            <EditField label="Last name">
              <Input
                value={fields.lastName}
                onChange={(e) => onChange({ lastName: e.target.value })}
              />
            </EditField>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <EditField label="Date of birth">
              <Input
                type="date"
                value={fields.dateOfBirth}
                onChange={(e) => onChange({ dateOfBirth: e.target.value })}
              />
            </EditField>
            <EditField label="Sex">
              <Select
                value={fields.sex}
                onValueChange={(v) => onChange({ sex: v as Sex | "" })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                  <SelectItem value="unknown">Unknown</SelectItem>
                </SelectContent>
              </Select>
            </EditField>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <EditField label="Phone">
              <Input
                value={fields.phone}
                onChange={(e) => onChange({ phone: e.target.value })}
              />
            </EditField>
            <EditField label="Email">
              <Input
                type="email"
                value={fields.email}
                onChange={(e) => onChange({ email: e.target.value })}
              />
            </EditField>
          </div>
          <EditField label="Address">
            <Input
              value={fields.addressLine1}
              onChange={(e) => onChange({ addressLine1: e.target.value })}
            />
          </EditField>
          <EditField label="Address line 2">
            <Input
              value={fields.addressLine2}
              onChange={(e) => onChange({ addressLine2: e.target.value })}
            />
          </EditField>
          <div className="grid grid-cols-3 gap-3">
            <EditField label="City">
              <Input
                value={fields.city}
                onChange={(e) => onChange({ city: e.target.value })}
              />
            </EditField>
            <EditField label="State">
              <Input
                value={fields.state}
                onChange={(e) =>
                  onChange({ state: e.target.value.toUpperCase() })
                }
                maxLength={2}
              />
            </EditField>
            <EditField label="Zip">
              <Input
                value={fields.zip}
                onChange={(e) => onChange({ zip: e.target.value })}
              />
            </EditField>
          </div>
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Clinical
        </p>
        <div className="grid gap-3">
          <EditField label="Allergies (comma-separated)">
            <Input
              value={fields.allergiesRaw}
              onChange={(e) => onChange({ allergiesRaw: e.target.value })}
              placeholder="Penicillin, Latex"
            />
          </EditField>
          <EditField label="Medical alerts (comma-separated)">
            <Input
              value={fields.medicalAlertsRaw}
              onChange={(e) => onChange({ medicalAlertsRaw: e.target.value })}
              placeholder="Diabetic, Pacemaker"
            />
          </EditField>
        </div>
      </div>

      {/* Insurance shown read-only — no insurance fields on patient record yet */}
      {!!(responses.insuranceCarrier || responses.insuranceMemberId) && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Insurance (read-only)
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Row label="Carrier" value={responses.insuranceCarrier} />
            <Row label="Member ID" value={responses.insuranceMemberId} />
            <Row label="Group number" value={responses.insuranceGroupNumber} />
            <Row label="Holder name" value={responses.insuranceHolderName} />
            <Row label="Holder DOB" value={responses.insuranceHolderDob} />
            <Row label="Relationship" value={responses.relationshipToInsured} />
          </dl>
        </div>
      )}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────

interface IntakeReviewModalProps {
  intakeFormId: string;
  patientId: string;
  open: boolean;
  onClose: () => void;
  onApplied: () => void;
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
  const { mutate: updatePatient, isPending: isUpdating } = useUpdatePatient(patientId);

  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState<EditFields | null>(null);

  // Seed edit fields whenever responses load
  useEffect(() => {
    if (form?.responses) {
      setEditFields(responsesToEditFields(form.responses));
    }
  }, [form?.responses]);

  function handleEditChange(patch: Partial<EditFields>) {
    setEditFields((prev) => (prev ? { ...prev, ...patch } : prev));
  }

  function handleApply() {
    applyIntake(intakeFormId, {
      onSuccess: () => {
        if (editing && editFields) {
          // Override with front-desk corrections (omit empty required fields to avoid validation errors)
          const body: UpdatePatientBody = {
            sex: editFields.sex || null,
            phone: editFields.phone || null,
            email: editFields.email || null,
            addressLine1: editFields.addressLine1 || null,
            addressLine2: editFields.addressLine2 || null,
            city: editFields.city || null,
            state: editFields.state || null,
            zip: editFields.zip || null,
            allergies: splitComma(editFields.allergiesRaw),
            medicalAlerts: splitComma(editFields.medicalAlertsRaw),
          };
          if (editFields.firstName) body.firstName = editFields.firstName;
          if (editFields.lastName) body.lastName = editFields.lastName;
          if (editFields.dateOfBirth) body.dateOfBirth = editFields.dateOfBirth;
          updatePatient(body, {
            onSuccess: () => {
              onApplied();
              onClose();
            },
          });
        } else {
          onApplied();
          onClose();
        }
      },
    });
  }

  const isBusy = isApplying || isUpdating;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2">
            <DialogTitle className="flex items-center gap-2">
              Review intake form
              {form && (
                <Badge variant="secondary" className="capitalize">
                  {form.status}
                </Badge>
              )}
            </DialogTitle>
            {form?.status === "completed" && !editing && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(true)}
              >
                Edit before applying
              </Button>
            )}
            {editing && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (form?.responses) {
                    setEditFields(responsesToEditFields(form.responses));
                  }
                  setEditing(false);
                }}
              >
                Cancel edits
              </Button>
            )}
          </div>
        </DialogHeader>

        {isLoading && (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          </div>
        )}

        {form && !isLoading && (
          <>
            {form.responses ? (
              editing && editFields ? (
                <IntakeEditForm
                  fields={editFields}
                  onChange={handleEditChange}
                  responses={form.responses}
                />
              ) : (
                <IntakeResponses responses={form.responses} />
              )
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
                <Button onClick={handleApply} disabled={isBusy}>
                  {isBusy
                    ? "Applying…"
                    : editing
                      ? "Apply with corrections"
                      : "Apply to patient record"}
                </Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
