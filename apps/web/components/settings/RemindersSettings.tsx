"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useReminderSettings, useUpdateReminderSettings } from "@/lib/api/reminders";

const MIN_HOURS = 1;
const MAX_HOURS = 168;
const MAX_WINDOWS = 5;

export function RemindersSettings() {
  const { data: settings, isLoading } = useReminderSettings();
  const updateSettings = useUpdateReminderSettings();

  const [hours, setHours] = useState<number[]>([]);
  const [newHours, setNewHours] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (settings && !dirty) {
      setHours(settings.reminderHours);
    }
  }, [settings, dirty]);

  function handleAdd() {
    setAddError(null);
    const parsed = parseInt(newHours, 10);
    if (isNaN(parsed) || parsed < MIN_HOURS || parsed > MAX_HOURS) {
      setAddError(`Enter a number between ${MIN_HOURS} and ${MAX_HOURS}`);
      return;
    }
    if (hours.includes(parsed)) {
      setAddError("That window already exists");
      return;
    }
    if (hours.length >= MAX_WINDOWS) {
      setAddError(`Maximum ${MAX_WINDOWS} windows allowed`);
      return;
    }
    const updated = [...hours, parsed].sort((a, b) => b - a);
    setHours(updated);
    setNewHours("");
    setDirty(true);
  }

  function handleRemove(h: number) {
    if (hours.length <= 1) return;
    setHours(hours.filter((x) => x !== h));
    setDirty(true);
  }

  async function handleSave() {
    setSaveError(null);
    try {
      await updateSettings.mutateAsync({ reminderHours: hours });
      setDirty(false);
    } catch {
      setSaveError("Failed to save settings. Please try again.");
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-8 w-64 animate-pulse rounded bg-muted" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 max-w-lg">
      <div>
        <h3 className="text-base font-semibold">Reminder Windows</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Reminders are sent this many hours before each appointment via SMS and email.
        </p>
      </div>

      <div className="rounded-md border divide-y">
        {hours.map((h) => (
          <div key={h} className="flex items-center justify-between px-4 py-3">
            <span className="text-sm font-medium">{h} hours before</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleRemove(h)}
              disabled={hours.length <= 1}
              aria-label={`Remove ${h}-hour window`}
            >
              <Trash2 className="h-4 w-4 text-muted-foreground" />
            </Button>
          </div>
        ))}
      </div>

      {hours.length < MAX_WINDOWS && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="new-hours">Add a window (hours before appointment)</Label>
          <div className="flex gap-2">
            <Input
              id="new-hours"
              type="number"
              min={MIN_HOURS}
              max={MAX_HOURS}
              value={newHours}
              onChange={(e) => {
                setNewHours(e.target.value);
                setAddError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAdd();
              }}
              placeholder="e.g. 72"
              className="w-32"
            />
            <Button variant="outline" onClick={handleAdd}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add
            </Button>
          </div>
          {addError && <p className="text-xs text-destructive">{addError}</p>}
        </div>
      )}

      {saveError && <p className="text-sm text-destructive">{saveError}</p>}

      {dirty && (
        <div className="flex gap-2">
          <Button
            onClick={() => void handleSave()}
            disabled={updateSettings.isPending}
          >
            {updateSettings.isPending ? "Saving..." : "Save changes"}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setHours(settings?.reminderHours ?? [48, 24]);
              setDirty(false);
              setSaveError(null);
            }}
            disabled={updateSettings.isPending}
          >
            Discard
          </Button>
        </div>
      )}
    </div>
  );
}
