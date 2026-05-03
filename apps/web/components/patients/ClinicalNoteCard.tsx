"use client";

import { useState } from "react";
import { PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useClinicalNotes } from "@/lib/api/clinical-notes";
import { ClinicalNoteList } from "./ClinicalNoteList";
import { CLINICAL_NOTE_TEMPLATES } from "@/lib/clinical-note-templates";

interface ClinicalNoteCardProps {
  patientId: string;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${m}/${d}/${y}`;
}

export function ClinicalNoteCard({ patientId }: ClinicalNoteCardProps) {
  const [listOpen, setListOpen] = useState(false);
  const { data, isLoading } = useClinicalNotes(patientId, 1);

  const mostRecent = data?.pages[0]?.items[0] ?? null;

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base font-semibold">Clinical Notes</CardTitle>
          <Button variant="ghost" size="sm" onClick={() => setListOpen(true)}>
            View all
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading && (
            <div className="flex justify-center py-4">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          )}

          {!isLoading && !mostRecent && (
            <p className="text-sm text-muted-foreground">No clinical notes yet.</p>
          )}

          {!isLoading && mostRecent && (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{formatDate(mostRecent.visitDate)}</span>
                {mostRecent.templateType && (
                  <Badge variant="outline" className="text-xs">
                    {CLINICAL_NOTE_TEMPLATES[mostRecent.templateType]?.label ??
                      mostRecent.templateType}
                  </Badge>
                )}
                {mostRecent.isSigned && (
                  <Badge variant="secondary" className="gap-1 text-xs">
                    <PenLine className="h-3 w-3" />
                    Signed
                  </Badge>
                )}
              </div>
              <p className="line-clamp-2 text-xs text-muted-foreground">
                {mostRecent.treatmentRendered}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {listOpen && (
        <NoteListModal patientId={patientId} onClose={() => setListOpen(false)} />
      )}
    </>
  );
}

function NoteListModal({
  patientId,
  onClose,
}: {
  patientId: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg bg-background shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-base font-semibold">Clinical Notes</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ClinicalNoteList patientId={patientId} />
        </div>
      </div>
    </div>
  );
}
