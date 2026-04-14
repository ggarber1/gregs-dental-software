"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
import { useCreatePatient, type CreatePatientBody } from "@/lib/api/patients";
import { createInsurance } from "@/lib/api/insurance";

const schema = z.object({
  firstName: z.string().min(1, "Required").max(100),
  lastName: z.string().min(1, "Required").max(100),
  dateOfBirth: z.string().min(1, "Required").regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD"),
  sex: z.enum(["male", "female", "other", "unknown"]).nullable().optional(),
  maritalStatus: z
    .enum(["single", "married", "divorced", "widowed", "separated", "domestic_partner", "other"])
    .nullable()
    .optional(),
  phone: z.string().max(20).nullable().optional(),
  email: z.string().email("Invalid email").max(255).nullable().or(z.literal("")).optional(),
  addressLine1: z.string().max(255).nullable().optional(),
  addressLine2: z.string().max(255).nullable().optional(),
  city: z.string().max(100).nullable().optional(),
  state: z.string().length(2, "2-letter code").nullable().or(z.literal("")).optional(),
  zip: z.string().max(10).nullable().optional(),
  ssn: z
    .string()
    .regex(/^\d{4}$|^\d{9}$/, "Enter last 4 or full 9 digits")
    .nullable()
    .or(z.literal(""))
    .optional(),
  emergencyContactName: z.string().max(200).nullable().optional(),
  emergencyContactPhone: z.string().max(20).nullable().optional(),
  occupation: z.string().max(200).nullable().optional(),
  employer: z.string().max(200).nullable().optional(),
  referralSource: z.string().max(200).nullable().optional(),
  medicationsRaw: z.string().optional(),
  allergiesRaw: z.string().optional(),
  medicalAlertsRaw: z.string().optional(),
  smsOptOut: z.boolean().optional(),
  // Insurance (optional — only submitted if carrier is provided)
  insuranceCarrier: z.string().max(255).or(z.literal("")).optional(),
  insuranceMemberId: z.string().max(100).or(z.literal("")).optional(),
  insuranceGroupNumber: z.string().max(100).or(z.literal("")).optional(),
  insuranceRelationship: z.enum(["self", "spouse", "child", "other"]).nullable().optional(),
  insuredFirstName: z.string().max(100).or(z.literal("")).optional(),
  insuredLastName: z.string().max(100).or(z.literal("")).optional(),
  insuredDateOfBirth: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD")
    .or(z.literal(""))
    .optional(),
});

type FormValues = z.infer<typeof schema>;
type FormErrors = Partial<Record<keyof FormValues, string>>;

