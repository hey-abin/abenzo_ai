"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { 
  Users, 
  CheckCircle, 
  FileText, 
  MessageSquare, 
  ArrowRight, 
  Sparkles, 
  ShieldCheck, 
  ExternalLink,
  RefreshCw,
  Plus
} from "lucide-react";
import { fetchMetrics } from "@/lib/api";

export default function OverviewPage() {
  const [metrics, setMetrics] = useState({
    total_leads: 0,
    qualified_leads: 0,
    drafts_waiting: 0,
    inbox_needing_attention: 0,
    recent_activity: []
  });
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    setLoading(true);
    fetchMetrics()
      .then((data) => {
        setMetrics(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Metrics load error:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            Abenzo Sales Assistant
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Local-first prospect discovery, evidence-based qualification, and human-in-the-loop outreach.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <Link
            href="/leads?action=new"
            className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Lead
          </Link>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Total Leads */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Total Leads Found</span>
            <Users className="h-4 w-4 text-zinc-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            {metrics.total_leads}
          </div>
          <div className="mt-2 text-xs text-zinc-500">
            <Link href="/leads" className="text-blue-600 hover:underline dark:text-blue-400 inline-flex items-center gap-1">
              View all leads <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>

        {/* Qualified Leads */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Qualified Leads (Score ≥ 60)</span>
            <CheckCircle className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-emerald-600 dark:text-emerald-400">
            {metrics.qualified_leads}
          </div>
          <div className="mt-2 text-xs text-zinc-500">
            <span>High web service fit</span>
          </div>
        </div>

        {/* Drafts Waiting */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Drafts Waiting Review</span>
            <FileText className="h-4 w-4 text-amber-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-amber-600 dark:text-amber-400">
            {metrics.drafts_waiting}
          </div>
          <div className="mt-2 text-xs text-zinc-500">
            <Link href="/leads?status=draft_ready" className="text-amber-600 hover:underline dark:text-amber-400 inline-flex items-center gap-1">
              Review drafts <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>

        {/* Inbound Conversations */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Inbox Needing Attention</span>
            <MessageSquare className="h-4 w-4 text-purple-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-purple-600 dark:text-purple-400">
            {metrics.inbox_needing_attention}
          </div>
          <div className="mt-2 text-xs text-zinc-500">
            <Link href="/inbox" className="text-purple-600 hover:underline dark:text-purple-400 inline-flex items-center gap-1">
              Open inbox <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>

      {/* Main Grid: Recent Activity & Honesty Guidelines */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent Activity */}
        <div className="lg:col-span-2 rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Recent Leads & Activity
            </h2>
            <Link href="/leads" className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200">
              View all
            </Link>
          </div>

          {metrics.recent_activity.length === 0 ? (
            <div className="rounded-md border border-dashed border-zinc-200 p-8 text-center text-sm text-zinc-500 dark:border-zinc-800">
              No leads added yet. Get started by clicking{" "}
              <Link href="/leads" className="font-semibold text-zinc-900 underline dark:text-zinc-100">
                Add Lead
              </Link>{" "}
              or importing a CSV.
            </div>
          ) : (
            <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {metrics.recent_activity.map((lead) => (
                <div key={lead.id} className="flex items-center justify-between py-3">
                  <div>
                    <Link
                      href={`/leads?highlight=${lead.id}`}
                      className="text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                    >
                      {lead.business_name}
                    </Link>
                    <div className="text-xs text-zinc-500">
                      Score: <span className="font-semibold text-zinc-700 dark:text-zinc-300">{lead.lead_score || "Unscored"}</span> • Status:{" "}
                      <span className="capitalize">{lead.outreach_status.replace("_", " ")}</span>
                    </div>
                  </div>
                  <Link
                    href={`/leads?highlight=${lead.id}`}
                    className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
                  >
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Safety & Compliance Box */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center gap-2 mb-3 text-zinc-900 dark:text-zinc-100">
            <ShieldCheck className="h-5 w-5 text-emerald-600" />
            <h2 className="text-sm font-semibold">Honesty & Safety Rules</h2>
          </div>
          <ul className="space-y-2.5 text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
            <li className="flex items-start gap-2">
              <span className="font-bold text-zinc-400">1.</span>
              <span><strong>No unsolicited automated cold DMs.</strong> All outreach drafts require manual human review and copying.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-zinc-400">2.</span>
              <span><strong>Factual evidence checks.</strong> We verify website status without falsely claiming certainty.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-zinc-400">3.</span>
              <span><strong>Zero password storage.</strong> Uses only official Meta APIs and strictly local Ollama inference.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold text-zinc-400">4.</span>
              <span><strong>Clear opt-outs.</strong> Businesses marked &ldquo;do not contact&rdquo; are strictly respected.</span>
            </li>
          </ul>

          <div className="mt-5 border-t border-zinc-100 pt-4 dark:border-zinc-800">
            <Link
              href="/settings"
              className="text-xs font-medium text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100 flex items-center gap-1"
            >
              Configure Abenzo Profile & FAQs <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
