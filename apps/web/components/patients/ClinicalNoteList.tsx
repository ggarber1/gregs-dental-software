"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, PenLine, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useClinicalNotes,
  useClinicalNote,
  type ClinicalNoteSummary,
} from "@/lib/api/clinical-notes";
import { ClinicalNoteEditor } from "./ClinicalNoteEditor";
import { CLINICAL_NOTE_TEMPLATES } from "@/lib/clinical-note-templates";

interface ClinicalNoteListProps {
  patientId: string;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${m}/${d}/${y}`;
}

function templateLabel(type: string | null): string | null {
  if (!type) return null;
  return CLINICAL_NOTE_TEMPLATES[type as keyof typeof CLINICAL_NOTE_TEMPLATES]?.label ?? type;
}

function NoteRow({
  note,
  patientId,
}: {
  note: ClinicalNoteSummary;
  patientId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const label = templateLabel(note.templateType);

  return (
    <>
      <div className="border-b border-border last:border-b-0">
        <div
          className="flex cursor-pointer items-start gap-3 px-4 py-3 hover:bg-accent/40"
          onClick={() => setExpanded((p) => !p)}
        >
          <span className="mt-0.5 text-muted-foreground">
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{formatDate(note.visitDate)}</span>
              {label && (
                <Badge variant="outline" className="text-xs">
                  {label}
                </Badge>
              )}
              {note.isSigned && (
                <Badge variant="secondary" className="gap-1 text-xs">
                  <PenLine className="h-3 w-3" />
                  Signed
                </Badge>
              )}
            </div>
            <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
              {note.treatmentRendered}
            </p>
          </div>
          {!note.isSigned && (
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                setEditOpen(true);
              }}
            >
              Edit
            </Button>
          )}
        </div>

        {expanded && (
          <div className="bg-muted/30 px-10 pb-4 pt-2">
            <dl className="grid gap-y-2 text-sm">
              <NoteField label="Treatment rendered" value={note.treatmentRendered} />
              {note.signedAt && (
                <NoteField
                  label="Signed"
                  value={new Date(note.signedAt).toLocaleString()}
                />
              )}
            </dl>
          </div>
        )}
      </div>

      {editOpen && (
        <ClinicalNoteDetailEditor
          patientId={patientId}
          noteId={note.id}
          open={editOpen}
          onClose={() => setEditOpen(false)}
        />
      )}
    </>
  );
}

function ClinicalNoteDetailEditor({
  patientId,
  noteId,
  open,
  onClose,
}: {
  patientId: string;
  noteId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { data: note, isLoading } = useClinicalNote(patientId, noteId);

  if (isLoading || !note) return null;

  return (
    <ClinicalNoteEditor
      patientId={patientId}
      open={open}
      onClose={onClose}
      existingNote={note}
    />
  );
}

function NoteField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 whitespace-pre-wrap font-medium">{value}</dd>
    </div>
  );
}

export function ClinicalNoteList({ patientId }: ClinicalNoteListProps) {
  const [newNoteOpen, setNewNoteOpen] = useState(false);
  const { data, isLoading, isFetchingNextPage, fetchNextPage, hasNextPage, isError } =
    useClinicalNotes(patientId);

  const allNotes = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm font-medium text-muted-foreground">
          {allNotes.length} note{allNotes.length !== 1 ? "s" : ""}
        </span>
        <Button size="sm" onClick={() => setNewNoteOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          New note
        </Button>
      </div>

      {isLoading && (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {isError && (
        <p className="px-4 py-4 text-sm text-destructive">Failed to load notes.</p>
      )}

      {!isLoading && !isError && allNotes.length === 0 && (
        <p className="px-4 py-6 text-center text-sm text-muted-foreground">
          No clinical notes yet.
        </p>
      )}

      {!isLoading && allNotes.length > 0 && (
        <div className="divide-y divide-border">
          {allNotes.map((note) => (
            <NoteRow key={note.id} note={note} patientId={patientId} />
          ))}
        </div>
      )}

      {hasNextPage && (
        <div className="flex justify-center py-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void fetchNextPage()}
            disabled={isFetchingNextPage}
          >
            {isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      )}

      {newNoteOpen && (
        <ClinicalNoteEditor
          patientId={patientId}
          open={newNoteOpen}
          onClose={() => setNewNoteOpen(false)}
        />
      )}
    </>
  );
}
