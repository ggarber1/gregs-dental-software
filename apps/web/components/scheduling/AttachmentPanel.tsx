"use client";

import { useRef } from "react";

import { Paperclip, Trash2, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ATTACHMENT_TYPE_LABELS,
  useAppointmentAttachments,
  useDeleteAttachment,
  useUploadAttachment,
  type AttachmentType,
} from "@/lib/api/attachments";

const ACCEPTED_MIME = ".jpg,.jpeg,.png,.pdf,.tif,.tiff";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentPanel({ appointmentId }: { appointmentId: string }) {
  const { data: attachments = [] } = useAppointmentAttachments(appointmentId);
  const upload = useUploadAttachment(appointmentId);
  const remove = useDeleteAttachment(appointmentId);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFiles(files: FileList | null) {
    if (!files) return;
    for (const file of Array.from(files)) {
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
      const attachmentType: AttachmentType =
        ["jpg", "jpeg", "png", "tif", "tiff"].includes(ext) ? "xray" : "other";
      upload.mutate({ file, attachmentType });
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Paperclip className="h-4 w-4" />
          Attachments
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {attachments.length === 0 && (
          <p className="text-sm text-muted-foreground">No attachments yet.</p>
        )}
        {attachments.map((att) => (
          <div
            key={att.id}
            className="flex items-center justify-between rounded border px-3 py-2 text-sm"
          >
            <div className="flex min-w-0 items-center gap-2">
              <Badge variant="secondary" className="shrink-0">
                {ATTACHMENT_TYPE_LABELS[att.attachmentType]}
              </Badge>
              <span className="truncate">{att.fileName}</span>
              <span className="shrink-0 text-muted-foreground">
                {formatBytes(att.fileSizeBytes)}
              </span>
            </div>
            {att.attachmentType !== "perio_narrative" && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={() => remove.mutate(att.id)}
                disabled={remove.isPending}
                title="Remove attachment"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        ))}

        <input
          ref={fileRef}
          type="file"
          accept={ACCEPTED_MIME}
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.currentTarget.value = "";
          }}
        />
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => fileRef.current?.click()}
          disabled={upload.isPending}
        >
          <Upload className="mr-2 h-4 w-4" />
          {upload.isPending ? "Uploading…" : "Add file"}
        </Button>
        {upload.isError && (
          <p className="text-xs text-destructive">Upload failed. Try again.</p>
        )}
      </CardContent>
    </Card>
  );
}
