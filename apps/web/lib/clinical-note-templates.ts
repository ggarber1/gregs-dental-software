import type { TemplateType } from "@/lib/api/clinical-notes";

export interface NoteTemplate {
  type: TemplateType;
  label: string;
  /** Single multi-line body that gets inserted into the note textarea. */
  body: string;
}

export const CLINICAL_NOTE_TEMPLATES: Record<TemplateType, NoteTemplate> = {
  exam: {
    type: "exam",
    label: "Exam",
    body:
      "CC: Routine examination\n" +
      "Anesthesia: None\n" +
      "Treatment: Comprehensive oral examination (D0150) performed. Radiographs " +
      "reviewed. Periodontal screening completed. Treatment plan discussed with patient.\n" +
      "Next visit: As indicated by findings.",
  },
  prophy: {
    type: "prophy",
    label: "Prophy",
    body:
      "CC: Routine cleaning\n" +
      "Anesthesia: None\n" +
      "Treatment: Adult prophylaxis (D1110) performed. Supragingival scaling and " +
      "polishing completed. Oral hygiene instructions reinforced. Fluoride applied.\n" +
      "Next visit: 6-month recall.",
  },
  extraction: {
    type: "extraction",
    label: "Extraction",
    body:
      "CC: Tooth removal\n" +
      "Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 1.7 mL\n" +
      "Treatment: Extraction (D7140/D7210) of tooth #___. Local anesthesia " +
      "administered. Tooth removed atraumatically. Socket irrigated and packed with " +
      "gauze. Post-operative instructions given.\n" +
      "Next visit: Post-op check in 7-10 days as needed.",
  },
  crown_prep: {
    type: "crown_prep",
    label: "Crown Prep",
    body:
      "CC: Crown preparation\n" +
      "Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 1.7 mL\n" +
      "Treatment: Crown preparation (D2710) of tooth #___. Local anesthesia " +
      "administered. Existing restoration/decay removed. Tooth prepared with " +
      "appropriate taper and margin placement. Impression taken. Temporary crown " +
      "fabricated and cemented. Bite checked and adjusted.\n" +
      "Next visit: Crown seat in 2-3 weeks.",
  },
  crown_seat: {
    type: "crown_seat",
    label: "Crown Seat",
    body:
      "CC: Crown delivery\n" +
      "Anesthesia: None\n" +
      "Treatment: Permanent crown delivery for tooth #___. Temporary removed and " +
      "site cleaned. Crown tried in for fit, contacts, and occlusion. Adjustments " +
      "made as needed. Crown cemented with ___. Bite verified.\n" +
      "Next visit: Routine recall.",
  },
  root_canal: {
    type: "root_canal",
    label: "Root Canal",
    body:
      "CC: Root canal therapy\n" +
      "Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 3.4 mL\n" +
      "Treatment: Root canal therapy (D3310-D3330) on tooth #___. Local anesthesia " +
      "administered. Access opening made. ___ canals located and negotiated to " +
      "length. Canals instrumented with rotary files and irrigated with NaOCl. " +
      "Canals dried and obturated with gutta percha and sealer. Access restored. " +
      "Patient tolerating well.\n" +
      "Next visit: Crown buildup and crown prep.",
  },
  filling: {
    type: "filling",
    label: "Filling",
    body:
      "CC: Restoration\n" +
      "Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 1.7 mL\n" +
      "Treatment: Composite restoration (D2391) on tooth #___, ___ surface(s). " +
      "Local anesthesia administered. Decay/old restoration removed. Bonding agent " +
      "applied. Composite placed and cured in increments. Occlusion checked and " +
      "adjusted. Polished.\n" +
      "Next visit: Routine recall.",
  },
  srp: {
    type: "srp",
    label: "SRP",
    body:
      "CC: Scaling and root planing\n" +
      "Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 1.7 mL per quadrant\n" +
      "Treatment: Scaling and root planing (D4341/D4342) of ___ quadrant(s). Local " +
      "anesthesia administered. Subgingival calculus and biofilm removed. Root " +
      "surfaces debrided. Oral hygiene instructions reinforced. Chlorhexidine rinse " +
      "prescribed.\n" +
      "Next visit: 4-6 week re-evaluation.",
  },
  other: {
    type: "other",
    label: "Other",
    body: "",
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
