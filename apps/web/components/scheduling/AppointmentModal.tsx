"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
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
import { Textarea } from "@/components/ui/textarea";
import { usePatients, type Patient } from "@/lib/api/patients";
import {
  useAppointment,
  useAppointmentTypes,
  useProviders,
  useOperatories,
  useCreateAppointment,
  useUpdateAppointment,
  type Appointment,
  type CreateAppointmentBody,
  type UpdateAppointmentBody,
} from "@/lib/api/scheduling";
import { AppointmentStatusActions } from "@/components/scheduling/AppointmentStatusActions";
import { ApiError } from "@/lib/api-client";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-fill values from calendar click */
  defaultDate?: string | undefined; // YYYY-MM-DD
  defaultStartTime?: string | undefined; // HH:mm
  defaultOperatoryId?: string | undefined;
  /** If set, we're editing an existing appointment */
  appointment?: Appointment | null | undefined;
}

interface FormValues {
  patientId: string;
  patientSearch: string;
  appointmentTypeId: string;
  providerId: string;
  operatoryId: string;
  date: string;
  startTime: string;
  endTime: string;
  notes: string;
}

const EMPTY: FormValues = {
  patientId: "",
  patientSearch: "",
  appointmentTypeId: "",
  providerId: "",
  operatoryId: "",
  date: "",
  startTime: "",
  endTime: "",
  notes: "",
};

function addMinutesToTime(time: string, minutes: number): string {
  const parts = time.split(":").map(Number);
  const h = parts[0] ?? 0;
  const m = parts[1] ?? 0;
  const total = h * 60 + m + minutes;
  const newH = Math.floor(total / 60) % 24;
  const newM = total % 60;
  return `${String(newH).padStart(2, "0")}:${String(newM).padStart(2, "0")}`;
}

function isoToDate(iso: string): string {
  return iso.slice(0, 10);
}

function isoToTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function AppointmentModal({
  open,
  onOpenChange,
  defaultDate,
  defaultStartTime,
  defaultOperatoryId,
  appointment,
}: Props) {
  const isEditing = Boolean(appointment);

  // Fetch live data so status updates reflect immediately
  const { data: liveAppointment } = useAppointment(appointment?.id ?? "");
  const currentAppointment = liveAppointment ?? appointment;

  const { data: appointmentTypes } = useAppointmentTypes();
  const { data: providers } = useProviders();
  const { data: operatories } = useOperatories();

  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof FormValues, string>>>({});
  const [apiErrorMessage, setApiErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Patient search
  const [showPatientDropdown, setShowPatientDropdown] = useState(false);
  const [patientSearchQuery, setPatientSearchQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { data: patientResults } = usePatients({
    q: patientSearchQuery,
    pageSize: 8,
  });
  const dropdownRef = useRef<HTMLDivElement>(null);

  const createMutation = useCreateAppointment();
  const updateMutation = useUpdateAppointment();

  const activeProviders = providers?.filter((p) => p.isActive) ?? [];
  const activeOperatories = operatories?.filter((o) => o.isActive) ?? [];
  const activeTypes = appointmentTypes?.filter((t) => t.isActive) ?? [];

  // Reset form when modal opens
  useEffect(() => {
    if (!open) return;
    setErrors({});
    setApiErrorMessage(null);

    if (appointment) {
      setValues({
        patientId: appointment.patientId ?? "",
        patientSearch: appointment.patientName ?? "",
        appointmentTypeId: appointment.appointmentTypeId ?? "",
        providerId: appointment.providerId ?? "",
        operatoryId: appointment.operatoryId ?? "",
        date: isoToDate(appointment.startTime),
        startTime: isoToTime(appointment.startTime),
        endTime: isoToTime(appointment.endTime),
        notes: appointment.notes ?? "",
      });
    } else {
      const today = new Date().toISOString().slice(0, 10);
      setValues({
        ...EMPTY,
        date: defaultDate ?? today,
        startTime: defaultStartTime ?? "09:00",
        endTime: defaultStartTime ? addMinutesToTime(defaultStartTime, 30) : "09:30",
        operatoryId: defaultOperatoryId ?? "",
      });
    }
  }, [open, appointment, defaultDate, defaultStartTime, defaultOperatoryId]);

  // Close patient dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPatientDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
    setApiErrorMessage(null);
  }

  const handlePatientSearchChange = useCallback(
    (val: string) => {
      set("patientSearch", val);
      set("patientId", "");
      setShowPatientDropdown(true);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        setPatientSearchQuery(val);
      }, 300);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  function selectPatient(patient: Patient) {
    set("patientId", patient.id);
    set("patientSearch", `${patient.firstName} ${patient.lastName}`);
    setShowPatientDropdown(false);
  }

  function handleTypeChange(typeId: string) {
    set("appointmentTypeId", typeId);
    const apptType = activeTypes.find((t) => t.id === typeId);
    if (apptType && values.startTime) {
      set("endTime", addMinutesToTime(values.startTime, apptType.durationMinutes));
    }
  }

  function handleStartTimeChange(time: string) {
    set("startTime", time);
    if (values.appointmentTypeId) {
      const apptType = activeTypes.find((t) => t.id === values.appointmentTypeId);
      if (apptType) {
        set("endTime", addMinutesToTime(time, apptType.durationMinutes));
      }
    }
  }

  function validate(): boolean {
    const errs: Partial<Record<keyof FormValues, string>> = {};
    if (!isEditing && !values.patientId) errs.patientSearch = "Select a patient";
    if (!values.providerId) errs.providerId = "Required";
    if (!values.operatoryId) errs.operatoryId = "Required";
    if (!values.date) errs.date = "Required";
    if (!values.startTime) errs.startTime = "Required";
    if (!values.endTime) errs.endTime = "Required";
    if (values.startTime && values.endTime && values.startTime >= values.endTime) {
      errs.endTime = "Must be after start time";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setIsSubmitting(true);
    setApiErrorMessage(null);

    const startTimeISO = new Date(`${values.date}T${values.startTime}:00`).toISOString();
    const endTimeISO = new Date(`${values.date}T${values.endTime}:00`).toISOString();

    try {
      if (isEditing && appointment) {
        const updateBody: UpdateAppointmentBody = {
          providerId: values.providerId,
          operatoryId: values.operatoryId,
          startTime: startTimeISO,
          endTime: endTimeISO,
        };
        if (values.patientId) updateBody.patientId = values.patientId;
        if (values.appointmentTypeId) updateBody.appointmentTypeId = values.appointmentTypeId;
        if (values.notes) updateBody.notes = values.notes;
        await updateMutation.mutateAsync({
          id: appointment.id,
          body: updateBody,
        });
      } else {
        const body: CreateAppointmentBody = {
          patientId: values.patientId,
          providerId: values.providerId,
          operatoryId: values.operatoryId,
          startTime: startTimeISO,
          endTime: endTimeISO,
        };
        if (values.appointmentTypeId) body.appointmentTypeId = values.appointmentTypeId;
        if (values.notes) body.notes = values.notes;
        await createMutation.mutateAsync(body);
      }
      onOpenChange(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const body = err.body as { error?: { message?: string; details?: { conflicts?: Array<{ type: string; resourceId: string }> } } };
        const conflicts = body?.error?.details?.conflicts;
        if (conflicts && conflicts.length > 0) {
          const descriptions = conflicts.map((c) => {
            if (c.type === "provider") return "Provider is already booked at this time";
            if (c.type === "operatory") return "Operatory is already booked at this time";
            return "Scheduling conflict";
          });
          setApiErrorMessage(descriptions.join(". "));
        } else {
          setApiErrorMessage(body?.error?.message ?? "Scheduling conflict");
        }
      } else if (err instanceof ApiError) {
        const body = err.body as { error?: { message?: string } };
        setApiErrorMessage(body?.error?.message ?? `Error (${err.status})`);
      } else {
        setApiErrorMessage("An unexpected error occurred");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Edit Appointment" : "New Appointment"}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Status actions (edit mode only) */}
          {isEditing && currentAppointment && (
            <div>
              <Label>Status</Label>
              <div className="mt-1">
                <AppointmentStatusActions appointment={currentAppointment} />
              </div>
            </div>
          )}

          {/* Patient search */}
          {!isEditing && (
            <div className="relative" ref={dropdownRef}>
              <Label htmlFor="patient-search">Patient</Label>
              <Input
                id="patient-search"
                value={values.patientSearch}
                onChange={(e) => handlePatientSearchChange(e.target.value)}
                onFocus={() => values.patientSearch && setShowPatientDropdown(true)}
                placeholder="Search by name..."
                autoComplete="off"
              />
              {errors.patientSearch && (
                <p className="mt-1 text-xs text-destructive">{errors.patientSearch}</p>
              )}
              {showPatientDropdown && (patientResults?.data?.length ?? 0) > 0 && (
                <div className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md">
                  {patientResults!.data.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
                      onClick={() => selectPatient(p)}
                    >
                      <span className="font-medium">
                        {p.firstName} {p.lastName}
                      </span>
                      <span className="text-muted-foreground">
                        DOB: {p.dateOfBirth}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {isEditing && appointment?.patientName && (
            <div>
              <Label>Patient</Label>
              <p className="mt-1 text-sm font-medium">{appointment.patientName}</p>
            </div>
          )}

          {/* Appointment Type */}
          <div>
            <Label htmlFor="appointment-type">Appointment Type</Label>
            <Select value={values.appointmentTypeId} onValueChange={handleTypeChange}>
              <SelectTrigger id="appointment-type">
                <SelectValue placeholder="Select type (optional)" />
              </SelectTrigger>
              <SelectContent>
                {activeTypes.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block h-3 w-3 rounded-full"
                        style={{ backgroundColor: t.color }}
                      />
                      {t.name} ({t.durationMinutes}m)
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Provider */}
          <div>
            <Label htmlFor="provider">Provider</Label>
            <Select value={values.providerId} onValueChange={(v) => set("providerId", v)}>
              <SelectTrigger id="provider">
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {activeProviders.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.fullName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.providerId && (
              <p className="mt-1 text-xs text-destructive">{errors.providerId}</p>
            )}
          </div>

          {/* Operatory */}
          <div>
            <Label htmlFor="operatory">Operatory</Label>
            <Select value={values.operatoryId} onValueChange={(v) => set("operatoryId", v)}>
              <SelectTrigger id="operatory">
                <SelectValue placeholder="Select operatory" />
              </SelectTrigger>
              <SelectContent>
                {activeOperatories.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.operatoryId && (
              <p className="mt-1 text-xs text-destructive">{errors.operatoryId}</p>
            )}
          </div>

          {/* Date + Time */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="date">Date</Label>
              <Input
                id="date"
                type="date"
                value={values.date}
                onChange={(e) => set("date", e.target.value)}
              />
              {errors.date && <p className="mt-1 text-xs text-destructive">{errors.date}</p>}
            </div>
            <div>
              <Label htmlFor="start-time">Start</Label>
              <Input
                id="start-time"
                type="time"
                value={values.startTime}
                onChange={(e) => handleStartTimeChange(e.target.value)}
              />
              {errors.startTime && (
                <p className="mt-1 text-xs text-destructive">{errors.startTime}</p>
              )}
            </div>
            <div>
              <Label htmlFor="end-time">End</Label>
              <Input
                id="end-time"
                type="time"
                value={values.endTime}
                onChange={(e) => set("endTime", e.target.value)}
              />
              {errors.endTime && (
                <p className="mt-1 text-xs text-destructive">{errors.endTime}</p>
              )}
            </div>
          </div>

          {/* Notes */}
          <div>
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              value={values.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Optional notes..."
              rows={2}
            />
          </div>

          {/* API error */}
          {apiErrorMessage && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {apiErrorMessage}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={isSubmitting}>
            {isSubmitting ? "Saving..." : isEditing ? "Update" : "Book Appointment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
