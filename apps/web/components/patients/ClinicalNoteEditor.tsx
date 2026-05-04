"use client";

import { useState } from "react";
import { PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  useCreateClinicalNote,
  useUpdateClinicalNote,
  useSignClinicalNote,
  type ClinicalNote,
  type CreateClinicalNoteBody,
  type UpdateClinicalNoteBody,
  type PatientTolerance,
  type TemplateType,
} from "@/lib/api/clinical-notes";
import { useProviders } from "@/lib/api/scheduling";
import {
  CLINICAL_NOTE_TEMPLATES,
  TEMPLATE_TYPE_OPTIONS,
} from "@/lib/clinical-note-templates";

interface ClinicalNoteEditorProps {
  patientId: string;
  open: boolean;
  onClose: () => void;
  /** When provided, the editor operates in edit/sign mode for an existing note. */
  existingNote?: ClinicalNote;
  /** Pre-fill from appointment context. */
  prefill?: {
    appointmentId?: string;
    providerId?: string;
    visitDate?: string;
  };
}

interface NoteFields {
  providerId: string;
  visitDate: string;
  templateType: TemplateType | "";
  chiefComplaint: string;
  anesthesia: string;
  patientTolerance: PatientTolerance | "";
  complications: string;
  treatmentRendered: string;
  nextVisitPlan: string;
  notes: string;
}

function fieldsFromNote(note: ClinicalNote): NoteFields {
  return {
    providerId: note.providerId,
    visitDate: note.visitDate,
    templateType: note.templateType ?? "",
    chiefComplaint: note.chiefComplaint ?? "",
    anesthesia: note.anesthesia ?? "",
    patientTolerance: note.patientTolerance ?? "",
    complications: note.complications ?? "",
    treatmentRendered: note.treatmentRendered,
    nextVisitPlan: note.nextVisitPlan ?? "",
    notes: note.notes ?? "",
  };
}

function defaultFields(prefill?: ClinicalNoteEditorProps["prefill"]): NoteFields {
  return {
    providerId: prefill?.providerId ?? "",
    visitDate: prefill?.visitDate ?? new Date().toISOString().slice(0, 10),
    templateType: "",
    chiefComplaint: "",
    anesthesia: "",
    patientTolerance: "",
    complications: "",
    treatmentRendered: "",
    nextVisitPlan: "",
    notes: "",
  };
}

