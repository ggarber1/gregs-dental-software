"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Pencil, X, Check, Send, Trash2 } from "lucide-react";
import Link from "next/link";

import { InsuranceCard } from "@/components/patients/InsuranceCard";
import { MedicalAlertsBar } from "@/components/patients/MedicalAlertsBar";
import { MedicalHistoryCard } from "@/components/patients/MedicalHistoryCard";
import { ClinicalNoteCard } from "@/components/patients/ClinicalNoteCard";
import { ClinicalNoteList } from "@/components/patients/ClinicalNoteList";
import { ToothChartCard } from "@/components/patients/ToothChartCard";
import { IntakeReviewModal } from "@/components/patients/IntakeReviewModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  usePatient,
  useUpdatePatient,
  useDeletePatient,
  isNotFoundError,
  type Patient,
  type UpdatePatientBody,
  type Sex,
  type MaritalStatus,
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
  if (!sex) return "—";
  return sex.charAt(0).toUpperCase() + sex.slice(1);
}

function maritalStatusLabel(status: MaritalStatus | null): string {
  if (!status) return "—";
  const labels: Record<MaritalStatus, string> = {
    single: "Single",
    married: "Married",
    divorced: "Divorced",
    widowed: "Widowed",
    separated: "Separated",
    domestic_partner: "Domestic partner",
    other: "Other",
  };
  return labels[status] ?? "—";
}

