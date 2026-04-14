"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const INSURANCE_CARRIERS = [
  "Delta Dental",
  "MetLife",
  "Cigna",
  "Aetna",
  "Guardian",
  "United Concordia",
  "Humana",
  "BlueCross BlueShield",
  "Ameritas",
  "Principal Financial",
  "Sun Life",
  "MassHealth / DentaQuest",
  "Anthem",
  "Other",
];

const DENTAL_SYMPTOMS = [
  "Bad breath",
  "Grinding teeth",
  "Sensitivity to hot",
  "Bleeding gums",
  "Loose teeth or broken fillings",
  "Sensitivity to sweets",
  "Clicking or popping jaw",
  "Periodontal treatment",
  "Sensitivity when biting",
  "Food collection between teeth",
  "Sensitivity to cold",
  "Sores or growths in your mouth",
];

const MEDICAL_CONDITIONS = [
  "Anemia",
  "Arthritis / Rheumatism",
  "Artificial Heart Valves",
  "Artificial Joints",
  "Asthma",
  "Back Problems",
  "Blood Disease",
  "Cancer",
  "Chemical Dependency",
  "Chemotherapy",
  "Circulatory Problems",
  "Cortisone Treatments",
  "Cough, Persistent",
  "Cough up Blood",
  "Diabetes",
  "Epilepsy",
  "Fainting",
  "Glaucoma",
  "Headaches",
  "Heart Murmur",
  "Heart Problems",
  "Hemophilia",
  "Hepatitis",
  "High Blood Pressure",
  "HIV/AIDS",
  "Jaw Pain",
  "Kidney Disease",
  "Latex allergy",
  "Liver Disease",
  "Mitral Valve Prolapse",
  "Pacemaker",
  "Pregnancy",
  "Radiation Treatment",
  "Respiratory Disease",
  "Rheumatic Fever",
  "Scarlet Fever",
  "Shortness of Breath",
  "Skin Rash",
  "Stroke",
  "Swelling of Feet or Ankles",
  "Thyroid Problems",
  "Tobacco Habit",
  "Tonsillitis",
  "Tuberculosis",
  "Ulcer",
  "Venereal Disease",
];

// ── Types ─────────────────────────────────────────────────────────────────────

interface TokenInfo {
  practiceName: string;
  patientFirstName: string;
}

interface FormData {
  // Step 1: Personal info
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  sex: string;
  maritalStatus: string;
  phone: string;
  email: string;
  addressLine1: string;
  addressLine2: string;
  city: string;
  state: string;
  zip: string;
  ssn: string;
  emergencyContactName: string;
  emergencyContactPhone: string;
  occupation: string;
  employer: string;
  referralSource: string;
  // Step 2: Medical history
  medicalConditions: string[];
  medications: string; // newline-separated, split before submit
  allergies: string; // newline-separated, split before submit
  // Step 3: Dental history + insurance
  lastDentalVisit: string;
  lastXrayDate: string;
  previousDentist: string;
  chiefComplaint: string;
  dentalSymptoms: string[];
  insuranceCarrier: string;
  insuranceCarrierCustom: string;
  insuranceMemberId: string;
  insuranceGroupNumber: string;
  insuranceHolderName: string;
  insuranceHolderDob: string;
  relationshipToInsured: string;
  // Step 4: Consent
  hipaaConsentAccepted: boolean;
  hipaaConsentSignature: string;
  smsOptIn: boolean;
}

const emptyForm = (): FormData => ({
  firstName: "",
  lastName: "",
  dateOfBirth: "",
  sex: "",
  maritalStatus: "",
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
  medicalConditions: [],
  medications: "",
  allergies: "",
  lastDentalVisit: "",
  lastXrayDate: "",
  previousDentist: "",
  chiefComplaint: "",
  dentalSymptoms: [],
  insuranceCarrier: "",
  insuranceCarrierCustom: "",
  insuranceMemberId: "",
  insuranceGroupNumber: "",
  insuranceHolderName: "",
  insuranceHolderDob: "",
  relationshipToInsured: "",
  hipaaConsentAccepted: false,
  hipaaConsentSignature: "",
  smsOptIn: true,
});

// ── Step components ───────────────────────────────────────────────────────────

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-sm font-medium">
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children}
    </div>
  );
}

interface StepProps {
  form: FormData;
  onChange: (patch: Partial<FormData>) => void;
  error: string | null;
}

