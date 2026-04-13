"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Pencil, X, Check, Send } from "lucide-react";
import Link from "next/link";

import { MedicalAlertsBar } from "@/components/patients/MedicalAlertsBar";
import { IntakeReviewModal } from "@/components/patients/IntakeReviewModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  usePatient,
  useUpdatePatient,
  isNotFoundError,
  type Patient,
  type UpdatePatientBody,
  type Sex,
} from "@/lib/api/patients";
import {
  usePatientIntakeForms,
  useSendIntakeForm,
  type IntakeFormSummary,
} from "@/lib/api/intake";

function formatDob(dob: string): string {
  const [y, m, d] = dob.split("-");
  return `${m}/${d}/${y}`;
}

function sexLabel(sex: Sex | null): string {
  if (!sex) return "Unknown";
  return sex.charAt(0).toUpperCase() + sex.slice(1);
}

// ── Demographics card ─────────────────────────────────────────────────────────

interface DemographicsCardProps {
  patient: Patient;
  patientId: string;
}

function DemographicsCard({ patient, patientId }: DemographicsCardProps) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState({
    firstName: patient.firstName,
    lastName: patient.lastName,
    dateOfBirth: patient.dateOfBirth,
    sex: patient.sex,
    ssnLastFour: patient.ssnLastFour ?? "",
  });
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useUpdatePatient(patientId);

  function handleCancel() {
    setFields({
      firstName: patient.firstName,
      lastName: patient.lastName,
      dateOfBirth: patient.dateOfBirth,
      sex: patient.sex,
      ssnLastFour: patient.ssnLastFour ?? "",
    });
    setError(null);
    setEditing(false);
  }

  function handleSave() {
    if (!fields.firstName.trim() || !fields.lastName.trim() || !fields.dateOfBirth.trim()) {
      setError("First name, last name, and date of birth are required.");
      return;
    }
    const body: UpdatePatientBody = {
      firstName: fields.firstName,
      lastName: fields.lastName,
      dateOfBirth: fields.dateOfBirth,
      sex: fields.sex,
      ssnLastFour: fields.ssnLastFour || null,
    };
    mutate(body, {
      onSuccess: () => {
        setError(null);
        setEditing(false);
      },
      onError: () => setError("Failed to save. Please try again."),
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Demographics</CardTitle>
        {!editing ? (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
        ) : (
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={handleCancel} disabled={isPending}>
              <X className="h-4 w-4" />
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isPending}>
              <Check className="h-4 w-4" />
              {isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <div className="grid gap-4">
            <div className="grid grid-cols-2 gap-4">
              <EditField label="First name *">
                <Input
                  value={fields.firstName}
                  onChange={(e) => setFields((p) => ({ ...p, firstName: e.target.value }))}
                />
              </EditField>
              <EditField label="Last name *">
                <Input
                  value={fields.lastName}
                  onChange={(e) => setFields((p) => ({ ...p, lastName: e.target.value }))}
                />
              </EditField>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <EditField label="Date of birth *">
                <Input
                  type="date"
                  value={fields.dateOfBirth}
                  onChange={(e) => setFields((p) => ({ ...p, dateOfBirth: e.target.value }))}
                />
              </EditField>
              <EditField label="Sex">
                <Select
                  value={fields.sex ?? ""}
                  onValueChange={(v) =>
                    setFields((p) => ({ ...p, sex: v === "" ? null : (v as Sex) }))
                  }
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
            <EditField label="SSN last 4">
              <Input
                value={fields.ssnLastFour}
                onChange={(e) => setFields((p) => ({ ...p, ssnLastFour: e.target.value }))}
                placeholder="1234"
                maxLength={4}
                className="max-w-[8rem]"
              />
            </EditField>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        ) : (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <DataRow label="First name" value={patient.firstName} />
            <DataRow label="Last name" value={patient.lastName} />
            <DataRow label="Date of birth" value={formatDob(patient.dateOfBirth)} />
            <DataRow label="Sex" value={sexLabel(patient.sex)} />
            <DataRow
              label="SSN"
              value={patient.ssnLastFour ? `••••••••${patient.ssnLastFour}` : "—"}
            />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

// ── Contact card ──────────────────────────────────────────────────────────────

interface ContactCardProps {
  patient: Patient;
  patientId: string;
}

function ContactCard({ patient, patientId }: ContactCardProps) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState({
    phone: patient.phone ?? "",
    email: patient.email ?? "",
    addressLine1: patient.addressLine1 ?? "",
    addressLine2: patient.addressLine2 ?? "",
    city: patient.city ?? "",
    state: patient.state ?? "",
    zip: patient.zip ?? "",
    smsOptOut: patient.smsOptOut,
  });
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useUpdatePatient(patientId);

  function handleCancel() {
    setFields({
      phone: patient.phone ?? "",
      email: patient.email ?? "",
      addressLine1: patient.addressLine1 ?? "",
      addressLine2: patient.addressLine2 ?? "",
      city: patient.city ?? "",
      state: patient.state ?? "",
      zip: patient.zip ?? "",
      smsOptOut: patient.smsOptOut,
    });
    setError(null);
    setEditing(false);
  }

  function handleSave() {
    const body: UpdatePatientBody = {
      phone: fields.phone || null,
      email: fields.email || null,
      addressLine1: fields.addressLine1 || null,
      addressLine2: fields.addressLine2 || null,
      city: fields.city || null,
      state: fields.state || null,
      zip: fields.zip || null,
      smsOptOut: fields.smsOptOut,
    };
    mutate(body, {
      onSuccess: () => {
        setError(null);
        setEditing(false);
      },
      onError: () => setError("Failed to save. Please try again."),
    });
  }

  const addressParts = [
    patient.addressLine1,
    patient.addressLine2,
    patient.city && patient.state
      ? `${patient.city}, ${patient.state} ${patient.zip ?? ""}`.trim()
      : patient.city ?? patient.state ?? null,
  ].filter(Boolean);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Contact</CardTitle>
        {!editing ? (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
        ) : (
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={handleCancel} disabled={isPending}>
              <X className="h-4 w-4" />
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isPending}>
              <Check className="h-4 w-4" />
              {isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <div className="grid gap-4">
            <div className="grid grid-cols-2 gap-4">
              <EditField label="Phone">
                <Input
                  value={fields.phone}
                  onChange={(e) => setFields((p) => ({ ...p, phone: e.target.value }))}
                  placeholder="555-867-5309"
                />
              </EditField>
              <EditField label="Email">
                <Input
                  type="email"
                  value={fields.email}
                  onChange={(e) => setFields((p) => ({ ...p, email: e.target.value }))}
                  placeholder="jane@example.com"
                />
              </EditField>
            </div>
            <EditField label="Address">
              <Input
                value={fields.addressLine1}
                onChange={(e) => setFields((p) => ({ ...p, addressLine1: e.target.value }))}
                placeholder="123 Main St"
              />
            </EditField>
            <EditField label="Address line 2">
              <Input
                value={fields.addressLine2}
                onChange={(e) => setFields((p) => ({ ...p, addressLine2: e.target.value }))}
                placeholder="Apt 4B"
              />
            </EditField>
            <div className="grid grid-cols-3 gap-4">
              <EditField label="City" className="col-span-1">
                <Input
                  value={fields.city}
                  onChange={(e) => setFields((p) => ({ ...p, city: e.target.value }))}
                  placeholder="Boston"
                />
              </EditField>
              <EditField label="State" className="col-span-1">
                <Input
                  value={fields.state}
                  onChange={(e) =>
                    setFields((p) => ({ ...p, state: e.target.value.toUpperCase() }))
                  }
                  placeholder="MA"
                  maxLength={2}
                />
              </EditField>
              <EditField label="Zip" className="col-span-1">
                <Input
                  value={fields.zip}
                  onChange={(e) => setFields((p) => ({ ...p, zip: e.target.value }))}
                  placeholder="02101"
                />
              </EditField>
            </div>
            <div className="flex items-center gap-2">
              <input
                id="editSmsOptOut"
                type="checkbox"
                checked={fields.smsOptOut}
                onChange={(e) => setFields((p) => ({ ...p, smsOptOut: e.target.checked }))}
                className="h-4 w-4 rounded border-input"
              />
              <Label htmlFor="editSmsOptOut" className="cursor-pointer text-sm">
                Opt out of SMS reminders
              </Label>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        ) : (
          <dl className="grid gap-y-3 text-sm">
            <DataRow label="Phone" value={patient.phone ?? "—"} />
            <DataRow label="Email" value={patient.email ?? "—"} />
            <DataRow
              label="Address"
              value={addressParts.length > 0 ? addressParts.join("\n") : "—"}
            />
            <DataRow label="SMS opt-out" value={patient.smsOptOut ? "Yes" : "No"} />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 whitespace-pre-line font-medium">{value}</dd>
    </div>
  );
}

function EditField({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

// ── Clinical card ─────────────────────────────────────────────────────────────

function ClinicalCard({ patient, patientId }: { patient: Patient; patientId: string }) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState({
    allergiesRaw: (patient.allergies ?? []).join(", "),
    medicalAlertsRaw: (patient.medicalAlerts ?? []).join(", "),
  });
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useUpdatePatient(patientId);

  function handleCancel() {
    setFields({
      allergiesRaw: (patient.allergies ?? []).join(", "),
      medicalAlertsRaw: (patient.medicalAlerts ?? []).join(", "),
    });
    setError(null);
    setEditing(false);
  }

  function splitComma(raw: string): string[] {
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function handleSave() {
    mutate(
      {
        allergies: splitComma(fields.allergiesRaw),
        medicalAlerts: splitComma(fields.medicalAlertsRaw),
      },
      {
        onSuccess: () => {
          setError(null);
          setEditing(false);
        },
        onError: () => setError("Failed to save. Please try again."),
      },
    );
  }

  const allergiesDisplay = (patient.allergies ?? []).join(", ") || "—";
  const alertsDisplay = (patient.medicalAlerts ?? []).join(", ") || "—";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Clinical</CardTitle>
        {!editing ? (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
        ) : (
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={handleCancel} disabled={isPending}>
              <X className="h-4 w-4" />
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isPending}>
              <Check className="h-4 w-4" />
              {isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {editing ? (
          <div className="grid gap-4">
            <EditField label="Allergies (comma-separated)">
              <Input
                value={fields.allergiesRaw}
                onChange={(e) => setFields((p) => ({ ...p, allergiesRaw: e.target.value }))}
                placeholder="Penicillin, Latex"
              />
            </EditField>
            <EditField label="Medical alerts (comma-separated)">
              <Input
                value={fields.medicalAlertsRaw}
                onChange={(e) =>
                  setFields((p) => ({ ...p, medicalAlertsRaw: e.target.value }))
                }
                placeholder="Diabetic, Pacemaker"
              />
            </EditField>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        ) : (
          <dl className="grid gap-y-3 text-sm">
            <DataRow label="Allergies" value={allergiesDisplay} />
            <DataRow label="Medical alerts" value={alertsDisplay} />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

// ── Intake forms card ─────────────────────────────────────────────────────────

function statusBadgeVariant(status: IntakeFormSummary["status"]) {
  if (status === "completed") return "default" as const;
  if (status === "expired") return "secondary" as const;
  return "outline" as const;
}

function IntakeFormsCard({ patient, patientId }: { patient: Patient; patientId: string }) {
  const { data: forms, isLoading } = usePatientIntakeForms(patientId);
  const { mutate: sendForm, isPending: isSending, error: sendError } = useSendIntakeForm();
  const [reviewId, setReviewId] = useState<string | null>(null);

  function handleSend() {
    sendForm({ patientId });
  }

  const canSend = !patient.smsOptOut && Boolean(patient.phone);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base font-semibold">Intake Forms</CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={handleSend}
            disabled={isSending || !canSend}
            title={!canSend ? "Patient has no phone number or has opted out of SMS" : undefined}
          >
            <Send className="h-4 w-4" />
            {isSending ? "Sending…" : "Send form"}
          </Button>
        </CardHeader>
        <CardContent>
          {sendError && (
            <p className="mb-3 text-sm text-destructive">Failed to send form. Please try again.</p>
          )}
          {!canSend && (
            <p className="mb-3 text-xs text-muted-foreground">
              {!patient.phone
                ? "Add a phone number to send an intake form."
                : "Patient has opted out of SMS."}
            </p>
          )}
          {isLoading && (
            <div className="flex justify-center py-4">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          )}
          {!isLoading && (!forms || forms.length === 0) && (
            <p className="text-sm text-muted-foreground">No intake forms sent yet.</p>
          )}
          {!isLoading && forms && forms.length > 0 && (
            <ul className="divide-y divide-border">
              {forms.map((f) => (
                <li key={f.id} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={statusBadgeVariant(f.status)} className="capitalize">
                      {f.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {new Date(f.createdAt).toLocaleDateString()}
                    </span>
                  </div>
                  {f.status === "completed" && (
                    <Button variant="ghost" size="sm" onClick={() => setReviewId(f.id)}>
                      Review
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {reviewId && (
        <IntakeReviewModal
          intakeFormId={reviewId}
          patientId={patientId}
          open={Boolean(reviewId)}
          onClose={() => setReviewId(null)}
          onApplied={() => setReviewId(null)}
        />
      )}
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PatientDetailPage() {
  const params = useParams<{ patientId: string }>();
  const router = useRouter();
  const patientId = params.patientId;

  const { data: patient, isLoading, isError, error } = usePatient(patientId);

  // Redirect on 404
  useEffect(() => {
    if (isError && isNotFoundError(error)) {
      router.replace("/patients");
    }
  }, [isError, error, router]);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-24 animate-pulse rounded bg-muted" />
        <div className="h-48 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  if (!patient) return null;

  return (
    <div className="flex flex-col gap-6">
      {/* Back + Title */}
      <div className="flex flex-col gap-2">
        <Link
          href="/patients"
          className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Patients
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {patient.firstName} {patient.lastName}
          </h1>
          <Badge variant="secondary">{formatDob(patient.dateOfBirth)}</Badge>
          {patient.sex && (
            <Badge variant="outline">{sexLabel(patient.sex)}</Badge>
          )}
        </div>
      </div>

      {/* Medical alerts bar */}
      <MedicalAlertsBar
        allergies={patient.allergies ?? []}
        medicalAlerts={patient.medicalAlerts ?? []}
      />

      {/* Cards */}
      <div className="grid gap-6 lg:grid-cols-2">
        <DemographicsCard patient={patient} patientId={patientId} />
        <ContactCard patient={patient} patientId={patientId} />
        <ClinicalCard patient={patient} patientId={patientId} />
      </div>

      {/* Intake forms */}
      <IntakeFormsCard patient={patient} patientId={patientId} />
    </div>
  );
}
