"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { 
  Sparkles, 
  Play, 
  Square, 
  RefreshCw, 
  CheckCircle2, 
  AlertCircle, 
  ExternalLink, 
  Copy, 
  Check, 
  Instagram, 
  Hash, 
  ShieldCheck, 
  Eye, 
  ArrowRight,
  TrendingUp,
  Layers,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Flame,
  HelpCircle,
  Info
} from "lucide-react";
import InstagramIcon from "@/components/InstagramIcon";
import { 
  startCampaign, 
  fetchActiveCampaign, 
  cancelCampaign, 
  fetchCampaigns, 
  fetchResearchedHashtags,
  updateLead
} from "@/lib/api";

const STAGES = [
  { key: "checking_apis", label: "1. API & Permission Verification" },
  { key: "researching_hashtags", label: "2. AI Hashtag Research" },
  { key: "discovering_media", label: "3. Discovering Posts & Reels" },
  { key: "qualifying", label: "4. Content & Niche Qualification" },
  { key: "generating_drafts", label: "5. Personalized Outreach Drafts" },
  { key: "saving_crm", label: "6. Neon CRM Persistence" },
  { key: "completed", label: "7. Campaign Complete" }
];

export default function ProspectingCampaignDashboard({ onLeadUpdated }) {
  const [activeCampaign, setActiveCampaign] = useState(null);
  const [loading, setLoading] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [updatingLeadId, setUpdatingLeadId] = useState(null);
  const [showHashtagDrawer, setShowHashtagDrawer] = useState(false);
  const [hashtags, setHashtags] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [campaignHistory, setCampaignHistory] = useState([]);
  const pollIntervalRef = useRef(null);

  // Initial load
  useEffect(() => {
    loadActiveCampaign();
    loadHashtags();
    loadHistory();
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // Set up polling when a campaign is running
  useEffect(() => {
    if (activeCampaign && activeCampaign.status === "running") {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(loadActiveCampaign, 2000);
      }
    } else {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }
  }, [activeCampaign?.status]);

  const loadActiveCampaign = async () => {
    try {
      const data = await fetchActiveCampaign();
      setActiveCampaign(data);
    } catch (err) {
      console.error("Failed to load active campaign:", err);
    }
  };

  const loadHashtags = async () => {
    try {
      const tags = await fetchResearchedHashtags();
      setHashtags(tags || []);
    } catch (e) {
      console.error("Failed to load hashtags:", e);
    }
  };

  const loadHistory = async () => {
    try {
      const list = await fetchCampaigns();
      setCampaignHistory(list || []);
    } catch (e) {
      console.error("Failed to load history:", e);
    }
  };

  const handleStartCampaign = async () => {
    setError(null);
    setLoading(true);
    try {
      const newCamp = await startCampaign();
      setActiveCampaign(newCamp);
      loadHistory();
    } catch (err) {
      setError(err.message || "Failed to start prospecting campaign");
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!activeCampaign) return;
    setCanceling(true);
    try {
      const updated = await cancelCampaign(activeCampaign.id);
      setActiveCampaign(updated);
      loadHistory();
    } catch (err) {
      setError(err.message || "Failed to cancel campaign");
    } finally {
      setCanceling(false);
    }
  };

  const handleCopyDraft = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const handleUpdateStatus = async (leadId, newStatus) => {
    setUpdatingLeadId(leadId);
    try {
      await updateLead(leadId, { outreach_status: newStatus });
      // Update local state in campaign summary if present
      if (activeCampaign && activeCampaign.results_summary) {
        setActiveCampaign(prev => ({
          ...prev,
          results_summary: prev.results_summary.map(item => 
            item.lead_id === leadId ? { ...item, outreach_status: newStatus } : item
          )
        }));
      }
      if (onLeadUpdated) onLeadUpdated();
    } catch (err) {
      console.error("Failed to update lead status:", err);
    } finally {
      setUpdatingLeadId(null);
    }
  };

  const isRunning = activeCampaign?.status === "running";
  const currentStageIndex = STAGES.findIndex(s => s.key === activeCampaign?.stage);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-gradient-to-b from-white via-zinc-50/50 to-white p-6 shadow-sm dark:border-zinc-800/80 dark:from-zinc-900/90 dark:via-zinc-900/40 dark:to-zinc-950">
      {/* Background ambient glow effect */}
      <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-pink-500/10 blur-3xl dark:from-indigo-500/20 dark:to-purple-500/10" />

      {/* Header section with One-Button Campaign trigger */}
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-purple-200 bg-purple-50 px-2.5 py-0.5 text-xs font-semibold text-purple-700 dark:border-purple-800/60 dark:bg-purple-950/40 dark:text-purple-300">
            <Sparkles className="h-3 w-3 animate-pulse text-purple-600 dark:text-purple-400" />
            Autonomous Prospecting Engine
          </div>
          <h2 className="mt-1 text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 sm:text-2xl">
            Instagram Prospecting Agent
          </h2>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400 sm:text-sm">
            Researches relevant hashtags, discovers verified public content, qualifies genuine digital opportunities, and drafts personalized outreach.
          </p>
        </div>

        {/* The One Prominent Button */}
        <div className="flex flex-wrap items-center gap-2.5">
          {isRunning ? (
            <button
              onClick={handleCancel}
              disabled={canceling}
              className="group inline-flex items-center gap-2 rounded-xl border border-rose-300 bg-rose-50 px-4 py-2.5 text-xs font-semibold text-rose-700 transition-all hover:bg-rose-100 hover:shadow-sm dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300 dark:hover:bg-rose-900/60"
            >
              <Square className={`h-3.5 w-3.5 fill-current ${canceling ? "animate-spin" : ""}`} />
              {canceling ? "Canceling..." : "Cancel Campaign"}
            </button>
          ) : (
            <button
              id="start-prospecting-campaign-btn"
              onClick={handleStartCampaign}
              disabled={loading}
              className="group relative inline-flex items-center gap-2.5 overflow-hidden rounded-xl bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-md shadow-indigo-500/20 transition-all hover:scale-[1.02] hover:shadow-lg hover:shadow-indigo-500/30 active:scale-[0.98] disabled:opacity-50 dark:shadow-indigo-900/30"
            >
              <div className="absolute inset-0 bg-white/10 opacity-0 transition-opacity group-hover:opacity-100" />
              <Play className={`h-4 w-4 fill-white ${loading ? "animate-spin" : ""}`} />
              <span>Start AI Prospecting Campaign</span>
            </button>
          )}

          <button
            onClick={() => {
              loadActiveCampaign();
              loadHashtags();
            }}
            title="Refresh Status"
            className="rounded-xl border border-zinc-200 bg-white p-2.5 text-zinc-600 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <RefreshCw className={`h-4 w-4 ${isRunning ? "animate-spin text-purple-600" : ""}`} />
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-xs text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/50 dark:text-rose-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
          <div className="flex-1">
            <span className="font-semibold">Notice:</span> {error}
          </div>
        </div>
      )}

      {/* Active or Last Campaign Live View */}
      {activeCampaign && (
        <div className="mt-6 space-y-5">
          {/* Status Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-200/70 bg-white/80 p-4 backdrop-blur-xs dark:border-zinc-800/70 dark:bg-zinc-900/80">
            <div className="flex items-center gap-3">
              <span className="relative flex h-3 w-3">
                {isRunning && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-purple-400 opacity-75" />
                )}
                <span className={`relative inline-flex h-3 w-3 rounded-full ${
                  isRunning 
                    ? "bg-purple-600" 
                    : activeCampaign.status === "completed" 
                      ? "bg-emerald-500" 
                      : activeCampaign.status === "cancelled" 
                        ? "bg-amber-500" 
                        : "bg-rose-500"
                }`} />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold capitalize text-zinc-900 dark:text-zinc-100">
                    Campaign #{activeCampaign.id} • {activeCampaign.status}
                  </span>
                  <span className="text-xs text-zinc-400 dark:text-zinc-500">
                    ({new Date(activeCampaign.started_at).toLocaleTimeString()})
                  </span>
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {activeCampaign.current_step_text || "Ready"}
                </p>
              </div>
            </div>

            {/* Live Metrics Counters */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-xs">
              <div className="rounded-lg bg-zinc-50 px-2.5 py-1.5 dark:bg-zinc-800/60">
                <span className="text-zinc-400">Discovered:</span>{" "}
                <span className="font-bold text-zinc-900 dark:text-zinc-100">{activeCampaign.discovered_posts_count}</span>
              </div>
              <div className="rounded-lg bg-zinc-50 px-2.5 py-1.5 dark:bg-zinc-800/60">
                <span className="text-zinc-400">Unique Profiles:</span>{" "}
                <span className="font-bold text-zinc-900 dark:text-zinc-100">{activeCampaign.unique_profiles_count}</span>
              </div>
              <div className="rounded-lg bg-emerald-50 px-2.5 py-1.5 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
                <span className="opacity-75">Qualified:</span>{" "}
                <span className="font-bold">{activeCampaign.qualified_prospects_count}</span>
              </div>
              <div className="rounded-lg bg-indigo-50 px-2.5 py-1.5 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-400">
                <span className="opacity-75">Drafts:</span>{" "}
                <span className="font-bold">{activeCampaign.drafts_generated_count}</span>
              </div>
              <div className="rounded-lg bg-zinc-50 px-2.5 py-1.5 text-zinc-500 dark:bg-zinc-800/60">
                <span className="opacity-75">Duplicates:</span>{" "}
                <span className="font-bold">{activeCampaign.duplicates_count}</span>
              </div>
            </div>
          </div>

          {/* Stepper Progress Bar (when running or completed) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
              <span>Pipeline Stage: {activeCampaign.stage?.replace("_", " ").toUpperCase()}</span>
              {isRunning && <span className="animate-pulse text-purple-600 dark:text-purple-400 font-semibold">Live Processing</span>}
            </div>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-7">
              {STAGES.map((s, idx) => {
                const isPassed = currentStageIndex > idx || activeCampaign.status === "completed";
                const isCurrent = currentStageIndex === idx && isRunning;
                return (
                  <div
                    key={s.key}
                    className={`rounded-lg px-2 py-1.5 text-center text-[10px] font-semibold transition-all ${
                      isCurrent
                        ? "bg-purple-600 text-white shadow-xs animate-pulse"
                        : isPassed
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800/50"
                          : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800/50 dark:text-zinc-500"
                    }`}
                  >
                    {s.label}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Researched Hashtags Display */}
          {activeCampaign.selected_hashtags && activeCampaign.selected_hashtags.length > 0 && (
            <div className="rounded-xl border border-zinc-200/70 bg-white/70 p-4 dark:border-zinc-800/70 dark:bg-zinc-900/60">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                  <Hash className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400" />
                  AI-Selected Hashtags & Rationale
                </div>
                <span className="text-[10px] text-zinc-500">
                  Grounded in Abenzo's web services knowledge base
                </span>
              </div>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {activeCampaign.selected_hashtags.map((ht, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col justify-between rounded-lg border border-zinc-100 bg-zinc-50/70 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-950/40"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-purple-700 dark:text-purple-300">
                        #{ht.hashtag}
                      </span>
                      <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[9px] font-medium text-purple-800 dark:bg-purple-900/60 dark:text-purple-200">
                        {ht.service_fit || "Web Services"}
                      </span>
                    </div>
                    <p className="mt-1.5 text-[11px] text-zinc-600 dark:text-zinc-400 leading-relaxed">
                      {ht.rationale}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Meta API & Provider Transparency Card */}
          {activeCampaign.meta_status && (
            <div className="rounded-xl border border-zinc-200/60 bg-zinc-50/50 p-3.5 text-xs text-zinc-600 dark:border-zinc-800/60 dark:bg-zinc-900/40 dark:text-zinc-400">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-medium text-zinc-900 dark:text-zinc-200">
                  <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  Meta Graph API & Discovery Engine Status
                </div>
                <span className="text-[10px] text-zinc-400">Official Graph API Protocol</span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed">
                {activeCampaign.meta_status.guidance || "Connected to Meta Graph API."}
              </p>
              {activeCampaign.meta_status.missing_permission && (
                <div className="mt-2 rounded-md bg-amber-50 p-2 text-[10px] text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                  <span className="font-semibold">Documented Permission State:</span> {activeCampaign.meta_status.missing_permission}
                </div>
              )}
            </div>
          )}

          {/* Provider Failure & Diagnostic Details Banner */}
          {(activeCampaign.status === "failed" || (activeCampaign.provider_failures && activeCampaign.provider_failures.length > 0 && activeCampaign.discovered_posts_count === 0)) && (
            <div className="rounded-xl border border-rose-200 bg-rose-50/70 p-4 text-xs text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200 space-y-2.5">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
                <h4 className="font-semibold text-rose-950 dark:text-rose-100">
                  {activeCampaign.status === "failed" ? "Discovery Provider Limitations / Failure" : "Discovery Provider Status & Fallback Log"}
                </h4>
              </div>
              <p className="text-[11px] leading-relaxed text-rose-900/90 dark:text-rose-200/90">
                {activeCampaign.error_message || activeCampaign.current_step_text}
              </p>

              {activeCampaign.provider_failures && activeCampaign.provider_failures.length > 0 && (
                <div className="rounded-lg bg-rose-100/60 p-2.5 dark:bg-rose-900/30 font-mono text-[10px] space-y-1">
                  <span className="font-sans font-semibold text-rose-950 dark:text-rose-100 block">Logged Provider Events:</span>
                  <ul className="list-disc list-inside space-y-0.5">
                    {activeCampaign.provider_failures.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="rounded-lg bg-white/70 p-2.5 text-[11px] text-zinc-700 dark:bg-zinc-900/70 dark:text-zinc-300 border border-rose-200/50 dark:border-rose-900/40">
                <p className="font-semibold text-zinc-900 dark:text-zinc-100 mb-0.5">💡 Production Search Guidance:</p>
                <p className="leading-relaxed">
                  Cloud hosting platforms (such as Render) are frequently blocked by DuckDuckGo with HTTP 202 Bot Challenge.
                  Add <code>SERPER_API_KEY</code> to your Render environment variables to activate Google Search API fallback for 100% reliable discovery.
                </p>
              </div>
            </div>
          )}

          {/* Clean Zero Results Notice (Search Succeeded, but No Posts Found) */}
          {activeCampaign.status === "completed" && activeCampaign.discovered_posts_count === 0 && (!activeCampaign.provider_failures || activeCampaign.provider_failures.length === 0 || activeCampaign.provider_failures[0]?.includes("HTTP 200")) && (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-6 text-center text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-400 space-y-2">
              <Info className="h-6 w-6 text-zinc-400 mx-auto" />
              <h4 className="font-semibold text-zinc-800 dark:text-zinc-200">No Public Posts Found for These Specific Hashtags</h4>
              <p className="max-w-md mx-auto text-[11px] leading-relaxed">
                The search providers executed normally (HTTP 200 OK), but returned 0 indexed Instagram posts or Reels under the current hashtags. 
                The AI will explore alternative commercial niches on the next campaign run.
              </p>
            </div>
          )}

          {/* Campaign Summary & Review Queue */}
          {activeCampaign.results_summary && activeCampaign.results_summary.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                  <span>Prospect Review Queue ({activeCampaign.results_summary.length} Qualified)</span>
                </h3>
                <Link
                  href="/leads"
                  className="inline-flex items-center gap-1 text-xs font-medium text-purple-600 hover:underline dark:text-purple-400"
                >
                  View in Full CRM <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              <div className="grid grid-cols-1 gap-3.5">
                {activeCampaign.results_summary.map((lead) => (
                  <div
                    key={lead.lead_id || lead.instagram_handle}
                    className="flex flex-col rounded-xl border border-zinc-200 bg-white p-4 shadow-xs transition-shadow hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
                  >
                    {/* Header info */}
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-zinc-900 dark:text-zinc-100 text-sm">
                            {lead.business_name}
                          </span>
                          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                            Fit Score: {lead.lead_score}/100
                          </span>
                          <span className="rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-medium text-purple-800 dark:bg-purple-950/60 dark:text-purple-300">
                            #{lead.discovery_hashtag}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                          {lead.instagram_handle && (
                            <span className="flex items-center gap-1">
                              <InstagramIcon className="h-3 w-3 text-pink-600" />
                              @{lead.instagram_handle}
                            </span>
                          )}
                          <span className="text-zinc-300 dark:text-zinc-700">•</span>
                          <span>{lead.recommended_service}</span>
                        </div>
                      </div>

                      {/* Action buttons: Open Profile & Mark Reviewed */}
                      <div className="flex items-center gap-2">
                        {lead.instagram_url && (
                          <a
                            href={lead.instagram_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
                          >
                            <ExternalLink className="h-3 w-3" />
                            Open Profile
                          </a>
                        )}
                        {lead.lead_id && (
                          <select
                            value={lead.outreach_status || "draft"}
                            disabled={updatingLeadId === lead.lead_id}
                            onChange={(e) => handleUpdateStatus(lead.lead_id, e.target.value)}
                            className="rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-700 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                          >
                            <option value="draft">Draft Ready</option>
                            <option value="reviewed">Mark Reviewed</option>
                            <option value="contacted">Mark Contacted</option>
                            <option value="replied">Replied</option>
                            <option value="interested">Interested</option>
                            <option value="consultation_requested">Consultation Requested</option>
                            <option value="converted">Won / Converted</option>
                            <option value="not_interested">Lost / Not Interested</option>
                          </select>
                        )}
                      </div>
                    </div>

                    {/* Observable Evidence pill */}
                    {lead.evidence && lead.evidence.length > 0 && (
                      <div className="mt-3 rounded-lg bg-zinc-50/80 p-2 text-[11px] text-zinc-600 dark:bg-zinc-950/40 dark:text-zinc-400">
                        <span className="font-semibold text-zinc-800 dark:text-zinc-200">Public Evidence:</span>{" "}
                        {lead.evidence.join(" ")}
                      </div>
                    )}

                    {/* Personalized Outreach Draft with Copy Message button */}
                    {lead.personalized_dm && (
                      <div className="mt-3 rounded-xl border border-purple-100 bg-purple-50/50 p-3.5 dark:border-purple-900/40 dark:bg-purple-950/20">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700 dark:text-purple-300">
                            AI Personalized Outreach Draft (Non-spam, evidence-backed)
                          </span>
                          <button
                            onClick={() => handleCopyDraft(lead.personalized_dm, lead.lead_id || lead.instagram_handle)}
                            className="inline-flex items-center gap-1.5 rounded-md bg-purple-600 px-2.5 py-1 text-[11px] font-medium text-white shadow-xs transition-colors hover:bg-purple-700 dark:bg-purple-600 dark:hover:bg-purple-500"
                          >
                            {copiedId === (lead.lead_id || lead.instagram_handle) ? (
                              <>
                                <Check className="h-3 w-3" />
                                Copied!
                              </>
                            ) : (
                              <>
                                <Copy className="h-3 w-3" />
                                Copy Message
                              </>
                            )}
                          </button>
                        </div>
                        <p className="text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed font-sans select-all">
                          &ldquo;{lead.personalized_dm}&rdquo;
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Drawer toggle for historical researched hashtags */}
      <div className="mt-6 border-t border-zinc-100 pt-4 dark:border-zinc-800/80 flex items-center justify-between text-xs text-zinc-500">
        <button
          onClick={() => setShowHashtagDrawer(!showHashtagDrawer)}
          className="inline-flex items-center gap-1 text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100 font-medium"
        >
          <Hash className="h-3.5 w-3.5" />
          Researched Hashtags Database ({hashtags.length})
          {showHashtagDrawer ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>

        <span className="text-[11px] text-zinc-400">
          Complies with Meta API policies • Zero automated unsolicited cold DMs
        </span>
      </div>

      {/* Researched Hashtags History Drawer */}
      {showHashtagDrawer && (
        <div className="mt-3 rounded-xl border border-zinc-200/80 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/50 text-xs">
          <div className="mb-2 font-semibold text-zinc-900 dark:text-zinc-100">
            Previously Researched Hashtags & Performance
          </div>
          {hashtags.length === 0 ? (
            <p className="text-zinc-400">No hashtags researched yet. Start a campaign to research hashtags.</p>
          ) : (
            <div className="divide-y divide-zinc-200/50 dark:divide-zinc-800/60 max-h-48 overflow-y-auto pr-1">
              {hashtags.map((h) => (
                <div key={h.hashtag} className="py-2 flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-purple-700 dark:text-purple-300">#{h.hashtag}</span>
                    <span className="ml-2 text-zinc-500 text-[11px]">{h.service_fit}</span>
                  </div>
                  <div className="flex items-center gap-3 text-zinc-500 text-[11px]">
                    <span>Searched: {h.times_used}x</span>
                    <span className="font-medium text-emerald-600 dark:text-emerald-400">
                      {h.qualified_found} qualified
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