export function ClinicalNoteEditor({
  patientId,
  open,
  onClose,
  existingNote,
  prefill,
}: ClinicalNoteEditorProps) {
  const isEdit = Boolean(existingNote);
  const isSigned = existingNote?.isSigned ?? false;

  const [fields, setFields] = useState<NoteFields>(() =>
    existingNote ? fieldsFromNote(existingNote) : defaultFields(prefill),
  );
  const [error, setError] = useState<string | null>(null);
  const [showSignConfirm, setShowSignConfirm] = useState(false);

  const { data: providers } = useProviders();
  const { mutate: createNote, isPending: isCreating } = useCreateClinicalNote(patientId);
  const { mutate: updateNote, isPending: isUpdating } = useUpdateClinicalNote(
    patientId,
    existingNote?.id ?? "",
  );
  const { mutate: signNote, isPending: isSigning } = useSignClinicalNote(
    patientId,
    existingNote?.id ?? "",
  );

  const isSaving = isCreating || isUpdating;

  function applyTemplate(type: TemplateType) {
    const tpl = CLINICAL_NOTE_TEMPLATES[type];
    setFields((prev) => ({
      ...prev,
      templateType: type,
      chiefComplaint: tpl.chiefComplaint,
      anesthesia: tpl.anesthesia,
      treatmentRendered: tpl.treatmentRendered,
    }));
  }

  function handleSave() {
    if (!fields.treatmentRendered.trim()) {
      setError("Treatment rendered is required.");
      return;
    }
    if (!fields.visitDate) {
      setError("Visit date is required.");
      return;
    }
    if (!fields.providerId.trim()) {
      setError("Provider ID is required.");
      return;
    }
    setError(null);

    if (isEdit && existingNote) {
      const updateBody: UpdateClinicalNoteBody = {
        treatmentRendered: fields.treatmentRendered,
      };
      if (fields.chiefComplaint) updateBody.chiefComplaint = fields.chiefComplaint;
      if (fields.anesthesia) updateBody.anesthesia = fields.anesthesia;
      if (fields.patientTolerance) updateBody.patientTolerance = fields.patientTolerance;
      if (fields.complications) updateBody.complications = fields.complications;
      if (fields.nextVisitPlan) updateBody.nextVisitPlan = fields.nextVisitPlan;
      if (fields.notes) updateBody.notes = fields.notes;
      if (fields.templateType) updateBody.templateType = fields.templateType;

      updateNote(updateBody, {
        onSuccess: onClose,
        onError: () => setError("Failed to save. Please try again."),
      });
    } else {
      const createBody: CreateClinicalNoteBody = {
        providerId: fields.providerId,
        visitDate: fields.visitDate,
        treatmentRendered: fields.treatmentRendered,
      };
      if (prefill?.appointmentId) createBody.appointmentId = prefill.appointmentId;
      if (fields.chiefComplaint) createBody.chiefComplaint = fields.chiefComplaint;
      if (fields.anesthesia) createBody.anesthesia = fields.anesthesia;
      if (fields.patientTolerance) createBody.patientTolerance = fields.patientTolerance;
      if (fields.complications) createBody.complications = fields.complications;
      if (fields.nextVisitPlan) createBody.nextVisitPlan = fields.nextVisitPlan;
      if (fields.notes) createBody.notes = fields.notes;
      if (fields.templateType) createBody.templateType = fields.templateType;

      createNote(createBody, {
        onSuccess: onClose,
        onError: () => setError("Failed to save. Please try again."),
      });
    }
  }

  function handleSign() {
    signNote(undefined, {
      onSuccess: onClose,
      onError: () => setError("Failed to sign note. Please try again."),
    });
  }

  function set(key: keyof NoteFields, value: string) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  const readOnly = isSigned;

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-2xl">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <DialogTitle>
                {isSigned ? "Clinical Note (Signed)" : isEdit ? "Edit Note" : "New Clinical Note"}
              </DialogTitle>
              {isSigned && (
                <Badge variant="secondary" className="gap-1">
                  <PenLine className="h-3 w-3" />
                  Signed
                </Badge>
              )}
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto">
            <div className="grid gap-4 py-2">
              {/* Template picker — only shown when creating or editing unsigned notes */}
              {!readOnly && (
                <div>
                  <Label className="mb-1 block text-xs text-muted-foreground">Template</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {TEMPLATE_TYPE_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => applyTemplate(opt.value)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                          fields.templateType === opt.value
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-background hover:bg-accent"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <Field label="Visit date *">
                  <Input
                    type="date"
                    value={fields.visitDate}
                    onChange={(e) => set("visitDate", e.target.value)}
                    disabled={readOnly || isEdit}
                  />
                </Field>
                <Field label="Provider *">
                  <Select
                    value={fields.providerId}
                    onValueChange={(v) => set("providerId", v)}
                    disabled={readOnly || isEdit}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {(providers ?? []).map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.fullName}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>

              <Field label="Chief complaint">
                <Input
                  value={fields.chiefComplaint}
                  onChange={(e) => set("chiefComplaint", e.target.value)}
                  placeholder="Patient's primary complaint"
                  disabled={readOnly}
                />
              </Field>

              <div className="grid grid-cols-2 gap-4">
                <Field label="Anesthesia">
                  <Input
                    value={fields.anesthesia}
                    onChange={(e) => set("anesthesia", e.target.value)}
                    placeholder="e.g. Lidocaine 2% 1:100k, 1.7mL"
                    disabled={readOnly}
                  />
                </Field>
                <Field label="Patient tolerance">
                  <Select
                    value={fields.patientTolerance}
                    onValueChange={(v) => set("patientTolerance", v)}
                    disabled={readOnly}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select…" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="excellent">Excellent</SelectItem>
                      <SelectItem value="good">Good</SelectItem>
                      <SelectItem value="fair">Fair</SelectItem>
                      <SelectItem value="poor">Poor</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>

              <Field label="Complications">
                <Input
                  value={fields.complications}
                  onChange={(e) => set("complications", e.target.value)}
                  placeholder="None, or describe"
                  disabled={readOnly}
                />
              </Field>

              <Field label="Treatment rendered *">
                <Textarea
                  value={fields.treatmentRendered}
                  onChange={(e) => set("treatmentRendered", e.target.value)}
                  rows={5}
                  placeholder="Describe all procedures performed…"
                  disabled={readOnly}
                  className="resize-y"
                />
              </Field>

              <Field label="Next visit plan">
                <Textarea
                  value={fields.nextVisitPlan}
                  onChange={(e) => set("nextVisitPlan", e.target.value)}
                  rows={2}
                  placeholder="Plan for next appointment"
                  disabled={readOnly}
                  className="resize-y"
                />
              </Field>

              <Field label="Additional notes">
                <Textarea
                  value={fields.notes}
                  onChange={(e) => set("notes", e.target.value)}
                  rows={2}
                  placeholder="Free-form notes"
                  disabled={readOnly}
                  className="resize-y"
                />
              </Field>

              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </div>

          <div className="flex justify-between border-t pt-4">
            <Button variant="outline" onClick={onClose} disabled={isSaving || isSigning}>
              {readOnly ? "Close" : "Cancel"}
            </Button>
            {!readOnly && (
              <div className="flex gap-2">
                <Button onClick={handleSave} disabled={isSaving}>
                  {isSaving ? "Saving…" : isEdit ? "Save changes" : "Save note"}
                </Button>
                {isEdit && (
                  <Button
                    variant="secondary"
                    onClick={() => setShowSignConfirm(true)}
                    disabled={isSaving || isSigning}
                  >
                    <PenLine className="mr-1.5 h-4 w-4" />
                    Sign note
                  </Button>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showSignConfirm} onOpenChange={setShowSignConfirm}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Sign this note?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Signing locks the note permanently. It cannot be edited after signing.
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setShowSignConfirm(false)}
              disabled={isSigning}
            >
              Cancel
            </Button>
            <Button onClick={handleSign} disabled={isSigning}>
              {isSigning ? "Signing…" : "Yes, sign note"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Field({
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
