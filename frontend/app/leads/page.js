"use client";

import { Suspense, useEffect, useState, useTransition } from "react";
import { useSearchParams } from "next/navigation";
import { 
  Search, 
  Filter, 
  Plus, 
  Upload, 
  Download, 
  Sparkles, 
  Globe, 
  Copy, 
  Check, 
  ExternalLink, 
  Trash2, 
  RefreshCw,
  AlertTriangle,
  Info,
  Compass,
  CheckSquare,
  Square
} from "lucide-react";
import InstagramIcon from "@/components/InstagramIcon";
import { 
  fetchLeads, 
  createLead, 
  updateLead, 
  deleteLead, 
  checkWebsite, 
  qualifyLeadAI, 
  importCSV, 
  getExportCSVUrl,
  discoverLeads,
  importDiscoveredLeads
} from "@/lib/api";

const INDIAN_STATES = [
  "All States", "Andhra Pradesh", "Assam", "Bihar", "Delhi", "Goa", "Gujarat", 
  "Haryana", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", 
  "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal"
];

const WEBSITE_STATUS_COLORS = {
  found: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800",
  not_found: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800",
  uncertain: "bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700"
};

const OUTREACH_STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "draft", label: "Draft" },
  { value: "reviewed", label: "Reviewed" },
  { value: "contacted", label: "Contacted" },
  { value: "replied", label: "Replied" },
  { value: "converted", label: "Converted" },
  { value: "not_interested", label: "Not Interested" },
  { value: "do_not_contact", label: "Do Not Contact (Opt-Out)" },
];