function Step1Personal({ form, onChange }: StepProps) {
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-4">
        <Field label="First name" required>
          <Input
            value={form.firstName}
            onChange={(e) => onChange({ firstName: e.target.value })}
            placeholder="Jane"
            autoComplete="given-name"
          />
        </Field>
        <Field label="Last name" required>
          <Input
            value={form.lastName}
            onChange={(e) => onChange({ lastName: e.target.value })}
            placeholder="Doe"
            autoComplete="family-name"
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Date of birth" required>
          <Input
            type="date"
            value={form.dateOfBirth}
            onChange={(e) => onChange({ dateOfBirth: e.target.value })}
            autoComplete="bday"
          />
        </Field>
        <Field label="Sex">
          <Select value={form.sex} onValueChange={(v) => onChange({ sex: v })}>
            <SelectTrigger>
              <SelectValue placeholder="Select…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="male">Male</SelectItem>
              <SelectItem value="female">Female</SelectItem>
              <SelectItem value="other">Other</SelectItem>
              <SelectItem value="unknown">Prefer not to say</SelectItem>
            </SelectContent>
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Phone" required>
          <Input
            value={form.phone}
            onChange={(e) => onChange({ phone: e.target.value })}
            placeholder="555-867-5309"
            type="tel"
            autoComplete="tel"
          />
        </Field>
        <Field label="Email">
          <Input
            value={form.email}
            onChange={(e) => onChange({ email: e.target.value })}
            placeholder="jane@example.com"
            type="email"
            autoComplete="email"
          />
        </Field>
      </div>
      <Field label="Address">
        <Input
          value={form.addressLine1}
          onChange={(e) => onChange({ addressLine1: e.target.value })}
          placeholder="123 Main St"
          autoComplete="address-line1"
        />
      </Field>
      <Field label="Address line 2">
        <Input
          value={form.addressLine2}
          onChange={(e) => onChange({ addressLine2: e.target.value })}
          placeholder="Apt 4B"
          autoComplete="address-line2"
        />
      </Field>
      <div className="grid grid-cols-3 gap-4">
        <Field label="City">
          <Input
            value={form.city}
            onChange={(e) => onChange({ city: e.target.value })}
            placeholder="Boston"
            autoComplete="address-level2"
          />
        </Field>
        <Field label="State">
          <Input
            value={form.state}
            onChange={(e) => onChange({ state: e.target.value.toUpperCase() })}
            placeholder="MA"
            maxLength={2}
            autoComplete="address-level1"
          />
        </Field>
        <Field label="Zip">
          <Input
            value={form.zip}
            onChange={(e) => onChange({ zip: e.target.value })}
            placeholder="02101"
            inputMode="numeric"
            autoComplete="postal-code"
          />
        </Field>
      </div>
      <Field label="SSN (last 4 or full 9 digits, optional)">
        <Input
          value={form.ssn}
          onChange={(e) => onChange({ ssn: e.target.value.replace(/\D/g, "").slice(0, 9) })}
          placeholder="1234 or 123456789"
          inputMode="numeric"
          maxLength={9}
          className="max-w-[12rem]"
          autoComplete="off"
        />
      </Field>
      <Field label="Marital status">
        <Select value={form.maritalStatus} onValueChange={(v) => onChange({ maritalStatus: v })}>
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
      <div className="grid grid-cols-2 gap-4">
        <Field label="Emergency contact name">
          <Input
            value={form.emergencyContactName}
            onChange={(e) => onChange({ emergencyContactName: e.target.value })}
            placeholder="John Doe"
          />
        </Field>
        <Field label="Emergency contact phone">
          <Input
            value={form.emergencyContactPhone}
            onChange={(e) => onChange({ emergencyContactPhone: e.target.value })}
            placeholder="555-555-5555"
            type="tel"
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Occupation">
          <Input
            value={form.occupation}
            onChange={(e) => onChange({ occupation: e.target.value })}
            placeholder="Software engineer"
          />
        </Field>
        <Field label="Employer / school">
          <Input
            value={form.employer}
            onChange={(e) => onChange({ employer: e.target.value })}
            placeholder="Acme Corp"
          />
        </Field>
      </div>
      <Field label="How did you hear about us?">
        <Input
          value={form.referralSource}
          onChange={(e) => onChange({ referralSource: e.target.value })}
          placeholder="Friend, Google, etc."
        />
      </Field>
    </div>
  );
}

