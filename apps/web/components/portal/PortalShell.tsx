"use client";

import Link from "next/link";
import {
  Activity,
  Compass,
  PanelLeftClose,
  Pin,
  Radio,
  Settings,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Locale } from "../../lib/i18n";
import { CheckpointBanner } from "./CheckpointBanner";

type PortalShellProps = {
  title: string;
  subtitle?: string;
  active:
    | "agent"
    | "live"
    | "actions"
    | "history"
    | "results"
    | "themes"
    | "a2a";
  actions?: ReactNode;
  children: ReactNode;
  locale?: Locale;
  onLocaleChange?: (locale: Locale) => void;
};

const navItems: Array<{
  id: PortalShellProps["active"];
  href: string;
  label: string;
  icon: LucideIcon;
}> = [
  { id: "agent", href: "/agent", label: "Agent", icon: Compass },
  { id: "live", href: "/live", label: "Live", icon: Sparkles },
  { id: "actions", href: "/actions", label: "Actions", icon: Settings },
  { id: "history", href: "/runs", label: "History", icon: Activity },
  { id: "a2a", href: "/a2a", label: "A2A", icon: Radio },
];

const zhNavLabels: Record<PortalShellProps["active"], string> = {
  agent: "Agent",
  live: "实时",
  actions: "能力",
  history: "历史",
  results: "产出",
  themes: "主题",
  a2a: "A2A",
};

export function PortalShell({
  title,
  subtitle,
  active,
  actions,
  children,
  locale = "zh",
  onLocaleChange,
}: PortalShellProps) {
  const [pinned, setPinned] = useState(false);
  const isZh = locale === "zh";

  useEffect(() => {
    setPinned(window.localStorage.getItem("shinkai.sidebar.pinned") === "true");
  }, []);

  function togglePinned() {
    setPinned((current) => {
      const next = !current;
      window.localStorage.setItem("shinkai.sidebar.pinned", String(next));
      return next;
    });
  }

  return (
    <div className="portal" data-sidebar-pinned={pinned ? "true" : "false"}>
      <aside className="portal-sidebar">
        <Link className="portal-logo" href="/">
          <span className="portal-logo-mark" aria-hidden="true">
            <Compass size={18} strokeWidth={1.8} />
          </span>
          <span className="portal-logo-text">Shinkai</span>
          <small>{isZh ? "Agent 运行框架" : "Agent Harness"}</small>
        </Link>
        <nav className="portal-nav" aria-label={isZh ? "工作区" : "Workspace"}>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                aria-current={active === item.id ? "page" : undefined}
                className={active === item.id ? "portal-nav-item active" : "portal-nav-item"}
                href={item.href}
                key={item.id}
              >
                <span className="portal-nav-icon" aria-hidden="true">
                  <Icon size={17} strokeWidth={1.9} />
                </span>
                <span className="portal-nav-label">{isZh ? zhNavLabels[item.id] : item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="portal-sidebar-footer">
          {onLocaleChange ? (
            <div
              className="sidebar-language"
              role="group"
              aria-label={isZh ? "语言切换" : "Language"}
            >
              <button
                type="button"
                aria-pressed={locale === "zh"}
                className={locale === "zh" ? "active" : ""}
                onClick={() => onLocaleChange("zh")}
              >
                中文
              </button>
              <button
                type="button"
                aria-pressed={locale === "en"}
                className={locale === "en" ? "active" : ""}
                onClick={() => onLocaleChange("en")}
              >
                EN
              </button>
            </div>
          ) : null}
          <button
            aria-label={pinned ? (isZh ? "收起侧边栏" : "Collapse sidebar") : isZh ? "固定展开侧边栏" : "Pin sidebar"}
            className="sidebar-pin-button"
            onClick={togglePinned}
            type="button"
          >
            <span className="portal-nav-icon" aria-hidden="true">
              {pinned ? <PanelLeftClose size={17} strokeWidth={1.9} /> : <Pin size={17} strokeWidth={1.9} />}
            </span>
            <span className="portal-nav-label">{pinned ? (isZh ? "收起" : "Collapse") : isZh ? "固定展开" : "Pin open"}</span>
          </button>
        </div>
      </aside>
      <main className="portal-main">
        <CheckpointBanner locale={locale} />
        <header className="portal-header">
          <div>
            <h1>{title}</h1>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {actions ? <div className="portal-actions">{actions}</div> : null}
        </header>
        {children}
      </main>
    </div>
  );
}