function LeadsContent() {
  const searchParams = useSearchParams();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("All States");
  const [statusFilter, setStatusFilter] = useState("");
  const [webFilter, setWebFilter] = useState("");
  
  // Modals & form state
  const [showAddModal, setShowAddModal] = useState(false);
  const [newLead, setNewLead] = useState({
    business_name: "",
    industry: "",
    state: "Kerala",
    website_url: "",
    instagram_url: "",
    source_url: ""
  });
  const [formError, setFormError] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);

  // Active action spinners
  const [analyzingId, setAnalyzingId] = useState(null);
  const [checkingWebId, setCheckingWebId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // Selected lead for detail/edit
  const [selectedLead, setSelectedLead] = useState(null);
  const [editDraft, setEditDraft] = useState("");

  // Lead Discovery state
  const [showDiscoverModal, setShowDiscoverModal] = useState(false);
  const [discoveryQuery, setDiscoveryQuery] = useState({
    niche: "",
    location: "Kerala",
    keywords: ""
  });
  const [discovering, setDiscovering] = useState(false);
  const [discoveryResults, setDiscoveryResults] = useState([]);
  const [discoveryError, setDiscoveryError] = useState("");
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [importingDiscovered, setImportingDiscovered] = useState(false);
  const [discoveryStats, setDiscoveryStats] = useState(null);

  const loadLeads = () => {
    setLoading(true);
    fetchLeads({
      search: search || undefined,
      state: stateFilter !== "All States" ? stateFilter : undefined,
      outreach_status: statusFilter || undefined,
      website_status: webFilter || undefined
    })
      .then((data) => {
        setLeads(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to load leads:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadLeads();
  }, [stateFilter, statusFilter, webFilter]);

  // Handle URL params on initial load
  useEffect(() => {
    if (searchParams.get("action") === "new") {
      setShowAddModal(true);
    }
  }, [searchParams]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadLeads();
  };

  const handleCreateLead = async (e) => {
    e.preventDefault();
    if (!newLead.business_name.trim()) {
      setFormError("Business name is required.");
      return;
    }
    setFormError("");
    setFormSubmitting(true);
    try {
      await createLead(newLead);
      setShowAddModal(false);
      setNewLead({
        business_name: "",
        industry: "",
        state: "Kerala",
        website_url: "",
        instagram_url: "",
        source_url: ""
      });
      loadLeads();
    } catch (err) {
      setFormError(err.message || "Failed to create lead");
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleRunAI = async (lead) => {
    setAnalyzingId(lead.id);
    try {
      const updated = await qualifyLeadAI(lead.id);
      setLeads((prev) => prev.map((l) => (l.id === lead.id ? updated : l)));
      if (selectedLead?.id === lead.id) {
        setSelectedLead(updated);
        setEditDraft(updated.personalized_dm);
      }
    } catch (err) {
      alert("AI Qualification Error: " + err.message);
    } finally {
      setAnalyzingId(null);
    }
  };

  const handleCheckWebsite = async (lead) => {
    setCheckingWebId(lead.id);
    try {
      const updated = await checkWebsite(lead.id);
      setLeads((prev) => prev.map((l) => (l.id === lead.id ? updated : l)));
      if (selectedLead?.id === lead.id) {
        setSelectedLead(updated);
      }
    } catch (err) {
      alert("Website check failed: " + err.message);
    } finally {
      setCheckingWebId(null);
    }
  };

  const handleStatusChange = async (leadId, newStatus) => {
    try {
      const updated = await updateLead(leadId, { outreach_status: newStatus });
      setLeads((prev) => prev.map((l) => (l.id === leadId ? updated : l)));
      if (selectedLead?.id === leadId) setSelectedLead(updated);
    } catch (err) {
      alert("Failed to update status");
    }
  };

  const handleSaveDraft = async () => {
    if (!selectedLead) return;
    try {
      const updated = await updateLead(selectedLead.id, { personalized_dm: editDraft });
      setLeads((prev) => prev.map((l) => (l.id === selectedLead.id ? updated : l)));
      setSelectedLead(updated);
      alert("Personalized DM draft saved.");
    } catch (err) {
      alert("Failed to save draft");
    }
  };

  const handleCopyDM = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  };

  const handleDelete = async (id) => {
    if (!confirm("Are you sure you want to delete this lead?")) return;
    try {
      await deleteLead(id);
      setLeads((prev) => prev.filter((l) => l.id !== id));
      if (selectedLead?.id === id) setSelectedLead(null);
    } catch (err) {
      alert("Failed to delete lead");
    }
  };

  const handleCSVUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await importCSV(file);
      alert(`CSV Import: ${res.imported} imported, ${res.skipped} skipped.`);
      loadLeads();
    } catch (err) {
      alert("CSV Import failed: " + err.message);
    }
    e.target.value = "";
  };

  const handleRunDiscovery = async (e) => {
    e.preventDefault();
    if (!discoveryQuery.niche.trim() && !discoveryQuery.keywords.trim()) {
      setDiscoveryError("Please enter a niche or keywords to discover businesses.");
      return;
    }
    setDiscovering(true);
    setDiscoveryError("");
    setDiscoveryResults([]);
    setSelectedCandidates([]);
    setDiscoveryStats(null);
    try {
      const res = await discoverLeads({
        niche: discoveryQuery.niche,
        location: discoveryQuery.location,
        keywords: discoveryQuery.keywords,
        limit: 10
      });
      setDiscoveryResults(res.results || []);
      setDiscoveryStats({
        total_found: res.total_found,
        execution_time_ms: res.execution_time_ms,
        message: res.message
      });
      // Preselect non-duplicates
      const selectable = (res.results || [])
        .map((r, i) => (!r.is_duplicate ? i : null))
        .filter((i) => i !== null);
      setSelectedCandidates(selectable);
    } catch (err) {
      setDiscoveryError(err.message || "Discovery search failed");
    } finally {
      setDiscovering(false);
    }
  };

  const handleToggleCandidate = (index) => {
    if (selectedCandidates.includes(index)) {
      setSelectedCandidates(selectedCandidates.filter((i) => i !== index));
    } else {
      setSelectedCandidates([...selectedCandidates, index]);
    }
  };

  const handleSelectAllCandidates = () => {
    const selectable = discoveryResults
      .map((r, i) => (!r.is_duplicate ? i : null))
      .filter((i) => i !== null);
    if (selectedCandidates.length === selectable.length) {
      setSelectedCandidates([]);
    } else {
      setSelectedCandidates(selectable);
    }
  };

  const handleImportCandidates = async () => {
    if (selectedCandidates.length === 0) return;
    const itemsToImport = selectedCandidates.map((idx) => discoveryResults[idx]);
    setImportingDiscovered(true);
    try {
      const res = await importDiscoveredLeads(itemsToImport);
      alert(`Successfully imported ${res.imported_count} leads (${res.skipped_count} skipped). Website verification and AI qualification are ready.`);
      setShowDiscoverModal(false);
      setDiscoveryResults([]);
      setSelectedCandidates([]);
      loadLeads();
    } catch (err) {
      alert("Failed to import discovered leads: " + err.message);
    } finally {
      setImportingDiscovered(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            Prospect Leads
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Search, qualify with local Ollama, check website evidence, and prepare personalized outreach.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* CSV Import */}
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
            <Upload className="h-3.5 w-3.5" />
            Import CSV
            <input type="file" accept=".csv" onChange={handleCSVUpload} className="hidden" />
          </label>

          {/* CSV Export */}
          <a
            href={getExportCSVUrl()}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </a>

          {/* Discover Leads Modal Button */}
          <button
            onClick={() => setShowDiscoverModal(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300"
          >
            <Compass className="h-3.5 w-3.5" />
            Discover Leads (Live)
          </button>

          {/* Add Lead */}
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Lead
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-900 sm:flex-row sm:items-center">
        <form onSubmit={handleSearchSubmit} className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
          <input
            type="text"
            placeholder="Search business name or notes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-zinc-300 bg-transparent py-1.5 pl-9 pr-3 text-sm placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-hidden dark:border-zinc-700 dark:text-zinc-100"
          />
        </form>

        <div className="flex flex-wrap items-center gap-2">
          {/* State */}
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white py-1.5 px-2.5 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            {INDIAN_STATES.map((st) => (
              <option key={st} value={st}>{st}</option>
            ))}
          </select>

          {/* Website Status */}
          <select
            value={webFilter}
            onChange={(e) => setWebFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white py-1.5 px-2.5 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <option value="">All Web Status</option>
            <option value="found">Website Found</option>
            <option value="not_found">Not Found</option>
            <option value="uncertain">Uncertain</option>
          </select>

          {/* Outreach Status */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white py-1.5 px-2.5 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <option value="">All Outreach Status</option>
            {OUTREACH_STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>

          <button
            onClick={loadLeads}
            className="rounded-md border border-zinc-300 bg-white p-2 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
            title="Refresh list"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Main Content Layout: Table & Detail Pane */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Leads Table */}
        <div className="lg:col-span-2 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-zinc-200 bg-zinc-50 font-medium text-zinc-500 dark:border-zinc-800 dark:bg-zinc-800/50 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-3">Business</th>
                  <th className="px-3 py-3">Web Evidence</th>
                  <th className="px-3 py-3">Score</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {leads.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="p-8 text-center text-sm text-zinc-500">
                      {loading ? "Loading leads..." : "No leads found matching criteria. Click 'Add Lead' or import CSV to get started."}
                    </td>
                  </tr>
                ) : (
                  leads.map((lead) => {
                    const isSelected = selectedLead?.id === lead.id;
                    const isAnalyzing = analyzingId === lead.id;
                    const isCheckingWeb = checkingWebId === lead.id;

                    return (
                      <tr 
                        key={lead.id}
                        onClick={() => {
                          setSelectedLead(lead);
                          setEditDraft(lead.personalized_dm || "");
                        }}
                        className={`cursor-pointer transition-colors ${
                          isSelected 
                            ? "bg-zinc-50 dark:bg-zinc-800/60" 
                            : "hover:bg-zinc-50/50 dark:hover:bg-zinc-800/30"
                        }`}
                      >
                        {/* Business Info */}
                        <td className="px-4 py-3">
                          <div className="font-semibold text-zinc-900 dark:text-zinc-100">
                            {lead.business_name}
                          </div>
                          <div className="text-[11px] text-zinc-500">
                            {[lead.industry, lead.state].filter(Boolean).join(" • ") || "India"}
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            {lead.instagram_url && (
                              <a
                                href={lead.instagram_url.startsWith("http") ? lead.instagram_url : `https://${lead.instagram_url}`}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-0.5 text-[10px] text-pink-600 hover:underline dark:text-pink-400"
                              >
                                <InstagramIcon className="h-2.5 w-2.5" />
                                Instagram
                              </a>
                            )}
                            {lead.website_url && (
                              <a
                                href={lead.website_url.startsWith("http") ? lead.website_url : `https://${lead.website_url}`}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-0.5 text-[10px] text-blue-600 hover:underline dark:text-blue-400"
                              >
                                <Globe className="h-2.5 w-2.5" />
                                Site
                              </a>
                            )}
                          </div>
                        </td>

                        {/* Web Evidence */}
                        <td className="px-3 py-3">
                          <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border ${WEBSITE_STATUS_COLORS[lead.website_status] || WEBSITE_STATUS_COLORS.uncertain}`}>
                            {lead.website_status}
                          </span>
                          <div className="mt-1 max-w-[160px] truncate text-[10px] text-zinc-500" title={lead.evidence_json?.evidence_summary || "No check yet"}>
                            {lead.evidence_json?.evidence_summary || "Pending verification"}
                          </div>
                        </td>

                        {/* Score */}
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-sm font-bold ${
                              lead.lead_score >= 70 ? "text-emerald-600 dark:text-emerald-400" :
                              lead.lead_score >= 40 ? "text-amber-600 dark:text-amber-400" :
                              lead.lead_score > 0 ? "text-zinc-600 dark:text-zinc-400" : "text-zinc-400"
                            }`}>
                              {lead.lead_score || "—"}
                            </span>
                            {lead.lead_score > 0 && (
                              <span className="text-[10px] text-zinc-400">/100</span>
                            )}
                          </div>
                          {lead.recommended_service && (
                            <div className="max-w-[140px] truncate text-[10px] text-zinc-500" title={lead.recommended_service}>
                              {lead.recommended_service}
                            </div>
                          )}
                        </td>

                        {/* Status */}
                        <td className="px-3 py-3">
                          <select
                            value={lead.outreach_status}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleStatusChange(lead.id, e.target.value)}
                            className="rounded border border-zinc-200 bg-white py-0.5 px-1.5 text-[11px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                          >
                            {OUTREACH_STATUS_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        </td>

                        {/* Action Buttons */}
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleRunAI(lead)}
                              disabled={isAnalyzing}
                              title="Qualify with Local Ollama"
                              className="inline-flex items-center gap-1 rounded bg-zinc-900 px-2 py-1 text-[11px] font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                            >
                              <Sparkles className={`h-3 w-3 ${isAnalyzing ? "animate-spin" : ""}`} />
                              <span>{isAnalyzing ? "AI..." : "Qualify"}</span>
                            </button>
                            <button
                              onClick={() => handleCheckWebsite(lead)}
                              disabled={isCheckingWeb}
                              title="Verify website status"
                              className="rounded border border-zinc-200 p-1 text-zinc-600 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
                            >
                              <RefreshCw className={`h-3 w-3 ${isCheckingWeb ? "animate-spin" : ""}`} />
                            </button>
                            <button
                              onClick={() => handleDelete(lead.id)}
                              title="Delete lead"
                              className="rounded p-1 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/50"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Lead Detail & Personalized DM Drawer */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          {selectedLead ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
                <div>
                  <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">
                    {selectedLead.business_name}
                  </h2>
                  <p className="text-xs text-zinc-500">
                    ID #{selectedLead.id} • Added {new Date(selectedLead.created_at).toLocaleDateString()}
                  </p>
                </div>
                <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium border ${WEBSITE_STATUS_COLORS[selectedLead.website_status]}`}>
                  {selectedLead.website_status}
                </span>
              </div>

              {/* Website Evidence Check Card */}
              <div className="rounded-md bg-zinc-50 p-3 text-xs dark:bg-zinc-800/50">
                <div className="font-semibold text-zinc-700 dark:text-zinc-300 mb-1 flex items-center gap-1.5">
                  <Globe className="h-3.5 w-3.5 text-blue-500" />
                  Website Evidence Verification
                </div>
                <p className="text-zinc-600 dark:text-zinc-400">
                  {selectedLead.evidence_json?.evidence_summary || "No verification run yet. Click 'Check Website'."}
                </p>
                {selectedLead.website_url && (
                  <div className="mt-2">
                    <a
                      href={selectedLead.website_url.startsWith("http") ? selectedLead.website_url : `https://${selectedLead.website_url}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline dark:text-blue-400 inline-flex items-center gap-1 text-[11px]"
                    >
                      Visit {selectedLead.website_url} <ExternalLink className="h-2.5 w-2.5" />
                    </a>
                  </div>
                )}
              </div>

              {/* AI Qualification & Opportunity */}
              <div className="rounded-md border border-zinc-200 p-3 text-xs dark:border-zinc-700">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400" />
                    AI Qualification Summary
                  </span>
                  <span className="font-bold text-zinc-900 dark:text-zinc-100">
                    Score: {selectedLead.lead_score || "—"}/100
                  </span>
                </div>
                {selectedLead.opportunity ? (
                  <div className="space-y-1.5 text-zinc-600 dark:text-zinc-400">
                    <div><strong>Opportunity:</strong> {selectedLead.opportunity}</div>
                    <div><strong>Recommended Service:</strong> {selectedLead.recommended_service}</div>
                    <div><strong>Reasoning:</strong> {selectedLead.reasoning_summary}</div>
                    <div><strong>Next Action:</strong> {selectedLead.next_best_action}</div>
                  </div>
                ) : (
                  <div className="text-zinc-500 italic">
                    AI analysis has not been run yet. Click &ldquo;Qualify&rdquo; above to run Ollama analysis.
                  </div>
                )}
              </div>

              {/* Personalized Cold-Outreach DM Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                    Personalized Outreach Draft (30-60 words)
                  </label>
                  {selectedLead.personalized_dm && (
                    <button
                      onClick={() => handleCopyDM(editDraft || selectedLead.personalized_dm, selectedLead.id)}
                      className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
                    >
                      {copiedId === selectedLead.id ? (
                        <>
                          <Check className="h-3.5 w-3.5" /> Copied!
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5" /> Copy Message
                        </>
                      )}
                    </button>
                  )}
                </div>

                <textarea
                  rows="4"
                  value={editDraft}
                  onChange={(e) => setEditDraft(e.target.value)}
                  placeholder="AI-generated personalized draft will appear here..."
                  className="w-full rounded-md border border-zinc-300 p-2 text-xs leading-relaxed dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 focus:outline-hidden"
                />

                <div className="flex items-center justify-between pt-1">
                  <button
                    onClick={handleSaveDraft}
                    className="rounded border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    Save Edited Draft
                  </button>

                  {selectedLead.instagram_url && (
                    <a
                      href={selectedLead.instagram_url.startsWith("http") ? selectedLead.instagram_url : `https://${selectedLead.instagram_url}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded bg-pink-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-pink-700"
                    >
                      <InstagramIcon className="h-3 w-3" />
                      Open Profile
                    </a>
                  )}
                </div>
              </div>

              {/* Status Update Quick Buttons */}
              <div className="border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <div className="text-[11px] font-medium text-zinc-500 mb-2">
                  Update Outreach Status:
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "reviewed")}
                    className="rounded bg-zinc-100 px-2 py-1 text-[10px] font-medium text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    Mark Reviewed
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "contacted")}
                    className="rounded bg-blue-100 px-2 py-1 text-[10px] font-medium text-blue-800 hover:bg-blue-200 dark:bg-blue-950/60 dark:text-blue-300"
                  >
                    Mark Contacted
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "replied")}
                    className="rounded bg-purple-100 px-2 py-1 text-[10px] font-medium text-purple-800 hover:bg-purple-200 dark:bg-purple-950/60 dark:text-purple-300"
                  >
                    Mark Replied
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "converted")}
                    className="rounded bg-emerald-100 px-2 py-1 text-[10px] font-medium text-emerald-800 hover:bg-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300"
                  >
                    Mark Converted
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "do_not_contact")}
                    className="rounded bg-red-100 px-2 py-1 text-[10px] font-medium text-red-800 hover:bg-red-200 dark:bg-red-950/60 dark:text-red-300"
                  >
                    Opt-Out
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-zinc-500">
              Select a lead from the table to view verified evidence, inspect the AI qualification score, and review/edit the personalized DM draft.
            </div>
          )}
        </div>
      </div>

      {/* Add Lead Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800">
            <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-4">
              Add New Business Lead
            </h2>

            {formError && (
              <div className="mb-4 rounded bg-red-50 p-2.5 text-xs text-red-700 dark:bg-red-950/50 dark:text-red-400 border border-red-200 dark:border-red-800">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateLead} className="space-y-3 text-xs">
              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Business Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Malabar Roastery"
                  value={newLead.business_name}
                  onChange={(e) => setNewLead({ ...newLead, business_name: e.target.value })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Industry
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Specialty Coffee"
                    value={newLead.industry}
                    onChange={(e) => setNewLead({ ...newLead, industry: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    State
                  </label>
                  <select
                    value={newLead.state}
                    onChange={(e) => setNewLead({ ...newLead, state: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  >
                    {INDIAN_STATES.filter(s => s !== "All States").map((st) => (
                      <option key={st} value={st}>{st}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Website URL (if any)
                </label>
                <input
                  type="text"
                  placeholder="e.g. https://malabarroastery.in"
                  value={newLead.website_url}
                  onChange={(e) => setNewLead({ ...newLead, website_url: e.target.value })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Instagram URL or @handle
                </label>
                <input
                  type="text"
                  placeholder="e.g. https://instagram.com/malabarroastery"
                  value={newLead.instagram_url}
                  onChange={(e) => setNewLead({ ...newLead, instagram_url: e.target.value })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Source Reference
                </label>
                <input
                  type="text"
                  placeholder="e.g. Kerala Startup Directory / Manual Research"
                  value={newLead.source_url}
                  onChange={(e) => setNewLead({ ...newLead, source_url: e.target.value })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100 dark:border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="rounded border border-zinc-300 px-3 py-1.5 font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="rounded bg-zinc-900 px-3 py-1.5 font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                >
                  {formSubmitting ? "Saving & Checking..." : "Create Lead"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Discover Leads Modal */}
      {showDiscoverModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 overflow-y-auto">
          <div className="w-full max-w-4xl max-h-[90vh] flex flex-col rounded-xl bg-white shadow-2xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            {/* Modal Header */}
            <div className="p-5 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between bg-zinc-50/50 dark:bg-zinc-800/40">
              <div>
                <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                  <Compass className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                  Live Business & Lead Discovery
                </h2>
                <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                  Search public web listings and directories by niche & location. Automatically checks website availability, deduplicates against CRM, and scores service fit.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowDiscoverModal(false)}
                className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                ✕
              </button>
            </div>

            {/* Discovery Query Form */}
            <div className="p-5 border-b border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900">
              <form onSubmit={handleRunDiscovery} className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
                <div className="sm:col-span-1">
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Niche / Category *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Boutique Hotel, Dentist"
                    value={discoveryQuery.niche}
                    onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, niche: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>

                <div className="sm:col-span-1">
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    City / State
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Kochi, Kerala or Bangalore"
                    value={discoveryQuery.location}
                    onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, location: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>

                <div className="sm:col-span-1">
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Keywords (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. appointment, booking, store"
                    value={discoveryQuery.keywords}
                    onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, keywords: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>

                <div className="sm:col-span-1 flex items-end">
                  <button
                    type="submit"
                    disabled={discovering}
                    className="w-full inline-flex items-center justify-center gap-1.5 rounded bg-indigo-600 py-2 px-3 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  >
                    <Search className={`h-3.5 w-3.5 ${discovering ? "animate-spin" : ""}`} />
                    {discovering ? "Scanning Web..." : "Discover Leads"}
                  </button>
                </div>
              </form>

              {discoveryError && (
                <div className="mt-3 rounded bg-red-50 p-2.5 text-xs text-red-700 border border-red-200 dark:bg-red-950/40 dark:border-red-800 dark:text-red-400">
                  {discoveryError}
                </div>
              )}
            </div>

            {/* Results Area */}
            <div className="flex-1 overflow-y-auto p-5 space-y-3 min-h-[240px]">
              {discovering ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-zinc-500 space-y-3">
                  <RefreshCw className="h-8 w-8 animate-spin text-indigo-500" />
                  <div>
                    <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                      Querying Public Directories & Search Engines...
                    </p>
                    <p className="text-xs text-zinc-400 mt-1">
                      Filtering public listings, testing live reachability, and evaluating prospect fit criteria.
                    </p>
                  </div>
                </div>
              ) : discoveryResults.length > 0 ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs text-zinc-500 border-b border-zinc-100 pb-2 dark:border-zinc-800">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleSelectAllCandidates}
                        className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 font-medium text-xs flex items-center gap-1"
                      >
                        <CheckSquare className="h-3.5 w-3.5" />
                        Select / Unselect All Eligible
                      </button>
                      <span>•</span>
                      <span>{discoveryResults.length} prospects discovered ({discoveryStats?.execution_time_ms}ms)</span>
                    </div>
                    <span>{selectedCandidates.length} of {discoveryResults.filter(r => !r.is_duplicate).length} selected</span>
                  </div>

                  <div className="space-y-2">
                    {discoveryResults.map((item, idx) => {
                      const isSelected = selectedCandidates.includes(idx);
                      return (
                        <div
                          key={idx}
                          onClick={() => !item.is_duplicate && handleToggleCandidate(idx)}
                          className={`rounded-lg border p-3.5 transition-colors text-xs ${
                            item.is_duplicate
                              ? "border-zinc-200 bg-zinc-50/50 opacity-60 dark:border-zinc-800 dark:bg-zinc-800/20 cursor-not-allowed"
                              : isSelected
                              ? "border-indigo-300 bg-indigo-50/40 dark:border-indigo-800 dark:bg-indigo-950/20 cursor-pointer"
                              : "border-zinc-200 bg-white hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 cursor-pointer"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-2.5">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                disabled={item.is_duplicate}
                                onChange={() => handleToggleCandidate(idx)}
                                onClick={(e) => e.stopPropagation()}
                                className="mt-1 rounded text-indigo-600 focus:ring-indigo-500"
                              />
                              <div>
                                <div className="flex items-center gap-2">
                                  <h3 className="font-bold text-zinc-900 dark:text-zinc-100 text-sm">
                                    {item.business_name}
                                  </h3>
                                  {item.is_duplicate && (
                                    <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300">
                                      Already in CRM
                                    </span>
                                  )}
                                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                                    item.reachable
                                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800"
                                      : "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800"
                                  }`}>
                                    {item.reachable ? "Reachable" : `Unreachable (${item.status_code || "timeout"})`}
                                  </span>
                                </div>

                                <div className="flex flex-wrap items-center gap-3 text-zinc-500 mt-1 text-[11px]">
                                  {item.website_url && (
                                    <a
                                      href={item.website_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      className="text-blue-600 hover:underline dark:text-blue-400 inline-flex items-center gap-1"
                                    >
                                      <Globe className="h-3 w-3" />
                                      {item.domain}
                                      <ExternalLink className="h-2.5 w-2.5" />
                                    </a>
                                  )}
                                  {item.public_phone && <span>📞 {item.public_phone}</span>}
                                  {item.public_email && <span>✉️ {item.public_email}</span>}
                                </div>

                                <p className="text-zinc-600 dark:text-zinc-400 mt-1.5 line-clamp-2 text-[11px]">
                                  {item.snippet}
                                </p>

                                {item.score_reasons && item.score_reasons.length > 0 && (
                                  <div className="mt-2 flex flex-wrap gap-1">
                                    {item.score_reasons.map((reason, rIdx) => (
                                      <span key={rIdx} className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                                        ✓ {reason}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>

                            <div className="text-right shrink-0">
                              <div className="flex items-center justify-end gap-1">
                                <span className="text-base font-bold text-indigo-600 dark:text-indigo-400">
                                  {item.lead_score}
                                </span>
                                <span className="text-[10px] text-zinc-400">/100</span>
                              </div>
                              <span className="text-[10px] text-zinc-400 block">Fit Score</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : discoveryStats ? (
                <div className="p-12 text-center text-xs text-zinc-500">
                  No public businesses found matching this query. Try a broader niche or general city/state keywords.
                </div>
              ) : (
                <div className="p-12 text-center text-xs text-zinc-500">
                  Enter a niche (e.g. &ldquo;Boutique Hotel&rdquo; or &ldquo;Dentist&rdquo;) and a location above, then click &ldquo;Discover Leads&rdquo; to scan public business directories.
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-zinc-100 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-800/40 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                {selectedCandidates.length > 0
                  ? `${selectedCandidates.length} eligible prospect${selectedCandidates.length > 1 ? "s" : ""} selected for import.`
                  : "Select prospects above to import into CRM."}
              </span>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowDiscoverModal(false)}
                  className="rounded border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={handleImportCandidates}
                  disabled={selectedCandidates.length === 0 || importingDiscovered}
                  className="rounded bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                >
                  {importingDiscovered
                    ? "Importing & Qualifying..."
                    : `Import Selected (${selectedCandidates.length})`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function LeadsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs text-zinc-500">Loading leads...</div>}>
      <LeadsContent />
    </Suspense>
  );
}
