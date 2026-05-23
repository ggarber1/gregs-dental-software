"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, PenLine } from "lucide-react";
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
  signClinicalNote,
  useCreateClinicalNote,
  useUpdateClinicalNote,
  useSignClinicalNote,
  type ClinicalNote,
  type CreateClinicalNoteBody,
  type UpdateClinicalNoteBody,
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

export interface NoteFields {
  providerId: string;
  visitDate: string;
  templateType: TemplateType | "";
  treatmentRendered: string;
}

/** Read-only snapshot of the deprecated multi-field structure, surfaced on
 * existing notes whose data predates the single-textbox redesign. */
export interface LegacyFields {
  chiefComplaint: string | null;
  anesthesia: string | null;
  patientTolerance: string | null;
  complications: string | null;
  nextVisitPlan: string | null;
  notes: string | null;
}

export function legacyFieldsFromNote(note: ClinicalNote): LegacyFields {
  return {
    chiefComplaint: note.chiefComplaint,
    anesthesia: note.anesthesia,
    patientTolerance: note.patientTolerance,
    complications: note.complications,
    nextVisitPlan: note.nextVisitPlan,
    notes: note.notes,
  };
}

export function hasLegacyFields(note: ClinicalNote | undefined): boolean {
  if (!note) return false;
  const f = legacyFieldsFromNote(note);
  return Boolean(
    (f.chiefComplaint && f.chiefComplaint.trim()) ||
      (f.anesthesia && f.anesthesia.trim()) ||
      (f.patientTolerance && f.patientTolerance.trim()) ||
      (f.complications && f.complications.trim()) ||
      (f.nextVisitPlan && f.nextVisitPlan.trim()) ||
      (f.notes && f.notes.trim()),
  );
}

export type ValidationResult =
  | { ok: true }
  | { ok: false; error: string };

export function validateFields(fields: NoteFields): ValidationResult {
  if (!fields.treatmentRendered.trim()) {
    return { ok: false, error: "Treatment rendered is required." };
  }
  if (!fields.visitDate) {
    return { ok: false, error: "Visit date is required." };
  }
  if (!fields.providerId.trim()) {
    return { ok: false, error: "Provider is required." };
  }
  return { ok: true };
}

export function buildCreateBody(
  fields: NoteFields,
  appointmentId?: string,
): CreateClinicalNoteBody {
  const body: CreateClinicalNoteBody = {
    providerId: fields.providerId,
    visitDate: fields.visitDate,
    treatmentRendered: fields.treatmentRendered,
  };
  if (appointmentId) body.appointmentId = appointmentId;
  if (fields.templateType) body.templateType = fields.templateType;
  return body;
}

function fieldsFromNote(note: ClinicalNote): NoteFields {
  return {
    providerId: note.providerId,
    visitDate: note.visitDate,
    templateType: note.templateType ?? "",
    treatmentRendered: note.treatmentRendered,
  };
}

