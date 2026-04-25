"use client";

import { useAppointmentReminders, type ReminderRecord } from "@/lib/api/reminders";
import { type ReminderSummary } from "@/lib/api/scheduling";
import { usePracticeTimezone } from "@/lib/api/practice";
import { formatTimeInTz } from "@/lib/timezone";

const CHANNEL_LABEL: Record<string, string> = {
  sms: "SMS",
  email: "Email",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  enqueued: "Queued",
  sent: "Sent",
  failed: "Failed",
  cancelled: "Cancelled",
};

function formatSendAt(isoString: string, timezone: string): string {
  const d = new Date(isoString);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(d);
}

function ReminderRow({ reminder, timezone }: { reminder: ReminderRecord; timezone: string }) {
  const isFailed = reminder.status === "failed";
  const isSent = reminder.status === "sent";
  const isCancelled = reminder.status === "cancelled";

  return (
    <div className="flex flex-col gap-0.5 py-1.5 border-b last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">
          {CHANNEL_LABEL[reminder.reminderType] ?? reminder.reminderType} ·{" "}
          {reminder.hoursBefore}h before
        </span>
        <span
          className={[
            "text-xs font-medium px-1.5 py-0.5 rounded",
            isFailed
              ? "bg-destructive/10 text-destructive"
              : isSent
                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                : isCancelled
                  ? "text-muted-foreground bg-muted"
                  : "text-muted-foreground",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {STATUS_LABEL[reminder.status] ?? reminder.status}
        </span>
      </div>

      <div className="text-xs text-muted-foreground">
        {isSent && reminder.sentAt ? (
          <>Sent {formatSendAt(reminder.sentAt, timezone)}</>
        ) : isFailed && reminder.failedAt ? (
          <>
            Failed {formatSendAt(reminder.failedAt, timezone)}
            {reminder.failureReason && (
              <span className="ml-1 text-destructive">— {reminder.failureReason}</span>
            )}
          </>
        ) : (
          <>Scheduled for {formatSendAt(reminder.sendAt, timezone)}</>
        )}
      </div>

      {reminder.responseReceived && (
        <div className="text-xs mt-0.5">
          <span className="font-medium">Reply: </span>
          <span className="text-muted-foreground">
            &ldquo;{reminder.responseReceived}&rdquo;
            {reminder.respondedAt && (
              <> · {formatSendAt(reminder.respondedAt, timezone)}</>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

interface ReminderHistoryProps {
  appointmentId: string;
  reminderSummary: ReminderSummary | null | undefined;
}

export function ReminderHistory({ appointmentId, reminderSummary }: ReminderHistoryProps) {
  const timezone = usePracticeTimezone();
  const { data: reminders, isLoading } = useAppointmentReminders(appointmentId);

  const optedOut = reminderSummary?.patientSmsOptedOut;

  return (
    <div className="space-y-1">
      <p className="text-sm font-medium leading-none">Reminders</p>

      {optedOut && (
        <div className="rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-xs text-orange-700 dark:border-orange-800 dark:bg-orange-950/30 dark:text-orange-400">
          Patient has opted out of SMS reminders
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2 pt-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-4 w-full animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : !reminders || reminders.length === 0 ? (
        <p className="text-xs text-muted-foreground py-1">No reminders scheduled.</p>
      ) : (
        <div className="rounded-md border">
          {reminders.map((r) => (
            <ReminderRow key={r.id} reminder={r} timezone={timezone} />
          ))}
        </div>
      )}
    </div>
  );
}