function Step2Medical({ form, onChange }: StepProps) {
  function toggleCondition(condition: string) {
    const current = form.medicalConditions;
    onChange({
      medicalConditions: current.includes(condition)
        ? current.filter((c) => c !== condition)
        : [...current, condition],
    });
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="mb-3 text-sm font-medium">
          Do you have any of the following conditions? (check all that apply)
        </p>
        <div className="grid gap-2">
          {MEDICAL_CONDITIONS.map((condition) => (
            <label key={condition} className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={form.medicalConditions.includes(condition)}
                onChange={() => toggleCondition(condition)}
                className="h-4 w-4 rounded border-input"
              />
              <span className="text-sm">{condition}</span>
            </label>
          ))}
        </div>
      </div>
      <Field label="Current medications (one per line)">
        <textarea
          value={form.medications}
          onChange={(e) => onChange({ medications: e.target.value })}
          placeholder={"Lisinopril 10mg\nMetformin 500mg"}
          rows={4}
          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none"
        />
      </Field>
      <Field label="Allergies (one per line)">
        <textarea
          value={form.allergies}
          onChange={(e) => onChange({ allergies: e.target.value })}
          placeholder={"Penicillin\nLatex"}
          rows={3}
          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none"
        />
      </Field>
    </div>
  );
}