const EMPTY: FormValues = {
  firstName: "",
  lastName: "",
  dateOfBirth: "",
  sex: null,
  maritalStatus: null,
  phone: "",
  email: "",
  addressLine1: "",
  addressLine2: "",
  city: "",
  state: "",
  zip: "",
  ssn: "",
  emergencyContactName: "",
  emergencyContactPhone: "",
  occupation: "",
  employer: "",
  referralSource: "",
  medicationsRaw: "",
  allergiesRaw: "",
  medicalAlertsRaw: "",
  smsOptOut: false,
  insuranceCarrier: "",
  insuranceMemberId: "",
  insuranceGroupNumber: "",
  insuranceRelationship: null,
  insuredFirstName: "",
  insuredLastName: "",
  insuredDateOfBirth: "",
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function splitComma(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function NewPatientModal({ open, onOpenChange }: Props) {
  const router = useRouter();
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<FormErrors>({});

  const { mutateAsync: createPatient, error: mutationError } = useCreatePatient();
  const [isSubmitting, setIsSubmitting] = useState(false);

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function validate(): boolean {
    const result = schema.safeParse(values);
    if (result.success) {
      setErrors({});
      return true;
    }
    const errs: FormErrors = {};
    for (const issue of result.error.issues) {
      const key = issue.path[0] as keyof FormValues;
      if (!errs[key]) errs[key] = issue.message;
    }
    setErrors(errs);
    return false;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const body: CreatePatientBody = {
      firstName: values.firstName,
      lastName: values.lastName,
      dateOfBirth: values.dateOfBirth,
      sex: values.sex ?? null,
      maritalStatus: values.maritalStatus ?? null,
      phone: values.phone || null,
      email: values.email || null,
      addressLine1: values.addressLine1 || null,
      addressLine2: values.addressLine2 || null,
      city: values.city || null,
      state: values.state || null,
      zip: values.zip || null,
      ssn: values.ssn || null,
      emergencyContactName: values.emergencyContactName || null,
      emergencyContactPhone: values.emergencyContactPhone || null,
      occupation: values.occupation || null,
      employer: values.employer || null,
      referralSource: values.referralSource || null,
      medications: splitComma(values.medicationsRaw),
      allergies: splitComma(values.allergiesRaw),
      medicalAlerts: splitComma(values.medicalAlertsRaw),
      smsOptOut: values.smsOptOut ?? false,
    };

    setIsSubmitting(true);
    try {
      const patient = await createPatient(body);

      if (values.insuranceCarrier) {
        try {
          await createInsurance(patient.id, {
            carrier: values.insuranceCarrier,
            memberId: values.insuranceMemberId || null,
            groupNumber: values.insuranceGroupNumber || null,
            relationshipToInsured: values.insuranceRelationship ?? "self",
            insuredFirstName: values.insuredFirstName || null,
            insuredLastName: values.insuredLastName || null,
            insuredDateOfBirth: values.insuredDateOfBirth || null,
          });
        } catch {
          // Patient was created — navigate anyway; staff can add insurance from the profile.
        }
      }

      setValues(EMPTY);
      setErrors({});
      onOpenChange(false);
      router.push(`/patients/${patient.id}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      setValues(EMPTY);
      setErrors({});
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Patient</DialogTitle>
        </DialogHeader>

        <form onSubmit={(e) => { void handleSubmit(e); }} noValidate>
          <div className="grid gap-4 py-2 max-h-[65vh] overflow-y-auto pr-1">
            {/* Name */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="First name *" error={errors.firstName}>
                <Input
                  value={values.firstName}
                  onChange={(e) => set("firstName", e.target.value)}
                  placeholder="Jane"
                />
              </Field>
              <Field label="Last name *" error={errors.lastName}>
                <Input
                  value={values.lastName}
                  onChange={(e) => set("lastName", e.target.value)}
                  placeholder="Smith"
                />
              </Field>
            </div>

            {/* DOB + Sex */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="Date of birth *" error={errors.dateOfBirth}>
                <Input
                  type="date"
                  value={values.dateOfBirth}
                  onChange={(e) => set("dateOfBirth", e.target.value)}
                />
              </Field>
              <Field label="Sex" error={errors.sex}>
                <Select
                  value={values.sex ?? ""}
                  onValueChange={(v) =>
                    set("sex", v === "" ? null : (v as FormValues["sex"]))
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
              </Field>
            </div>

            {/* Marital status */}
            <Field label="Marital status" error={errors.maritalStatus}>
              <Select
                value={values.maritalStatus ?? ""}
                onValueChange={(v) =>
                  set("maritalStatus", v === "" ? null : (v as FormValues["maritalStatus"]))
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
            </Field>

            {/* Phone + Email */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="Phone" error={errors.phone}>
                <Input
                  value={values.phone ?? ""}
                  onChange={(e) => set("phone", e.target.value)}
                  placeholder="555-867-5309"
                />
              </Field>
              <Field label="Email" error={errors.email}>
                <Input
                  type="email"
                  value={values.email ?? ""}
                  onChange={(e) => set("email", e.target.value)}
                  placeholder="jane@example.com"
                />
              </Field>
            </div>

            {/* Address */}
            <Field label="Address" error={errors.addressLine1}>
              <Input
                value={values.addressLine1 ?? ""}
                onChange={(e) => set("addressLine1", e.target.value)}
                placeholder="123 Main St"
              />
            </Field>
            <Field label="Address line 2" error={errors.addressLine2}>
              <Input
                value={values.addressLine2 ?? ""}
                onChange={(e) => set("addressLine2", e.target.value)}
                placeholder="Apt 4B"
              />
            </Field>

            <div className="grid grid-cols-3 gap-4">
              <Field label="City" error={errors.city} className="col-span-1">
                <Input
                  value={values.city ?? ""}
                  onChange={(e) => set("city", e.target.value)}
                  placeholder="Boston"
                />
              </Field>
              <Field label="State" error={errors.state} className="col-span-1">
                <Input
                  value={values.state ?? ""}
                  onChange={(e) => set("state", e.target.value.toUpperCase())}
                  placeholder="MA"
                  maxLength={2}
                />
              </Field>
              <Field label="Zip" error={errors.zip} className="col-span-1">
                <Input
                  value={values.zip ?? ""}
                  onChange={(e) => set("zip", e.target.value)}
                  placeholder="02101"
                />
              </Field>
            </div>

            {/* SSN */}
            <Field label="SSN (last 4 or full 9 digits)" error={errors.ssn}>
              <Input
                value={values.ssn ?? ""}
                onChange={(e) => set("ssn", e.target.value)}
                placeholder="1234 or 123456789"
                maxLength={9}
                className="max-w-[12rem]"
              />
            </Field>

            {/* Emergency contact */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="Emergency contact name" error={errors.emergencyContactName}>
                <Input
                  value={values.emergencyContactName ?? ""}
                  onChange={(e) => set("emergencyContactName", e.target.value)}
                  placeholder="John Doe"
                />
              </Field>
              <Field label="Emergency contact phone" error={errors.emergencyContactPhone}>
                <Input
                  value={values.emergencyContactPhone ?? ""}
                  onChange={(e) => set("emergencyContactPhone", e.target.value)}
                  placeholder="555-555-5555"
                />
              </Field>
            </div>

            {/* Occupation / employer */}
            <div className="grid grid-cols-2 gap-4">
              <Field label="Occupation" error={errors.occupation}>
                <Input
                  value={values.occupation ?? ""}
                  onChange={(e) => set("occupation", e.target.value)}
                  placeholder="Software engineer"
                />
              </Field>
              <Field label="Employer / school" error={errors.employer}>
                <Input
                  value={values.employer ?? ""}
                  onChange={(e) => set("employer", e.target.value)}
                  placeholder="Acme Corp"
                />
              </Field>
            </div>

            {/* Referral source */}
            <Field label="How did they hear about us?" error={errors.referralSource}>
              <Input
                value={values.referralSource ?? ""}
                onChange={(e) => set("referralSource", e.target.value)}
                placeholder="Friend, Google, etc."
              />
            </Field>

            {/* Medications */}
            <Field
              label="Medications (comma-separated)"
              error={errors.medicationsRaw}
            >
              <Input
                value={values.medicationsRaw ?? ""}
                onChange={(e) => set("medicationsRaw", e.target.value)}
                placeholder="Lisinopril, Metformin"
              />
            </Field>

            {/* Allergies + Medical alerts */}
            <Field
              label="Allergies (comma-separated)"
              error={errors.allergiesRaw}
            >
              <Input
                value={values.allergiesRaw ?? ""}
                onChange={(e) => set("allergiesRaw", e.target.value)}
                placeholder="Penicillin, Latex"
              />
            </Field>
            <Field
              label="Medical alerts (comma-separated)"
              error={errors.medicalAlertsRaw}
            >
              <Input
                value={values.medicalAlertsRaw ?? ""}
                onChange={(e) => set("medicalAlertsRaw", e.target.value)}
                placeholder="Diabetic, Pacemaker"
              />
            </Field>

            {/* Insurance */}
            <div className="border-t pt-3">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Insurance (optional)
              </p>
              <div className="grid gap-4">
                <Field label="Carrier" error={errors.insuranceCarrier}>
                  <Input
                    value={values.insuranceCarrier ?? ""}
                    onChange={(e) => set("insuranceCarrier", e.target.value)}
                    placeholder="Delta Dental, Cigna…"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Member ID" error={errors.insuranceMemberId}>
                    <Input
                      value={values.insuranceMemberId ?? ""}
                      onChange={(e) => set("insuranceMemberId", e.target.value)}
                      placeholder="123456789"
                    />
                  </Field>
                  <Field label="Group #" error={errors.insuranceGroupNumber}>
                    <Input
                      value={values.insuranceGroupNumber ?? ""}
                      onChange={(e) => set("insuranceGroupNumber", e.target.value)}
                      placeholder="GRP001"
                    />
                  </Field>
                </div>
                <Field label="Relationship to insured" error={errors.insuranceRelationship}>
                  <Select
                    value={values.insuranceRelationship ?? "self"}
                    onValueChange={(v) =>
                      set("insuranceRelationship", v as FormValues["insuranceRelationship"])
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Self" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="self">Self</SelectItem>
                      <SelectItem value="spouse">Spouse</SelectItem>
                      <SelectItem value="child">Child</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                {values.insuranceRelationship && values.insuranceRelationship !== "self" && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Insured first name" error={errors.insuredFirstName}>
                        <Input
                          value={values.insuredFirstName ?? ""}
                          onChange={(e) => set("insuredFirstName", e.target.value)}
                          placeholder="John"
                        />
                      </Field>
                      <Field label="Insured last name" error={errors.insuredLastName}>
                        <Input
                          value={values.insuredLastName ?? ""}
                          onChange={(e) => set("insuredLastName", e.target.value)}
                          placeholder="Smith"
                        />
                      </Field>
                    </div>
                    <Field label="Insured date of birth" error={errors.insuredDateOfBirth}>
                      <Input
                        type="date"
                        value={values.insuredDateOfBirth ?? ""}
                        onChange={(e) => set("insuredDateOfBirth", e.target.value)}
                        className="max-w-[12rem]"
                      />
                    </Field>
                  </>
                )}
              </div>
            </div>

            {/* SMS opt-out */}
            <div className="flex items-center gap-2">
              <input
                id="smsOptOut"
                type="checkbox"
                checked={values.smsOptOut ?? false}
                onChange={(e) => set("smsOptOut", e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <Label htmlFor="smsOptOut" className="cursor-pointer">
                Opt out of SMS reminders
              </Label>
            </div>
          </div>

          {mutationError && (
            <p className="mt-2 text-sm text-destructive">
              {mutationError.message ?? "Failed to create patient. Please try again."}
            </p>
          )}

          <DialogFooter className="mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving…" : "Create patient"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface FieldProps {
  label: string;
  error?: string | undefined;
  children: React.ReactNode;
  className?: string | undefined;
}

function Field({ label, error, children, className }: FieldProps) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
