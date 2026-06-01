"use client";

import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";
import { CapabilityConfig } from "./CapabilityConfig";

type Trigger = {
  key: string;
  name_en: string;
  name_zh: string;
  default: unknown;
  description_en: string;
  description_zh: string;
  options: unknown[];
};

type TriggersMatrixProps = {
  locale: Locale;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export function TriggersMatrix({ locale }: TriggersMatrixProps) {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/actions/triggers`, {
          cache: "no-store",
        });
        if (!response.ok) return;
        const data: Trigger[] = await response.json();
        if (!cancelled) setTriggers(data);
      } catch {
        // silent
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);
  return <CapabilityConfig triggers={triggers} locale={locale} />;
}
