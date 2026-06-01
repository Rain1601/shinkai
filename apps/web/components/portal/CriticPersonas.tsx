"use client";

import { useEffect, useState } from "react";
import type { Locale } from "../../lib/i18n";

type Persona = {
  key: string;
  name_en: string;
  name_zh: string;
  prompt_text: string;
  v0_rule_summary_en: string;
  v0_rule_summary_zh: string;
  total_verdicts: number;
  total_rejects: number;
};

type CriticPersonasProps = {
  locale: Locale;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

export function CriticPersonas({ locale }: CriticPersonasProps) {
  const isZh = locale === "zh";
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(`${API_URL}/api/v1/actions/critics`, {
          cache: "no-store",
        });
        if (!response.ok) return;
        const data: Persona[] = await response.json();
        if (!cancelled) setPersonas(data);
      } catch {
        // silent
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="surface critic-personas-panel">
      <div className="panel-heading">
        <h2>{isZh ? "评审 persona" : "Critic Personas"}</h2>
        <span className="label">{personas.length}</span>
      </div>
      <div className="critic-personas-list">
        {personas.map((persona) => {
          const open = expanded.has(persona.key);
          return (
            <article className="critic-persona-card" key={persona.key}>
              <header
                role="button"
                tabIndex={0}
                onClick={() => toggle(persona.key)}
              >
                <div>
                  <strong>{isZh ? persona.name_zh : persona.name_en}</strong>
                  <code>{persona.key}</code>
                </div>
                <span className="label">
                  {persona.total_rejects} / {persona.total_verdicts}{" "}
                  {isZh ? "否决" : "rejects"}
                </span>
              </header>
              <p className="critic-persona-summary">
                {isZh ? persona.v0_rule_summary_zh : persona.v0_rule_summary_en}
              </p>
              {open ? (
                <pre className="critic-persona-prompt">{persona.prompt_text}</pre>
              ) : (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => toggle(persona.key)}
                >
                  {isZh ? "查看完整 prompt" : "View full prompt"} →
                </button>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
