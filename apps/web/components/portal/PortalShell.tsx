"use client";

import Link from "next/link";
import {
  Activity,
  ClipboardCheck,
  Compass,
  Gauge,
  Home,
  Layers,
  Network,
  PanelLeftClose,
  Pin,
  Radio
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Locale } from "../../lib/i18n";
import { CheckpointBanner } from "./CheckpointBanner";

type PortalShellProps = {
  title: string;
  subtitle?: string;
  active: "overview" | "themes" | "runs" | "review" | "graph" | "eval" | "a2a";
  actions?: ReactNode;
  children: ReactNode;
  locale?: Locale;
};

const navItems: Array<{
  id: PortalShellProps["active"];
  href: string;
  label: string;
  icon: LucideIcon;
}> = [
  { id: "overview", href: "/", label: "Overview", icon: Home },
  { id: "themes", href: "/themes", label: "Themes", icon: Layers },
  { id: "runs", href: "/runs", label: "Runs", icon: Activity },
  { id: "review", href: "/review", label: "Review", icon: ClipboardCheck },
  { id: "graph", href: "/graph", label: "Graph", icon: Network },
  { id: "eval", href: "/eval", label: "Eval", icon: Gauge },
  { id: "a2a", href: "/a2a", label: "A2A", icon: Radio }
];

const zhNavLabels: Record<PortalShellProps["active"], string> = {
  overview: "总览",
  themes: "主题",
  runs: "运行",
  review: "复盘",
  graph: "图谱",
  eval: "评测",
  a2a: "A2A"
};

export function PortalShell({
  title,
  subtitle,
  active,
  actions,
  children,
  locale = "zh"
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
