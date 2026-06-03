"use client";

import Link from "next/link";
import {
  Activity,
  Compass,
  Moon,
  PanelLeftClose,
  Pin,
  Radio,
  Settings,
  Sparkles,
  Sun,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Locale } from "../../lib/i18n";
import { CheckpointBanner } from "./CheckpointBanner";
import { ShinkaiMark } from "./ShinkaiMark";

type Theme = "day" | "night";

function resolveInitialTheme(): Theme {
  if (typeof window === "undefined") return "night";
  const stored = window.localStorage.getItem("shinkai.theme");
  if (stored === "day" || stored === "night") return stored;
  if (window.matchMedia?.("(prefers-color-scheme: light)").matches) return "day";
  return "night";
}

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
  { id: "agent", href: "/agent", label: "Overview", icon: Compass },
  { id: "live", href: "/live", label: "Current", icon: Sparkles },
  { id: "actions", href: "/actions", label: "Actions", icon: Settings },
  { id: "history", href: "/runs", label: "History", icon: Activity },
  { id: "a2a", href: "/a2a", label: "A2A", icon: Radio },
];

const zhNavLabels: Record<PortalShellProps["active"], string> = {
  agent: "总览",
  live: "当下工作",
  actions: "能力",
  history: "历史记录",
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
  const [theme, setTheme] = useState<Theme>("night");
  const isZh = locale === "zh";

  useEffect(() => {
    setPinned(window.localStorage.getItem("shinkai.sidebar.pinned") === "true");
    const next = resolveInitialTheme();
    setTheme(next);
    document.documentElement.dataset.theme = next;
  }, []);

  function togglePinned() {
    setPinned((current) => {
      const next = !current;
      window.localStorage.setItem("shinkai.sidebar.pinned", String(next));
      return next;
    });
  }

  function toggleTheme() {
    setTheme((current) => {
      const next: Theme = current === "night" ? "day" : "night";
      window.localStorage.setItem("shinkai.theme", next);
      document.documentElement.dataset.theme = next;
      return next;
    });
  }

  return (
    <div className="portal" data-sidebar-pinned={pinned ? "true" : "false"}>
      <aside className="portal-sidebar">
        <Link className="portal-logo" href="/">
          <span className="portal-logo-mark" aria-hidden="true">
            <ShinkaiMark size={18} strokeWidth={1.5} />
          </span>
          <span className="portal-logo-text">shinkai</span>
          <small>{isZh ? "深海 · 投研引擎" : "Deep · Research Engine"}</small>
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
          <button
            type="button"
            className="sidebar-theme-button"
            onClick={toggleTheme}
            aria-label={
              theme === "night"
                ? isZh
                  ? "切换到白天模式"
                  : "Switch to day mode"
                : isZh
                  ? "切换到夜间模式"
                  : "Switch to night mode"
            }
          >
            <span className="portal-nav-icon" aria-hidden="true">
              {theme === "night" ? (
                <Sun size={16} strokeWidth={1.8} />
              ) : (
                <Moon size={16} strokeWidth={1.8} />
              )}
            </span>
            <span className="portal-nav-label">
              {theme === "night"
                ? isZh
                  ? "白天"
                  : "Day"
                : isZh
                  ? "夜间"
                  : "Night"}
            </span>
          </button>
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
