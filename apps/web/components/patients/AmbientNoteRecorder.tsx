"use client";

import { useRef, useState } from "react";
import { Mic, Square, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchAmbientNoteDraft } from "@/lib/api/ambient-notes";

type RecorderState = "idle" | "requesting" | "recording" | "processing" | "error";

interface Props {
  patientId: string;
  templateHint?: string;
  onDraft: (draft: string, detectedTemplate: string | null) => void;
}

const MAX_RECORDING_MS = 10 * 60 * 1000; // 10 minutes

export function AmbientNoteRecorder({ patientId, templateHint, onDraft }: Props) {
  const [state, setState] = useState<RecorderState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  function clearTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function stopStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  async function startRecording() {
    setState("requesting");
    setErrorMsg(null);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setState("error");
      setErrorMsg("Microphone access denied. Check your browser permissions.");
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = () => {
      clearTimer();
      stopStream();
      const blob = new Blob(chunksRef.current, { type: mimeType });
      void processAudio(blob);
    };

    recorder.start(1000); // collect chunks every second
    setState("recording");
    setElapsed(0);

    timerRef.current = setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 1;
        if (next >= MAX_RECORDING_MS / 1000) {
          stopRecording();
        }
        return next;
      });
    }, 1000);
  }

  function stopRecording() {
    clearTimer();
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setState("processing");
  }

  async function processAudio(blob: Blob) {
    try {
      const result = await fetchAmbientNoteDraft(patientId, blob, templateHint);
      onDraft(result.draft, result.detectedTemplate);
      setState("idle");
    } catch (err) {
      setState("error");
      const msg = err instanceof Error ? err.message : "Unknown error";
      if (msg.includes("502") || msg.includes("unavailable")) {
        setErrorMsg("Transcription service unavailable. Try again or type your note.");
      } else if (msg.includes("504") || msg.includes("timed out")) {
        setErrorMsg("Transcription timed out. Try a shorter recording.");
      } else {
        setErrorMsg("Failed to process dictation. Try again.");
      }
    }
  }

  function formatElapsed(secs: number) {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  if (state === "idle") {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => void startRecording()}
        className="gap-1.5"
      >
        <Mic className="h-3.5 w-3.5" />
        Dictate
      </Button>
    );
  }

  if (state === "requesting") {
    return (
      <Button type="button" variant="outline" size="sm" disabled className="gap-1.5">
        <Mic className="h-3.5 w-3.5 animate-pulse" />
        Requesting mic…
      </Button>
    );
  }

  if (state === "recording") {
    return (
      <Button
        type="button"
        variant="destructive"
        size="sm"
        onClick={stopRecording}
        className="gap-1.5"
      >
        <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
        <Square className="h-3.5 w-3.5" />
        Stop {formatElapsed(elapsed)}
      </Button>
    );
  }

  if (state === "processing") {
    return (
      <Button type="button" variant="outline" size="sm" disabled className="gap-1.5">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Transcribing…
      </Button>
    );
  }

  // error state
  return (
    <div className="flex items-center gap-2">
      <span className="flex items-center gap-1 text-xs text-destructive">
        <AlertCircle className="h-3.5 w-3.5" />
        {errorMsg}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => { setState("idle"); setErrorMsg(null); }}
      >
        Try again
      </Button>
    </div>
  );
}
