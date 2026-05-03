import type { TemplateType } from "@/lib/api/clinical-notes";

export interface NoteTemplate {
  type: TemplateType;
  label: string;
  chiefComplaint: string;
  anesthesia: string;
  treatmentRendered: string;
}

export const CLINICAL_NOTE_TEMPLATES: Record<TemplateType, NoteTemplate> = {
  exam: {
    type: "exam",
    label: "Exam",
    chiefComplaint: "Routine examination",
    anesthesia: "",
    treatmentRendered:
      "Comprehensive oral examination (D0150) performed. Radiographs reviewed. " +
      "Periodontal screening completed. Treatment plan discussed with patient.",
  },
  prophy: {
    type: "prophy",
    label: "Prophy",
    chiefComplaint: "Routine cleaning",
    anesthesia: "",
    treatmentRendered:
      "Adult prophylaxis (D1110) performed. Supragingival scaling and polishing " +
      "completed. Oral hygiene instructions reinforced. Fluoride applied.",
  },
  extraction: {
    type: "extraction",
    label: "Extraction",
    chiefComplaint: "Tooth removal",
    anesthesia: "Lidocaine 2% 1:100,000 epinephrine, 1.7 mL",
    treatmentRendered:
      "Extraction (D7140/D7210) of tooth #___. Local anesthesia administered. " +
      "Tooth removed atraumatically. Socket irrigated and packed with gauze. " +
      "Post-operative instructions given.",
  },
  crown_prep: {
    type: "crown_prep",
    label: "Crown Prep",
    chiefComplaint: "Crown preparation",
    anesthesia: "Lidocaine 2% 1:100,000 epinephrine, 1.7 mL",
    treatmentRendered:
      "Crown preparation (D2710) of tooth #___. Local anesthesia administered. " +
      "Existing restoration/decay removed. Tooth prepared with appropriate taper and " +
      "margin placement. Impression taken. Temporary crown fabricated and cemented. " +
      "Bite checked and adjusted.",
  },
  crown_seat: {
    type: "crown_seat",
    label: "Crown Seat",
    chiefComplaint: "Crown delivery",
    anesthesia: "",
    treatmentRendered:
      "Permanent crown delivery for tooth #___. Temporary removed and site cleaned. " +
      "Crown tried in for fit, contacts, and occlusion. Adjustments made as needed. " +
      "Crown cemented with ___. Bite verified.",
  },
  root_canal: {
    type: "root_canal",
    label: "Root Canal",
    chiefComplaint: "Root canal therapy",
    anesthesia: "Lidocaine 2% 1:100,000 epinephrine, 3.4 mL",
    treatmentRendered:
      "Root canal therapy (D3310-D3330) on tooth #___. Local anesthesia administered. " +
      "Access opening made. ___ canals located and negotiated to length. Canals " +
      "instrumented with rotary files and irrigated with NaOCl. Canals dried and " +
      "obturated with gutta percha and sealer. Access restored. Patient tolerating well.",
  },
  filling: {
    type: "filling",
    label: "Filling",
    chiefComplaint: "Restoration",
    anesthesia: "Lidocaine 2% 1:100,000 epinephrine, 1.7 mL",
    treatmentRendered:
      "Composite restoration (D2391) on tooth #___, ___ surface(s). Local anesthesia " +
      "administered. Decay/old restoration removed. Bonding agent applied. Composite " +
      "placed and cured in increments. Occlusion checked and adjusted. Polished.",
  },
  srp: {
    type: "srp",
    label: "SRP",
    chiefComplaint: "Scaling and root planing",
    anesthesia: "Lidocaine 2% 1:100,000 epinephrine, 1.7 mL per quadrant",
    treatmentRendered:
      "Scaling and root planing (D4341/D4342) of ___ quadrant(s). Local anesthesia " +
      "administered. Subgingival calculus and biofilm removed. Root surfaces debrided. " +
      "Oral hygiene instructions reinforced. Chlorhexidine rinse prescribed. " +
      "4–6 week re-evaluation scheduled.",
  },
  other: {
    type: "other",
    label: "Other",
    chiefComplaint: "",
    anesthesia: "",
    treatmentRendered: "",
  },
};

export const TEMPLATE_TYPE_OPTIONS: Array<{ value: TemplateType; label: string }> = [
  { value: "exam", label: "Exam" },
  { value: "prophy", label: "Prophy" },
  { value: "extraction", label: "Extraction" },
  { value: "crown_prep", label: "Crown Prep" },
  { value: "crown_seat", label: "Crown Seat" },
  { value: "root_canal", label: "Root Canal" },
  { value: "filling", label: "Filling" },
  { value: "srp", label: "SRP" },
  { value: "other", label: "Other" },
];
