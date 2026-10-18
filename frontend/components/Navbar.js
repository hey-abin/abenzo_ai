"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Inbox, BookOpen, Settings, Sparkles, CheckCircle2, AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchSystemHealth } from "@/lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetchSystemHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [pathname]);

  const navItems = [
    { label: "Overview", href: "/", icon: LayoutDashboard },
    { label: "Leads", href: "/leads", icon: Users },
    { label: "Inbox", href: "/inbox", icon: Inbox },
    { label: "Knowledge", href: "/knowledge", icon: BookOpen },
    { label: "Settings", href: "/settings", icon: Settings },
  ];

  return (
    <header className="sticky top-0 z-50 border-b border-zinc-200 bg-white/95 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/95">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 font-bold text-sm">
              A
            </div>
            <div>
              <span className="font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
                Abenzo AI
              </span>
              <span className="ml-2 rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                MVP
              </span>
            </div>
          </Link>

          <nav className="flex items-center space-x-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                      : "text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-200"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3 text-xs">
          {health?.ollama?.reachable ? (
            <div className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span>{health.ollama.provider === "openai_compatible" ? `AI (${health.ollama.model})` : `Ollama (${health.ollama.model})`}</span>
            </div>
          ) : (
            <div 
              className="flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border border-amber-200 dark:border-amber-800 cursor-help"
              title={health?.ollama?.error_message || "AI inference service unreachable"}
            >
              <AlertCircle className="h-3 w-3" />
              <span>{health?.ollama?.provider === "openai_compatible" ? "AI Offline" : "Ollama Offline"}</span>
            </div>
          )}

          <div className="hidden sm:flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-1 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700">
            {health?.database?.status === "connected" ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span>{health?.database?.engine === "postgresql" || health?.database?.type?.includes("Neon") || health?.database?.type?.includes("PostgreSQL") ? "Neon PostgreSQL" : "SQLite Local"}</span>
              </>
            ) : (
              <span>Database Offline</span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
