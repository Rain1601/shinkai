"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type Locale } from "../../lib/i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100";

type MemberRow = {
  id: string;
  label: string;
  kind: string;
  layer: string | null;
  target_entity_id: string;
  has_subject_id: string | null;
};

type MembersResponse = {
  subject_id: string;
  members: MemberRow[];
  count: number;
};

const LAYER_LABEL: Record<string, string> = {
  ai_model: "AI Model",
  designer: "Designer",
  assembly: "Assembly",
  advanced_packaging: "Packaging",
  memory: "Memory",
  testing: "Test / OSAT",
  foundry: "Foundry",
  optical: "Optical",
  robotics: "Robotics",
  battery: "Battery",
  power: "Power",
  cooling: "Cooling",
  infrastructure: "Infra",
  passive: "Passives",
  materials: "Materials",
  theme: "Theme",
  other: "Other",
};

type Props = {
  subjectId: string;
  locale: Locale;
};

export function ThemeMembersGrid({ subjectId, locale }: Props) {
  const isZh = locale === "zh";
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    async function load() {
      try {
        const r = await fetch(
          `${API_URL}/api/v1/industry_graph/subjects/${encodeURIComponent(subjectId)}/members`,
          { cache: "no-store" },
        );
        if (!r.ok) throw new Error(`members ${r.status}`);
        const d: MembersResponse = await r.json();
        if (cancelled) return;
        setMembers(d.members);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [subjectId]);

  // Group members by their derived layer so the grid keeps the same
  // strata vocabulary the Company graph uses.
  const byLayer = new Map<string, MemberRow[]>();
  for (const m of members) {
    const key = m.layer ?? "other";
    if (!byLayer.has(key)) byLayer.set(key, []);
    byLayer.get(key)!.push(m);
  }
  const orderedLayers = Array.from(byLayer.keys()).sort((a, b) => {
    const order = [
      "designer",
      "ai_model",
      "assembly",
      "advanced_packaging",
      "memory",
      "testing",
      "foundry",
      "optical",
      "robotics",
      "battery",
      "power",
      "cooling",
      "infrastructure",
      "passive",
      "materials",
      "other",
    ];
    return order.indexOf(a) - order.indexOf(b);
  });

  if (loading) {
    return <p className="muted live-empty">{isZh ? "加载中…" : "Loading members…"}</p>;
  }
  if (error) {
    return <p className="muted error-copy">{error}</p>;
  }
  if (members.length === 0) {
    return (
      <div className="ig-members-empty">
        <p className="muted">
          {isZh
            ? "尚未识别出此主题下的成员公司。Agent 在后续 pass 时会填补。"
            : "No member companies attributed yet. The agent fills this on the next pass."}
        </p>
      </div>
    );
  }

  return (
    <div className="ig-members">
      <header className="ig-members-header">
        <span className="ig-members-eyebrow">
          {isZh ? "成员公司" : "Members"}
        </span>
        <span className="ig-members-count">
          {members.length} {isZh ? "家" : ""}
        </span>
      </header>

      <div className="ig-members-grid">
        {orderedLayers.map((layer) => {
          const rows = byLayer.get(layer)!;
          return (
            <section key={layer} className="ig-members-stratum">
              <h3 className="ig-members-stratum-head">
                <span>{LAYER_LABEL[layer] ?? layer}</span>
                <span className="ig-members-stratum-count">{rows.length}</span>
              </h3>
              <ul className="ig-members-list">
                {rows.map((m) => {
                  const inner = (
                    <>
                      <span className="ig-member-name">{m.label}</span>
                      <span className="ig-member-id">{m.id}</span>
                    </>
                  );
                  return (
                    <li key={m.id} className="ig-member">
                      {m.has_subject_id ? (
                        <Link
                          href={`/industry-graph/${encodeURIComponent(m.has_subject_id)}`}
                          className="ig-member-link"
                          title={isZh ? "进入 Company Detail" : "Open company detail"}
                        >
                          {inner}
                          <span className="ig-member-go">→</span>
                        </Link>
                      ) : (
                        <span
                          className="ig-member-link disabled"
                          title={isZh ? "尚未建 Subject" : "No Subject record yet"}
                        >
                          {inner}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