function defaultFields(prefill?: ClinicalNoteEditorProps["prefill"]): NoteFields {
  return {
    providerId: prefill?.providerId ?? "",
    visitDate: prefill?.visitDate ?? new Date().toISOString().slice(0, 10),
    templateType: "",
    treatmentRendered: "",
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
  const [isSavingAndSigning, setIsSavingAndSigning] = useState(false);
  const [legacyOpen, setLegacyOpen] = useState(false);

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

  const isSaving = isCreating || isUpdating || isSavingAndSigning;
  const showLegacySection = hasLegacyFields(existingNote);

  function applyTemplate(type: TemplateType) {
    const tpl = CLINICAL_NOTE_TEMPLATES[type];
    setFields((prev) => ({
      ...prev,
      templateType: type,
      treatmentRendered: tpl.body,
    }));
  }

  function validate(): boolean {
    const result = validateFields(fields);
    if (!result.ok) {
      setError(result.error);
      return false;
    }
    setError(null);
    return true;
  }

  function handleSave() {
    if (!validate()) return;

    if (isEdit && existingNote) {
      const updateBody: UpdateClinicalNoteBody = {
        treatmentRendered: fields.treatmentRendered,
      };
      if (fields.templateType) updateBody.templateType = fields.templateType;

      updateNote(updateBody, {
        onSuccess: onClose,
        onError: () => setError("Failed to save. Please try again."),
      });
    } else {
      createNote(buildCreateBody(fields, prefill?.appointmentId), {
        onSuccess: onClose,
        onError: () => setError("Failed to save. Please try again."),
      });
    }
  }

  async function handleSaveAndSign() {
    if (!validate()) return;
    setIsSavingAndSigning(true);
    try {
      const note = await new Promise<ClinicalNote>((resolve, reject) => {
        createNote(buildCreateBody(fields, prefill?.appointmentId), {
          onSuccess: resolve,
          onError: reject,
        });
      });
      await signClinicalNote(patientId, note.id);
      onClose();
    } catch {
      setError("Failed to save and sign. Please try again.");
    } finally {
      setIsSavingAndSigning(false);
    }
  }

  function handleSign() {
    signNote(undefined, {
      onSuccess: onClose,
      onError: () => setError("Failed to sign note. Please try again."),
    });
  }

  function set<K extends keyof NoteFields>(key: K, value: NoteFields[K]) {
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

              <Field label="Note *">
                <Textarea
                  value={fields.treatmentRendered}
                  onChange={(e) => set("treatmentRendered", e.target.value)}
                  rows={12}
                  placeholder="Describe the visit. Pick a template above to insert a starting block."
                  disabled={readOnly}
                  className="resize-y font-mono text-sm"
                />
              </Field>

              {showLegacySection && existingNote && (
                <LegacyFieldsSection
                  fields={legacyFieldsFromNote(existingNote)}
                  open={legacyOpen}
                  onToggle={() => setLegacyOpen((p) => !p)}
                />
              )}

              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </div>

          <div className="flex justify-between border-t pt-4">
            <Button variant="outline" onClick={onClose} disabled={isSaving || isSigning}>
              {readOnly ? "Close" : "Cancel"}
            </Button>
            {!readOnly && (
              <div className="flex gap-2">
                <Button onClick={handleSave} disabled={isSaving || isSigning}>
                  {isCreating ? "Saving…" : isEdit ? "Save changes" : "Save draft"}
                </Button>
                {!isEdit && (
                  <Button
                    variant="secondary"
                    onClick={() => void handleSaveAndSign()}
                    disabled={isSaving || isSigning}
                  >
                    <PenLine className="mr-1.5 h-4 w-4" />
                    {isSavingAndSigning ? "Signing…" : "Save & Sign"}
                  </Button>
                )}
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

function LegacyFieldsSection({
  fields,
  open,
  onToggle,
}: {
  fields: LegacyFields;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-md border border-dashed border-border bg-muted/30">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:bg-accent/30"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        Legacy fields (from older note format, read-only)
      </button>
      {open && (
        <dl className="grid gap-2 px-3 pb-3 pt-1 text-sm">
          {fields.chiefComplaint && (
            <LegacyRow label="Chief complaint" value={fields.chiefComplaint} />
          )}
          {fields.anesthesia && (
            <LegacyRow label="Anesthesia" value={fields.anesthesia} />
          )}
          {fields.patientTolerance && (
            <LegacyRow label="Patient tolerance" value={fields.patientTolerance} />
          )}
          {fields.complications && (
            <LegacyRow label="Complications" value={fields.complications} />
          )}
          {fields.nextVisitPlan && (
            <LegacyRow label="Next visit plan" value={fields.nextVisitPlan} />
          )}
          {fields.notes && <LegacyRow label="Additional notes" value={fields.notes} />}
        </dl>
      )}
    </div>
  );
}

function LegacyRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 whitespace-pre-wrap">{value}</dd>
    </div>
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