function maskSsn(ssn: string | null): string {
  if (!ssn) return "—";
  const last4 = ssn.slice(-4);
  return `•••-••-${last4}`;
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
    maritalStatus: patient.maritalStatus,
    ssn: patient.ssn ?? "",
  });
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useUpdatePatient(patientId);

  useEffect(() => {
    if (!editing) {
      setFields({
        firstName: patient.firstName,
        lastName: patient.lastName,
        dateOfBirth: patient.dateOfBirth,
        sex: patient.sex,
        maritalStatus: patient.maritalStatus,
        ssn: patient.ssn ?? "",
      });
    }
  }, [patient, editing]);

  function handleCancel() {
    setFields({
      firstName: patient.firstName,
      lastName: patient.lastName,
      dateOfBirth: patient.dateOfBirth,
      sex: patient.sex,
      maritalStatus: patient.maritalStatus,
      ssn: patient.ssn ?? "",
    });
    setError(null);
    setEditing(false);
  }

  function handleSave() {
    if (!fields.firstName.trim() || !fields.lastName.trim() || !fields.dateOfBirth.trim()) {
      setError("First name, last name, and date of birth are required.");
      return;
    }
    if (fields.ssn && !/^\d{4}$|^\d{9}$/.test(fields.ssn)) {
      setError("SSN must be 4 digits (last four) or 9 digits (full).");
      return;
    }
    const body: UpdatePatientBody = {
      firstName: fields.firstName,
      lastName: fields.lastName,
      dateOfBirth: fields.dateOfBirth,
      sex: fields.sex,
      maritalStatus: fields.maritalStatus,
      ssn: fields.ssn || null,
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
            <EditField label="Marital status">
              <Select
                value={fields.maritalStatus ?? ""}
                onValueChange={(v) =>
                  setFields((p) => ({
                    ...p,
                    maritalStatus: v === "" ? null : (v as MaritalStatus),
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">Single</SelectItem>
                  <SelectItem value="married">Married</SelectItem>
                  <SelectItem value="divorced">Divorced</SelectItem>
                  <SelectItem value="widowed">Widowed</SelectItem>
                  <SelectItem value="separated">Separated</SelectItem>
                  <SelectItem value="domestic_partner">Domestic partner</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </EditField>
            <EditField label="SSN (last 4 or full 9 digits)">
              <Input
                value={fields.ssn}
                onChange={(e) => setFields((p) => ({ ...p, ssn: e.target.value }))}
                placeholder="1234 or 123456789"
                maxLength={9}
                className="max-w-[12rem]"
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
            <DataRow label="Marital status" value={maritalStatusLabel(patient.maritalStatus)} />
            <DataRow label="SSN" value={maskSsn(patient.ssn)} />
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

  useEffect(() => {
    if (!editing) {
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
    }
  }, [patient, editing]);

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

// ── Dental history card ───────────────────────────────────────────────────────

function DentalHistoryCard({ patient, patientId }: { patient: Patient; patientId: string }) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState({
    lastXrayDate: patient.lastXrayDate ?? "",
    lastDentalVisit: patient.lastDentalVisit ?? "",
    previousDentist: patient.previousDentist ?? "",
    dentalSymptomsRaw: (patient.dentalSymptoms ?? []).join(", "),
  });
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useUpdatePatient(patientId);

  useEffect(() => {
    if (!editing) {
      setFields({
        lastXrayDate: patient.lastXrayDate ?? "",
        lastDentalVisit: patient.lastDentalVisit ?? "",
        previousDentist: patient.previousDentist ?? "",
        dentalSymptomsRaw: (patient.dentalSymptoms ?? []).join(", "),
      });
    }
  }, [patient, editing]);

  function handleCancel() {
    setFields({
      lastXrayDate: patient.lastXrayDate ?? "",
      lastDentalVisit: patient.lastDentalVisit ?? "",
      previousDentist: patient.previousDentist ?? "",
      dentalSymptomsRaw: (patient.dentalSymptoms ?? []).join(", "),
    });
    setError(null);
    setEditing(false);
  }

  function handleSave() {
    const dentalSymptoms = fields.dentalSymptomsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    mutate(
      {
        lastXrayDate: fields.lastXrayDate || null,
        lastDentalVisit: fields.lastDentalVisit || null,
        previousDentist: fields.previousDentist || null,
        dentalSymptoms,
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

  const xrayDisplay = patient.lastXrayDate ? formatDob(patient.lastXrayDate) : "—";
  const symptomsDisplay = (patient.dentalSymptoms ?? []).join(", ") || "—";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Dental History</CardTitle>
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
            <EditField label="Last dental visit">
              <Input
                value={fields.lastDentalVisit}
                onChange={(e) => setFields((p) => ({ ...p, lastDentalVisit: e.target.value }))}
                placeholder="About 1 year ago, or never"
              />
            </EditField>
            <EditField label="Previous dentist">
              <Input
                value={fields.previousDentist}
                onChange={(e) => setFields((p) => ({ ...p, previousDentist: e.target.value }))}
                placeholder="Dr. Smith"
              />
            </EditField>
            <EditField label="Last X-ray date">
              <Input
                type="date"
                value={fields.lastXrayDate}
                onChange={(e) => setFields((p) => ({ ...p, lastXrayDate: e.target.value }))}
                className="max-w-[12rem]"
              />
            </EditField>
            <EditField label="Dental symptoms (comma-separated)">
              <Input
                value={fields.dentalSymptomsRaw}
                onChange={(e) => setFields((p) => ({ ...p, dentalSymptomsRaw: e.target.value }))}
                placeholder="Sensitivity to cold, Bleeding gums"
              />
            </EditField>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        ) : (
          <dl className="grid gap-y-3 text-sm">
            <DataRow label="Last dental visit" value={patient.lastDentalVisit ?? "—"} />
            <DataRow label="Previous dentist" value={patient.previousDentist ?? "—"} />
            <DataRow label="Last X-ray" value={xrayDisplay} />
            <DataRow label="Dental symptoms" value={symptomsDisplay} />
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

// ── Delete confirmation dialog ────────────────────────────────────────────────

function DeletePatientDialog({
  patient,
  open,
  onClose,
  onDeleted,
}: {
  patient: Patient;
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { mutate: deletePatient, isPending, error } = useDeletePatient();

  function handleConfirm() {
    deletePatient(patient.id, {
      onSuccess: onDeleted,
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete patient?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Are you sure you want to delete{" "}
          <span className="font-medium text-foreground">
            {patient.firstName} {patient.lastName}
          </span>
          ? This cannot be undone.
        </p>
        {error && (
          <p className="text-sm text-destructive">Failed to delete patient. Please try again.</p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={isPending}>
            No, keep patient
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={isPending}>
            {isPending ? "Deleting…" : "Yes, delete"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PatientDetailPage() {
  const params = useParams<{ patientId: string }>();
  const router = useRouter();
  const patientId = params.patientId;

  const { data: patient, isLoading, isError, error } = usePatient(patientId);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "notes" | "tooth-chart">("overview");

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
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {patient.firstName} {patient.lastName}
            </h1>
            <Badge variant="secondary">{formatDob(patient.dateOfBirth)}</Badge>
            {patient.sex && (
              <Badge variant="outline">{sexLabel(patient.sex)}</Badge>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => setShowDeleteDialog(true)}
          >
            <Trash2 className="h-4 w-4" />
            Delete patient
          </Button>
        </div>
      </div>

      {showDeleteDialog && (
        <DeletePatientDialog
          patient={patient}
          open={showDeleteDialog}
          onClose={() => setShowDeleteDialog(false)}
          onDeleted={() => router.replace("/patients")}
        />
      )}

      {/* Medical alerts bar */}
      <MedicalAlertsBar
        allergies={patient.allergies ?? []}
        medicalAlerts={patient.medicalAlerts ?? []}
        medications={patient.medications ?? []}
      />

      {/* Tab navigation */}
      <div className="flex gap-1 border-b border-border">
        {(["overview", "notes", "tooth-chart"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab === "tooth-chart" ? "Tooth Chart" : tab}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {activeTab === "overview" && (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <DemographicsCard patient={patient} patientId={patientId} />
            <ContactCard patient={patient} patientId={patientId} />
            <MedicalHistoryCard patientId={patientId} />
            <DentalHistoryCard patient={patient} patientId={patientId} />
            <InsuranceCard patientId={patientId} />
            <ClinicalNoteCard patientId={patientId} />
          </div>
          <IntakeFormsCard patient={patient} patientId={patientId} />
        </>
      )}

      {/* Notes tab */}
      {activeTab === "notes" && (
        <div className="rounded-lg border border-border bg-card">
          <ClinicalNoteList patientId={patientId} />
        </div>
      )}

      {/* Tooth Chart tab */}
      {activeTab === "tooth-chart" && (
        <ToothChartCard patientId={patientId} />
      )}
    </div>
  );
}
