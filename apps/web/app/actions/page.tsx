"use client";

import { useEffect, useState } from "react";
import { CriticPersonas } from "../../components/portal/CriticPersonas";
import { MemoryLayers } from "../../components/portal/MemoryLayers";
import { PatchInbox } from "../../components/portal/PatchInbox";
import { PortalShell } from "../../components/portal/PortalShell";
import { TriggersMatrix } from "../../components/portal/TriggersMatrix";
import type { Locale } from "../../lib/i18n";

export default function ActionsPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const isZh = locale === "zh";

  function changeLocale(next: Locale) {
    setLocale(next);
    window.localStorage.setItem("shinkai.locale", next);
  }

  useEffect(() => {
    const stored = window.localStorage.getItem("shinkai.locale");
    if (stored === "zh" || stored === "en") setLocale(stored);
  }, []);

  return (
    <PortalShell
      active="actions"
      locale={locale}
      onLocaleChange={changeLocale}
      title={isZh ? "能力装备" : "Capabilities"}
      subtitle={
        isZh
          ? "Agent 当前的 trigger、critic、记忆与待审补丁。"
          : "Triggers, critics, memory layers, and pending patch inbox."
      }
    >
      <div className="actions-grid">
        <TriggersMatrix locale={locale} />
        <CriticPersonas locale={locale} />
        <MemoryLayers locale={locale} />
        <PatchInbox locale={locale} />
      </div>
    </PortalShell>
  );
}
