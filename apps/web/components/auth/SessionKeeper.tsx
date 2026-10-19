"use client";

import { useEffect } from "react";

import { msUntilRefresh, refreshSession } from "@/lib/auth/clientSession";
import { getAccessToken } from "@/lib/auth/cookies";

/**
 * Keeps the session cookie fresh while the app is open: refreshes shortly before
 * the token expires, and again when the tab becomes visible (timers don't fire
 * while a laptop sleeps). A failed refresh isn't retried here — the next API call
 * gets a 401 and api-client sends the user to login.
 */
export function SessionKeeper(): null {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(() => void refreshNow(), msUntilRefresh(getAccessToken(), Date.now()));
    }

    async function refreshNow() {
      const ok = await refreshSession();
      if (ok && !cancelled) schedule();
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible") schedule();
    }

    schedule();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return null;
}
