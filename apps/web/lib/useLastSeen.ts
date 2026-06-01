"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Track when the user last visited a given resource (run, theme, etc.). The
 * timestamp is stored under ``shinkai.lastSeen.<key>`` in ``localStorage``.
 *
 * On mount, the previously stored value is loaded into state and the current
 * timestamp is written back. The previous value is exposed as ``lastSeen`` so
 * the caller can compute "since last visit" diffs against newer events.
 *
 * ``markSeen()`` lets the caller force a refresh, e.g. when the page is about
 * to unmount or when the user explicitly dismisses a recap panel.
 */
export function useLastSeen(key: string | null): {
  lastSeen: number;
  markSeen: () => void;
} {
  const [lastSeen, setLastSeen] = useState<number>(0);

  useEffect(() => {
    if (!key || typeof window === "undefined") return;
    const storageKey = `shinkai.lastSeen.${key}`;
    const previous = Number(window.localStorage.getItem(storageKey) ?? 0);
    setLastSeen(previous);
    const now = Math.floor(Date.now() / 1000);
    window.localStorage.setItem(storageKey, String(now));
  }, [key]);

  const markSeen = useCallback(() => {
    if (!key || typeof window === "undefined") return;
    const storageKey = `shinkai.lastSeen.${key}`;
    const now = Math.floor(Date.now() / 1000);
    window.localStorage.setItem(storageKey, String(now));
    setLastSeen(now);
  }, [key]);

  useEffect(() => {
    if (!key || typeof window === "undefined") return undefined;
    const handler = () => markSeen();
    window.addEventListener("beforeunload", handler);
    document.addEventListener("visibilitychange", handler);
    return () => {
      window.removeEventListener("beforeunload", handler);
      document.removeEventListener("visibilitychange", handler);
    };
  }, [key, markSeen]);

  return { lastSeen, markSeen };
}

export const IMPORTANT_EVENT_TYPES = new Set([
  "checkpoint_raised",
  "checkpoint_released",
  "critic_aggregated",
  "hypothesis_falsified",
  "hypothesis_superseded",
  "memory_patch_proposed",
  "filter_policy_patch_proposed",
  "checklist_patch_proposed",
  "human_injection",
  "injection_acknowledged",
  "budget_exhausted",
  "error",
]);

export function isImportantEvent(eventType: string | undefined): boolean {
  if (!eventType) return false;
  return IMPORTANT_EVENT_TYPES.has(eventType);
}
