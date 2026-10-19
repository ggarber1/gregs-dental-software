import {
  prefillFeeDollars,
  type CdtCode,
  type CreateAppointmentProcedureBody,
  type EstimateSource,
} from "@/lib/api/procedures";

/** Form state for the "add procedure" row in ProceduresSection. */
export interface DraftProcedure {
  /** Set only when a catalog code was picked; cleared once the code text is edited. */
  cdtCodeId: string | null;
  procedureCode: string;
  procedureName: string;
  toothNumber: string;
  surface: string;
  fee: string;
  insuranceEst: string;
  patientEst: string;
  estimateSource: EstimateSource | "";
  notes: string;
}

export const EMPTY_DRAFT: DraftProcedure = {
  cdtCodeId: null,
  procedureCode: "",
  procedureName: "",
  toothNumber: "",
  surface: "",
  fee: "",
  insuranceEst: "",
  patientEst: "",
  estimateSource: "",
  notes: "",
};

function dollarsToCents(value: string): number {
  return Math.round(parseFloat(value) * 100);
}

/** Typing in the code box breaks any previously picked catalog link. */
export function withCodeText(draft: DraftProcedure, value: string): DraftProcedure {
  return { ...draft, procedureCode: value, cdtCodeId: null };
}

/** Picking a catalog code fills code, name, fee, and the catalog link. */
export function withCatalogCode(draft: DraftProcedure, code: CdtCode): DraftProcedure {
  return {
    ...draft,
    cdtCodeId: code.id,
    procedureCode: code.code,
    procedureName: code.description,
    fee: prefillFeeDollars(draft.fee, code.resolvedFeeCents),
  };
}

export function buildCreateProcedureBody(draft: DraftProcedure): CreateAppointmentProcedureBody {
  const body: CreateAppointmentProcedureBody = {
    procedureCode: draft.procedureCode.trim(),
    procedureName: draft.procedureName.trim(),
    feeCents: dollarsToCents(draft.fee),
  };
  if (draft.cdtCodeId) body.cdtCodeId = draft.cdtCodeId;
  if (draft.toothNumber.trim()) body.toothNumber = draft.toothNumber.trim();
  if (draft.surface.trim()) body.surface = draft.surface.trim();
  if (draft.insuranceEst.trim()) body.insuranceEstCents = dollarsToCents(draft.insuranceEst);
  if (draft.patientEst.trim()) body.patientEstCents = dollarsToCents(draft.patientEst);
  if (draft.estimateSource) body.estimateSource = draft.estimateSource;
  if (draft.notes.trim()) body.notes = draft.notes.trim();
  return body;
}
