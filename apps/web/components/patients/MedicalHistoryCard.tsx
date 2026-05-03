"use client";

import { useState } from "react";
import { ClipboardList, History, Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import { useMedicalHistory, type MedicalHistoryVersion } from "@/lib/api/medical-history";
import { MedicalHistoryModal } from "./MedicalHistoryModal";
import { MedicalHistoryHistoryDrawer } from "./MedicalHistoryHistoryDrawer";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  patientId: string;
}

// ── Flag badges ───────────────────────────────────────────────────────────────

const FLAG_LABELS: Array<{ key: keyof MedicalHistoryVersion["flags"]; label: string }> = [
  { key: "flagBloodThinners", label: "Blood thinner risk" },
  { key: "flagBisphosphonates", label: "Bisphosphonate" },
  { key: "flagHeartCondition", label: "Heart condition" },
  { key: "flagDiabetes", label: "Diabetes" },
  { key: "flagPacemaker", label: "Pacemaker / ICD" },
  { key: "flagLatexAllergy", label: "Latex allergy" },
];

function FlagBadges({ flags }: { flags: MedicalHistoryVersion["flags"] }) {
  const active = FLAG_LABELS.filter(({ key }) => flags[key]);
  if (active.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {active.map(({ key, label }) => (
        <Badge key={key} variant="destructive">
          {label}
        </Badge>
      ))}
    </div>
  );
}

// ── Structured sections ───────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{children}</p>
  );
}

function VersionContent({ version }: { version: MedicalHistoryVersion }) {
  return (
    <div className="flex flex-col gap-4">
      <FlagBadges flags={version.flags} />

      {version.allergies.length > 0 && (
        <div className="flex flex-col gap-1">
          <SectionHeading>Allergies</SectionHeading>
          <ul className="flex flex-col gap-0.5 text-sm">
            {version.allergies.map((a, i) => (
              <li key={i}>
                <span className="font-medium">{a.name}</span>
                {a.severity && (
                  <Badge variant="outline" className="ml-1.5 text-xs">
                    {a.severity}
                  </Badge>
                )}
                {a.reaction && (
                  <span className="ml-1.5 text-muted-foreground">— {a.reaction}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {version.medications.length > 0 && (
        <div className="flex flex-col gap-1">
          <SectionHeading>Medications</SectionHeading>
          <ul className="flex flex-col gap-0.5 text-sm">
            {version.medications.map((m, i) => (
              <li key={i}>
                <span className="font-medium">{m.name}</span>
                {m.dose && <span className="text-muted-foreground"> · {m.dose}</span>}
                {m.frequency && <span className="text-muted-foreground"> · {m.frequency}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {version.conditions.length > 0 && (
        <div className="flex flex-col gap-1">
          <SectionHeading>Conditions</SectionHeading>
          <ul className="flex flex-col gap-0.5 text-sm">
            {version.conditions.map((c, i) => (
              <li key={i}>
                <span className="font-medium">{c.name}</span>
                {c.icd10Hint && (
                  <span className="text-muted-foreground"> ({c.icd10Hint})</span>
                )}
                {c.notes && <span className="text-muted-foreground"> — {c.notes}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {version.additionalNotes && (
        <div className="flex flex-col gap-1">
          <SectionHeading>Notes</SectionHeading>
          <p className="text-sm whitespace-pre-line">{version.additionalNotes}</p>
        </div>
      )}

      {version.allergies.length === 0 &&
        version.medications.length === 0 &&
        version.conditions.length === 0 &&
        !version.additionalNotes && (
          <p className="text-sm text-muted-foreground">No details recorded.</p>
        )}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onRecord }: { onRecord: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <ClipboardList className="h-8 w-8 text-muted-foreground" />
      <div>
        <p className="text-sm font-medium">No medical history recorded</p>
        <p className="text-xs text-muted-foreground">
          Record allergies, medications, and conditions for this patient.
        </p>
      </div>
      <Button size="sm" onClick={onRecord}>
        Record Medical History
      </Button>
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────

export function MedicalHistoryCard({ patientId }: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const { data: version, isLoading, isError, error } = useMedicalHistory(patientId);

  const isNoHistory = isError && error instanceof ApiError && error.status === 404;

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base font-semibold">Medical History</CardTitle>
          <div className="flex gap-1">
            {version && (
              <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)}>
                <History className="h-4 w-4" />
                History
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => setModalOpen(true)}>
              <Pencil className="h-4 w-4" />
              {version ? "Update" : "Record"}
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          {isLoading && (
            <div className="flex justify-center py-6">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          )}

          {isNoHistory && <EmptyState onRecord={() => setModalOpen(true)} />}

          {isError && !isNoHistory && (
            <p className="py-4 text-sm text-destructive">Failed to load medical history.</p>
          )}

          {version && <VersionContent version={version} />}

          {version && (
            <p className="mt-4 text-xs text-muted-foreground">
              Last updated {new Date(version.recordedAt).toLocaleDateString()} · v{version.versionNumber}
            </p>
          )}
        </CardContent>
      </Card>

      <MedicalHistoryModal
        patientId={patientId}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        {...(version ? { currentVersion: version } : {})}
      />

      <MedicalHistoryHistoryDrawer
        patientId={patientId}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
    </>
  );
}