function Step3DentalInsurance({ form, onChange }: StepProps) {
  function toggleSymptom(symptom: string) {
    const current = form.dentalSymptoms;
    onChange({
      dentalSymptoms: current.includes(symptom)
        ? current.filter((s) => s !== symptom)
        : [...current, symptom],
    });
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-4">
        <p className="text-sm font-semibold">Dental history</p>
        <div className="grid grid-cols-2 gap-4">
          <Field label="When was your last dental visit?">
            <Input
              value={form.lastDentalVisit}
              onChange={(e) => onChange({ lastDentalVisit: e.target.value })}
              placeholder="About 1 year ago, or never"
            />
          </Field>
          <Field label="Date of last dental X-rays">
            <Input
              type="date"
              value={form.lastXrayDate}
              onChange={(e) => onChange({ lastXrayDate: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Previous dentist's name">
          <Input
            value={form.previousDentist}
            onChange={(e) => onChange({ previousDentist: e.target.value })}
            placeholder="Dr. Smith"
          />
        </Field>
        <Field label="Reason for today's visit / chief complaint">
          <textarea
            value={form.chiefComplaint}
            onChange={(e) => onChange({ chiefComplaint: e.target.value })}
            placeholder="Tooth pain, routine cleaning, etc."
            rows={3}
            className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none"
          />
        </Field>
      </div>
      <div className="grid gap-4">
        <p className="mb-1 text-sm font-semibold">Dental symptoms</p>
        <p className="text-sm text-muted-foreground">
          Are you experiencing any of the following? (check all that apply)
        </p>
        <div className="grid gap-2">
          {DENTAL_SYMPTOMS.map((symptom) => (
            <label key={symptom} className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={form.dentalSymptoms.includes(symptom)}
                onChange={() => toggleSymptom(symptom)}
                className="h-4 w-4 rounded border-input"
              />
              <span className="text-sm">{symptom}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-4">
        <p className="text-sm font-semibold">Dental insurance (if applicable)</p>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Insurance carrier">
            <Select
              value={form.insuranceCarrier}
              onValueChange={(v) =>
                onChange({ insuranceCarrier: v, insuranceCarrierCustom: "" })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Select carrier…" />
              </SelectTrigger>
              <SelectContent>
                {INSURANCE_CARRIERS.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.insuranceCarrier === "Other" && (
              <Input
                className="mt-2"
                value={form.insuranceCarrierCustom}
                onChange={(e) => onChange({ insuranceCarrierCustom: e.target.value })}
                placeholder="Enter carrier name"
              />
            )}
          </Field>
          <Field label="Member ID">
            <Input
              value={form.insuranceMemberId}
              onChange={(e) => onChange({ insuranceMemberId: e.target.value })}
              placeholder="00123456"
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Group number">
            <Input
              value={form.insuranceGroupNumber}
              onChange={(e) => onChange({ insuranceGroupNumber: e.target.value })}
              placeholder="GRP001"
            />
          </Field>
          <Field label="Relationship to insured">
            <Select
              value={form.relationshipToInsured}
              onValueChange={(v) => onChange({ relationshipToInsured: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="self">Self</SelectItem>
                <SelectItem value="spouse">Spouse</SelectItem>
                <SelectItem value="child">Child</SelectItem>
                <SelectItem value="other">Other</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
        {form.relationshipToInsured && form.relationshipToInsured !== "self" && (
          <div className="grid grid-cols-2 gap-4">
            <Field label="Insured's name">
              <Input
                value={form.insuranceHolderName}
                onChange={(e) => onChange({ insuranceHolderName: e.target.value })}
                placeholder="John Doe"
              />
            </Field>
            <Field label="Insured's date of birth">
              <Input
                type="date"
                value={form.insuranceHolderDob}
                onChange={(e) => onChange({ insuranceHolderDob: e.target.value })}
              />
            </Field>
          </div>
        )}
      </div>
    </div>
  );
}

function Step4Consent({ form, onChange }: StepProps) {
  return (
    <div className="grid gap-6">
      <div className="rounded-md border border-border bg-muted/40 p-4 text-sm leading-relaxed text-muted-foreground">
        <p className="mb-2 font-semibold text-foreground">HIPAA Notice of Privacy Practices</p>
        <p className="mb-2">
          This practice is required by law to maintain the privacy of your protected health
          information (PHI) and to provide you with notice of its legal duties and privacy
          practices with respect to PHI.
        </p>
        <p>
          Your health information may be used to provide treatment, obtain payment, and support
          healthcare operations. We will not disclose your information without your written
          authorization except as required by law.
        </p>
      </div>
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={form.hipaaConsentAccepted}
          onChange={(e) => onChange({ hipaaConsentAccepted: e.target.checked })}
          className="mt-0.5 h-4 w-4 rounded border-input"
        />
        <span className="text-sm">
          I acknowledge that I have received, read, and understood the Notice of Privacy Practices.{" "}
          <span className="text-destructive">*</span>
        </span>
      </label>
      <Field label="Signature (type your full name)" required>
        <Input
          value={form.hipaaConsentSignature}
          onChange={(e) => onChange({ hipaaConsentSignature: e.target.value })}
          placeholder="Jane Doe"
          autoComplete="name"
        />
      </Field>
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={form.smsOptIn}
          onChange={(e) => onChange({ smsOptIn: e.target.checked })}
          className="mt-0.5 h-4 w-4 rounded border-input"
        />
        <span className="text-sm">
          I consent to receiving appointment reminders and practice communications via SMS.
        </span>
      </label>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const STEP_TITLES = [
  "Personal Information",
  "Medical History",
  "Dental History & Insurance",
  "Review & Consent",
];

type PageState = "loading" | "ready" | "expired" | "completed" | "error" | "submitting";

export default function IntakeFormPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = params.token;

  const [pageState, setPageState] = useState<PageState>("loading");
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormData>(emptyForm());
  const [stepError, setStepError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    void (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/intake/form/${token}`);
        if (res.status === 410) {
          const body = (await res.json()) as { error: { code: string } };
          setPageState(body.error?.code === "INTAKE_COMPLETED" ? "completed" : "expired");
          return;
        }
        if (!res.ok) {
          setPageState("error");
          return;
        }
        const data = (await res.json()) as TokenInfo;
        setTokenInfo(data);
        setPageState("ready");
      } catch {
        setPageState("error");
      }
    })();
  }, [token]);

  function handleChange(patch: Partial<FormData>) {
    setForm((prev) => ({ ...prev, ...patch }));
    setStepError(null);
  }

  function validateStep(): string | null {
    if (step === 0) {
      if (!form.firstName.trim()) return "First name is required.";
      if (!form.lastName.trim()) return "Last name is required.";
      if (!form.dateOfBirth.trim()) return "Date of birth is required.";
      if (!/^\d{4}-\d{2}-\d{2}$/.test(form.dateOfBirth)) return "Date of birth must be in YYYY-MM-DD format.";
      if (!form.phone.trim()) return "Phone number is required.";
    }
    if (step === 3) {
      if (!form.hipaaConsentAccepted) return "You must accept the HIPAA consent to continue.";
      if (!form.hipaaConsentSignature.trim()) return "Signature is required.";
    }
    return null;
  }

  function handleNext() {
    const err = validateStep();
    if (err) {
      setStepError(err);
      return;
    }
    setStep((s) => s + 1);
  }

  async function handleSubmit() {
    const err = validateStep();
    if (err) {
      setStepError(err);
      return;
    }

    setPageState("submitting");
    setSubmitError(null);

    const payload = {
      firstName: form.firstName,
      lastName: form.lastName,
      dateOfBirth: form.dateOfBirth,
      sex: form.sex || undefined,
      maritalStatus: form.maritalStatus || undefined,
      phone: form.phone,
      email: form.email || undefined,
      addressLine1: form.addressLine1 || undefined,
      addressLine2: form.addressLine2 || undefined,
      city: form.city || undefined,
      state: form.state || undefined,
      zip: form.zip || undefined,
      ssn: form.ssn || undefined,
      emergencyContactName: form.emergencyContactName || undefined,
      emergencyContactPhone: form.emergencyContactPhone || undefined,
      occupation: form.occupation || undefined,
      employer: form.employer || undefined,
      referralSource: form.referralSource || undefined,
      medicalConditions: form.medicalConditions,
      medications: form.medications
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      allergies: form.allergies
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      lastDentalVisit: form.lastDentalVisit || undefined,
      lastXrayDate: form.lastXrayDate || undefined,
      previousDentist: form.previousDentist || undefined,
      chiefComplaint: form.chiefComplaint || undefined,
      dentalSymptoms: form.dentalSymptoms,
      insuranceCarrier: (form.insuranceCarrier === "Other" ? form.insuranceCarrierCustom : form.insuranceCarrier) || undefined,
      insuranceMemberId: form.insuranceMemberId || undefined,
      insuranceGroupNumber: form.insuranceGroupNumber || undefined,
      insuranceHolderName: form.insuranceHolderName || undefined,
      insuranceHolderDob: form.insuranceHolderDob || undefined,
      relationshipToInsured: form.relationshipToInsured || undefined,
      hipaaConsentAccepted: form.hipaaConsentAccepted,
      hipaaConsentTimestamp: new Date().toISOString(),
      hipaaConsentSignature: form.hipaaConsentSignature,
      smsOptIn: form.smsOptIn,
    };

    try {
      const res = await fetch(`${API_BASE_URL}/api/intake/form/${token}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.status === 410) {
        setPageState("expired");
        return;
      }
      if (!res.ok) {
        setPageState("ready");
        setSubmitError("There was a problem submitting your form. Please try again.");
        return;
      }
      router.push(`/intake/${token}/complete`);
    } catch {
      setPageState("ready");
      setSubmitError("Network error. Please check your connection and try again.");
    }
  }

  // ── Render states ─────────────────────────────────────────────────────────

  if (pageState === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (pageState === "expired") {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="pt-6">
            <p className="text-lg font-semibold">Link expired</p>
            <p className="mt-2 text-sm text-muted-foreground">
              This intake form link has expired or has already been submitted. Please contact
              your dental practice for a new link.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (pageState === "completed") {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="pt-6">
            <p className="text-lg font-semibold">Already submitted</p>
            <p className="mt-2 text-sm text-muted-foreground">
              This intake form has already been completed. See you at your appointment!
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (pageState === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="pt-6">
            <p className="text-lg font-semibold">Something went wrong</p>
            <p className="mt-2 text-sm text-muted-foreground">
              We couldn&apos;t load your intake form. Please try again or contact your dental practice.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isSubmitting = pageState === "submitting";

  const stepProps: StepProps = {
    form,
    onChange: handleChange,
    error: stepError,
  };

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <p className="text-sm text-muted-foreground">{tokenInfo?.practiceName}</p>
        <h1 className="text-2xl font-semibold tracking-tight">
          Hi {tokenInfo?.patientFirstName}, welcome!
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Please fill in the form below before your appointment.
        </p>
      </div>

      {/* Step indicator */}
      <div className="mb-6 flex gap-1">
        {STEP_TITLES.map((_, i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-primary" : "bg-muted"}`}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Step {step + 1} of {STEP_TITLES.length}: {STEP_TITLES[step]}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {step === 0 && <Step1Personal {...stepProps} />}
          {step === 1 && <Step2Medical {...stepProps} />}
          {step === 2 && <Step3DentalInsurance {...stepProps} />}
          {step === 3 && <Step4Consent {...stepProps} />}

          {(stepError ?? submitError) && (
            <p className="mt-4 text-sm text-destructive">{stepError ?? submitError}</p>
          )}
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="mt-4 flex justify-between gap-2">
        {step > 0 ? (
          <Button
            variant="outline"
            onClick={() => setStep((s) => s - 1)}
            disabled={isSubmitting}
            className="min-h-[44px]"
          >
            Back
          </Button>
        ) : (
          <div />
        )}
        {step < STEP_TITLES.length - 1 ? (
          <Button onClick={handleNext} className="min-h-[44px]">
            Next
          </Button>
        ) : (
          <Button onClick={() => void handleSubmit()} disabled={isSubmitting} className="min-h-[44px]">
            {isSubmitting ? "Submitting…" : "Submit"}
          </Button>
        )}
      </div>
    </div>
  );
}
