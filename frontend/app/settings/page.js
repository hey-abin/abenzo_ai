"use client";

import { useEffect, useState } from "react";
import { 
  Settings as SettingsIcon, 
  Database, 
  Cpu, 
  Building, 
  CheckCircle, 
  AlertCircle, 
  RefreshCw, 
  Save, 
  Plus, 
  Trash2,
  Shield,
  HelpCircle
} from "lucide-react";
import InstagramIcon from "@/components/InstagramIcon";
import { 
  fetchSystemHealth, 
  fetchBusinessProfile, 
  updateBusinessProfile, 
  fetchMetaStatus,
  testMetaConnection
} from "@/lib/api";

export default function SettingsPage() {
  const [health, setHealth] = useState(null);
  const [metaStatus, setMetaStatus] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [testingMeta, setTestingMeta] = useState(false);

  const loadAll = () => {
    setLoading(true);
    Promise.all([
      fetchSystemHealth(),
      fetchMetaStatus(),
      fetchBusinessProfile()
    ])
      .then(([h, m, p]) => {
        setHealth(h);
        setMetaStatus(m);
        setProfile(p);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Settings load error:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleTestMeta = async () => {
    setTestingMeta(true);
    try {
      const res = await testMetaConnection();
      setMetaStatus(res);
      if (res.configured) {
        alert(`Successfully verified Instagram connection for @${res.username}!`);
      } else {
        alert(`Connection test: ${res.status}. ${res.error_details || res.guidance}`);
      }
    } catch (err) {
      alert("Failed to test connection: " + err.message);
    } finally {
      setTestingMeta(false);
    }
  };

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setSaveSuccess(false);
    try {
      const updated = await updateBusinessProfile(profile);
      setProfile(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      alert("Failed to save profile: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAddFaq = () => {
    setProfile({
      ...profile,
      approved_faq: [
        ...(profile.approved_faq || []),
        { question: "New FAQ Question?", answer: "Approved factual answer here." }
      ]
    });
  };

  const handleRemoveFaq = (index) => {
    const updated = [...profile.approved_faq];
    updated.splice(index, 1);
    setProfile({ ...profile, approved_faq: updated });
  };

  const handleFaqChange = (index, field, value) => {
    const updated = [...profile.approved_faq];
    updated[index][field] = value;
    setProfile({ ...profile, approved_faq: updated });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            System Settings & Abenzo Profile
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Monitor local Ollama AI health, database status, Meta integration requirements, and configure approved business FAQs.
          </p>
        </div>
        <button
          onClick={loadAll}
          className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Diagnostics
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Diagnostics Side Column */}
        <div className="space-y-6 lg:col-span-1">
          {/* Ollama Health Card */}
          <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center justify-between mb-3">
              <span className="font-semibold text-xs text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                <Cpu className="h-4 w-4 text-purple-600" />
                Local Ollama AI
              </span>
              {health?.ollama?.reachable ? (
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400">
                  Online
                </span>
              ) : (
                <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-800 dark:bg-red-950/60 dark:text-red-400">
                  Offline
                </span>
              )}
            </div>

            <div className="space-y-2 text-xs text-zinc-600 dark:text-zinc-400">
              <div className="flex justify-between">
                <span>Endpoint:</span>
                <span className="font-mono text-zinc-900 dark:text-zinc-100">{health?.ollama?.base_url || "http://127.0.0.1:11434"}</span>
              </div>
              <div className="flex justify-between">
                <span>Target Model:</span>
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">{health?.ollama?.model || "qwen2.5:3b"}</span>
              </div>
              <div className="flex justify-between">
                <span>Model Installed:</span>
                <span>{health?.ollama?.model_installed ? "Yes (Ready)" : "No"}</span>
              </div>
              <div className="flex justify-between">
                <span>Ping Latency:</span>
                <span>{health?.ollama?.latency_ms ? `${health.ollama.latency_ms} ms` : "—"}</span>
              </div>
            </div>
          </div>

          {/* SQLite DB Card */}
          <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center justify-between mb-3">
              <span className="font-semibold text-xs text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                <Database className="h-4 w-4 text-blue-600" />
                Local SQLite Database
              </span>
              <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400">
                Active
              </span>
            </div>

            <div className="space-y-2 text-xs text-zinc-600 dark:text-zinc-400">
              <div className="flex justify-between">
                <span>Mode:</span>
                <span className="text-zinc-900 dark:text-zinc-100">SQLite 3 (WAL Mode)</span>
              </div>
              <div className="flex justify-between">
                <span>Stored Leads:</span>
                <span className="font-bold text-zinc-900 dark:text-zinc-100">{health?.database?.leads_count ?? 0}</span>
              </div>
              <div className="truncate text-[10px] text-zinc-400 mt-2" title={health?.database?.path}>
                Path: {health?.database?.path}
              </div>
            </div>
          </div>

          {/* Meta Instagram Status Card */}
          <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center justify-between mb-3">
              <span className="font-semibold text-xs text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                <InstagramIcon className="h-4 w-4 text-pink-600" />
                Meta Instagram Connection
              </span>
              {metaStatus?.status === "connected" ? (
                <span className="flex items-center gap-1 rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Connected
                </span>
              ) : metaStatus?.status === "error" ? (
                <span className="rounded bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-800 dark:bg-red-950/60 dark:text-red-400">
                  Error
                </span>
              ) : (
                <span className="rounded bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  Not Connected
                </span>
              )}
            </div>

            {/* Profile info if connected */}
            {metaStatus?.configured && metaStatus?.username ? (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 mb-3 dark:border-zinc-800 dark:bg-zinc-800/40">
                <div className="flex items-center gap-3">
                  {metaStatus.profile_picture_url ? (
                    <img
                      src={metaStatus.profile_picture_url}
                      alt={metaStatus.username}
                      className="h-10 w-10 rounded-full border border-zinc-200 object-cover dark:border-zinc-700"
                    />
                  ) : (
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pink-100 text-pink-600 font-bold text-xs">
                      IG
                    </div>
                  )}
                  <div>
                    <div className="font-bold text-xs text-zinc-900 dark:text-zinc-100 flex items-center gap-1">
                      @{metaStatus.username}
                      <span className="rounded bg-pink-50 text-[10px] font-medium text-pink-700 px-1 py-0.2 border border-pink-200 dark:bg-pink-950/40 dark:text-pink-400 dark:border-pink-800">
                        {metaStatus.account_type || "Business"}
                      </span>
                    </div>
                    <div className="text-[11px] text-zinc-500">
                      {metaStatus.profile_name || "Abenzo Professional Account"}
                    </div>
                    <div className="text-[10px] text-zinc-400">
                      ID: {metaStatus.account_id} • Host: {metaStatus.api_host}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            <p className="text-xs text-zinc-600 dark:text-zinc-400 mb-3">
              {metaStatus?.guidance}
            </p>

            {metaStatus?.error_details && (
              <div className="rounded bg-red-50 p-2 text-xs text-red-700 mb-3 border border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800">
                {metaStatus.error_details}
              </div>
            )}

            <div className="rounded bg-zinc-50 p-2.5 text-[11px] space-y-1.5 mb-3 dark:bg-zinc-800/40">
              <div className="font-semibold text-zinc-800 dark:text-zinc-200">
                Verified Capabilities:
              </div>
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>Profile Access (GET /me):</span>
                <span className={metaStatus?.capabilities?.basic_profile ? "text-emerald-600 font-semibold" : "text-zinc-400"}>
                  {metaStatus?.capabilities?.basic_profile ? "Verified Active" : "Pending"}
                </span>
              </div>
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>Media & Comments Access:</span>
                <span className={metaStatus?.capabilities?.media_access ? "text-emerald-600 font-semibold" : "text-zinc-400"}>
                  {metaStatus?.capabilities?.media_access ? "Verified Active" : "Pending"}
                </span>
              </div>
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>Direct Messaging Access:</span>
                <span className={metaStatus?.capabilities?.messaging_conversations ? "text-emerald-600 font-semibold" : "text-zinc-400"}>
                  {metaStatus?.capabilities?.messaging_conversations ? "Verified Active" : "Pending"}
                </span>
              </div>
              <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                <span>Automated Cold DM:</span>
                <span className="text-red-500 font-semibold">Forbidden by Policy</span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-[10px] text-zinc-400">
                {metaStatus?.tested_at ? `Checked ${new Date(metaStatus.tested_at).toLocaleTimeString()}` : ""}
              </span>
              <button
                type="button"
                onClick={handleTestMeta}
                disabled={testingMeta}
                className="inline-flex items-center gap-1 rounded border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
              >
                <RefreshCw className={`h-3 w-3 ${testingMeta ? "animate-spin" : ""}`} />
                {testingMeta ? "Testing..." : "Test Connection"}
              </button>
            </div>
          </div>
        </div>

        {/* Business Profile Editor */}
        <div className="lg:col-span-2 rounded-lg border border-zinc-200 bg-white p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between border-b border-zinc-100 pb-3 mb-4 dark:border-zinc-800">
            <div>
              <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                <Building className="h-4 w-4 text-zinc-600" />
                Abenzo Business Profile & Approved FAQs
              </h2>
              <p className="text-xs text-zinc-500">
                The local AI references these exact facts when drafting replies and qualification notes.
              </p>
            </div>
            {saveSuccess && (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400">
                <CheckCircle className="h-3.5 w-3.5" /> Saved!
              </span>
            )}
          </div>

          {profile && (
            <form onSubmit={handleSaveProfile} className="space-y-4 text-xs">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Agency Name
                  </label>
                  <input
                    type="text"
                    value={profile.agency_name}
                    onChange={(e) => setProfile({ ...profile, agency_name: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>

                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Contact Email
                  </label>
                  <input
                    type="email"
                    value={profile.contact_email}
                    onChange={(e) => setProfile({ ...profile, contact_email: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Tagline / Core Mission
                </label>
                <input
                  type="text"
                  value={profile.tagline}
                  onChange={(e) => setProfile({ ...profile, tagline: e.target.value })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Services Offered (one per line)
                </label>
                <textarea
                  rows="3"
                  value={(profile.services || []).join("\n")}
                  onChange={(e) => setProfile({ ...profile, services: e.target.value.split("\n").filter(Boolean) })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Portfolio URLs (one per line)
                </label>
                <textarea
                  rows="2"
                  value={(profile.portfolio_urls || []).join("\n")}
                  onChange={(e) => setProfile({ ...profile, portfolio_urls: e.target.value.split("\n").filter(Boolean) })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              {/* Approved FAQs */}
              <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                      Approved FAQ Answers
                    </span>
                    <p className="text-[11px] text-zinc-500">
                      AI is permitted to quote these answers directly. If unknown, AI must defer to human follow-up.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleAddFaq}
                    className="inline-flex items-center gap-1 rounded border border-zinc-300 bg-white px-2 py-1 text-[11px] font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                  >
                    <Plus className="h-3 w-3" /> Add FAQ
                  </button>
                </div>

                <div className="space-y-3">
                  {(profile.approved_faq || []).map((faq, idx) => (
                    <div key={idx} className="rounded-md border border-zinc-200 p-3 bg-zinc-50/50 dark:border-zinc-700 dark:bg-zinc-800/30 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-[11px] text-zinc-600 dark:text-zinc-400">
                          FAQ #{idx + 1}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleRemoveFaq(idx)}
                          className="text-zinc-400 hover:text-red-600"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      <input
                        type="text"
                        placeholder="Question"
                        value={faq.question}
                        onChange={(e) => handleFaqChange(idx, "question", e.target.value)}
                        className="w-full rounded border border-zinc-300 p-1.5 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                      />
                      <textarea
                        rows="2"
                        placeholder="Approved Answer"
                        value={faq.answer}
                        onChange={(e) => handleFaqChange(idx, "answer", e.target.value)}
                        className="w-full rounded border border-zinc-300 p-1.5 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Tone & Policy */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 pt-2">
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Tone Guidelines
                  </label>
                  <textarea
                    rows="2"
                    value={profile.tone_guidelines}
                    onChange={(e) => setProfile({ ...profile, tone_guidelines: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Allowed Claims
                  </label>
                  <textarea
                    rows="2"
                    value={profile.allowed_claims}
                    onChange={(e) => setProfile({ ...profile, allowed_claims: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end pt-4 border-t border-zinc-100 dark:border-zinc-800">
                <button
                  type="submit"
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-4 py-2 font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                >
                  <Save className="h-4 w-4" />
                  {saving ? "Saving..." : "Save Business Profile"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
