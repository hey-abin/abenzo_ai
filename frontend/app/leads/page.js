"use client";

import { Suspense, useEffect, useState } from "react";
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
  Square,
  UserCheck,
  Phone,
  Mail,
  Calendar,
  DollarSign,
  Clock,
  ShieldCheck,
  Send,
  Eye
} from "lucide-react";
import InstagramIcon from "@/components/InstagramIcon";
import { 
  fetchLeads, 
  createLead, 
  updateLead, 
  deleteLead, 
  checkWebsite, 
  qualifyLeadAI, 
  recalculateLeadQualification,
  fetchLeadMessagingStatus,
  sendLeadMessage,
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

const POPULAR_NICHES = [
  "Clothing Boutiques", "Cafes & Roasteries", "Restaurants", "Salons & Spas", 
  "Gyms & Fitness", "Clinics & Doctors", "Local Brands", "Architects & Studios", "Small Manufacturers"
];

const POPULAR_LOCATIONS = [
  "Kochi", "Trivandrum", "Kozhikode", "Thrissur", "Kannur", 
  "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Chennai"
];

export function getWebsiteStatusBadge(status) {
  switch (status) {
    case "has_website":
    case "found":
      return {
        label: "Website verified",
        className: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800"
      };
    case "broken_website":
      return {
        label: "Website unreachable",
        className: "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800"
      };
    case "no_website":
    case "not_found":
      return {
        label: "No website found",
        className: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800"
      };
    case "uncertain":
    default:
      return {
        label: "Website not assessed",
        className: "bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700"
      };
  }
}

const OUTREACH_STATUS_OPTIONS = [
  { value: "new", label: "Discovered (New)" },
  { value: "draft", label: "Draft Ready" },
  { value: "reviewed", label: "Reviewed" },
  { value: "followed", label: "Followed on IG" },
  { value: "contacted", label: "Contacted / DM Sent" },
  { value: "replied", label: "Replied" },
  { value: "interested", label: "Interested" },
  { value: "consultation_requested", label: "Consultation Requested" },
  { value: "proposal_sent", label: "Proposal Sent" },
  { value: "converted", label: "Won / Converted" },
  { value: "won", label: "Won" },
  { value: "not_interested", label: "Lost / Not Interested" },
  { value: "lost", label: "Lost" },
  { value: "do_not_contact", label: "Opt-Out" },
];

function LeadsContent() {
  const searchParams = useSearchParams();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("All States");
  const [statusFilter, setStatusFilter] = useState("");
  const [webFilter, setWebFilter] = useState("");
  const [queueTab, setQueueTab] = useState("all"); // 'all' | 'outreach' | 'discovered' | 'converted'
  
  // Modals & form state
  const [showAddModal, setShowAddModal] = useState(false);
  const [newLead, setNewLead] = useState({
    business_name: "",
    industry: "",
    state: "Kerala",
    city: "Kochi",
    website_url: "",
    instagram_url: "",
    source_url: "",
    contact_name: "",
    public_phone: "",
    public_email: ""
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
  const [editContactName, setEditContactName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editService, setEditService] = useState("");
  const [editTimeline, setEditTimeline] = useState("");
  const [editBudget, setEditBudget] = useState("");
  const [editConsent, setEditConsent] = useState("");
  const [editFollowUp, setEditFollowUp] = useState("");
  const [savingLead, setSavingLead] = useState(false);

  // Lead Discovery state
  const [showDiscoverModal, setShowDiscoverModal] = useState(false);
  const [discoveryQuery, setDiscoveryQuery] = useState({
    niche: "Clothing Boutiques",
    location: "Kochi",
    keywords: "",
    source_mode: "instagram_only",
    stage: "all",
    website_filter: "all",
    min_score: 0,
    limit: 10,
    exclude_crm: true,
    search_provider: "serper"
  });
  const [discovering, setDiscovering] = useState(false);
  const [discoveryResults, setDiscoveryResults] = useState([]);
  const [discoveryLimitation, setDiscoveryLimitation] = useState(null);
  const [discoveryError, setDiscoveryError] = useState("");
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [importingDiscovered, setImportingDiscovered] = useState(false);
  const [discoveryStats, setDiscoveryStats] = useState(null);
  const [discoveryDiagnostics, setDiscoveryDiagnostics] = useState(null);

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

  // Messaging action state
  const [messagingStatus, setMessagingStatus] = useState(null);
  const [loadingMessagingStatus, setLoadingMessagingStatus] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(null);
  const [sendError, setSendError] = useState("");
  const [recalculatingId, setRecalculatingId] = useState(null);

  // Sync selectedLead into edit state and load messaging eligibility
  useEffect(() => {
    if (selectedLead) {
      setEditDraft(selectedLead.personalized_dm || "");
      setEditContactName(selectedLead.contact_name || "");
      setEditPhone(selectedLead.public_phone || "");
      setEditEmail(selectedLead.public_email || "");
      setEditService(selectedLead.suggested_service || selectedLead.recommended_service || "");
      setEditTimeline(selectedLead.project_timeline || "");
      setEditBudget(selectedLead.budget || "");
      setEditConsent(selectedLead.consent_source || "");
      setEditFollowUp(selectedLead.follow_up_date || "");

      // Check Meta messaging eligibility
      setSendSuccess(null);
      setSendError("");
      setLoadingMessagingStatus(true);
      fetchLeadMessagingStatus(selectedLead.id)
        .then((st) => {
          setMessagingStatus(st);
          setLoadingMessagingStatus(false);
        })
        .catch(() => {
          setMessagingStatus(null);
          setLoadingMessagingStatus(false);
        });
    } else {
      setMessagingStatus(null);
      setSendSuccess(null);
      setSendError("");
    }
  }, [selectedLead?.id]);

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
        city: "Kochi",
        website_url: "",
        instagram_url: "",
        source_url: "",
        contact_name: "",
        public_phone: "",
        public_email: ""
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

  const handleRecalculateLead = async (leadId) => {
    setRecalculatingId(leadId);
    try {
      const updated = await recalculateLeadQualification(leadId);
      if (selectedLead?.id === leadId) setSelectedLead(updated);
      setLeads((prev) => prev.map((l) => (l.id === leadId ? updated : l)));
    } catch (err) {
      alert("Failed to recalculate qualification: " + err.message);
    } finally {
      setRecalculatingId(null);
    }
  };

  const handleSendLeadDM = async () => {
    if (!selectedLead || sendingMessage) return;
    const textToSend = editDraft.trim();
    if (!textToSend) {
      setSendError("Please provide message text to send.");
      return;
    }
    setSendingMessage(true);
    setSendError("");
    setSendSuccess(null);
    try {
      const res = await sendLeadMessage(selectedLead.id, textToSend);
      setSendSuccess(res);
      const updatedLead = { ...selectedLead, outreach_status: "contacted", outreach_action_at: res.sent_at || new Date().toISOString() };
      setSelectedLead(updatedLead);
      setLeads((prev) => prev.map((l) => (l.id === selectedLead.id ? updatedLead : l)));
    } catch (err) {
      setSendError(err.message || "Failed to send message via Meta API.");
    } finally {
      setSendingMessage(false);
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

  const handleSaveLeadDetails = async () => {
    if (!selectedLead) return;
    setSavingLead(true);
    try {
      const updated = await updateLead(selectedLead.id, {
        personalized_dm: editDraft,
        contact_name: editContactName,
        public_phone: editPhone,
        public_email: editEmail,
        suggested_service: editService,
        project_timeline: editTimeline,
        budget: editBudget,
        consent_source: editConsent,
        follow_up_date: editFollowUp
      });
      setLeads((prev) => prev.map((l) => (l.id === selectedLead.id ? updated : l)));
      setSelectedLead(updated);
      alert("Lead qualification details & outreach draft saved.");
    } catch (err) {
      alert("Failed to save lead: " + err.message);
    } finally {
      setSavingLead(false);
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
    if (e) e.preventDefault();
    if (!discoveryQuery.niche.trim() && !discoveryQuery.keywords.trim()) {
      setDiscoveryError("Please enter a business niche or keywords to discover prospects.");
      return;
    }
    setDiscovering(true);
    setDiscoveryError("");
    setDiscoveryLimitation(null);
    setDiscoveryResults([]);
    setSelectedCandidates([]);
    setDiscoveryStats(null);
    setDiscoveryDiagnostics(null);
    try {
      const res = await discoverLeads({
        niche: discoveryQuery.niche,
        city_or_state: discoveryQuery.location,
        keywords: discoveryQuery.keywords,
        source_mode: discoveryQuery.source_mode,
        stage: discoveryQuery.stage,
        website_filter: discoveryQuery.website_filter,
        min_score: parseInt(discoveryQuery.min_score, 10) || 0,
        exclude_crm: discoveryQuery.exclude_crm,
        limit: parseInt(discoveryQuery.limit, 10) || 10,
        search_provider: discoveryQuery.search_provider || "auto"
      });
      setDiscoveryResults(res.results || []);
      setDiscoveryLimitation(res.limitation_notice);
      setDiscoveryDiagnostics(res.diagnostics || null);
      setDiscoveryStats({
        total_found: res.total_found,
        source_mode: res.source_mode,
        provider: res.provider
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
      alert(`Successfully imported ${res.imported_count} prospects into CRM (${res.skipped_count} skipped/duplicates). Ready for outreach review.`);
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

  // Filter leads based on queue tab
  const displayedLeads = leads.filter((l) => {
    if (queueTab === "outreach") {
      return ["followed", "contacted", "replied", "interested"].includes(l.outreach_status);
    }
    if (queueTab === "discovered") {
      return ["new", "draft", "reviewed"].includes(l.outreach_status);
    }
    if (queueTab === "converted") {
      return ["converted", "consultation_requested", "proposal_sent"].includes(l.outreach_status);
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
            Prospect Acquisition & Outreach
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Instagram-first client discovery, digital presence gap analysis, and human-reviewed outreach queue.
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

          {/* Live Instagram & Business Discovery */}
          <button
            onClick={() => setShowDiscoverModal(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-pink-600 via-rose-600 to-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-95"
          >
            <InstagramIcon className="h-3.5 w-3.5" />
            Instagram Discovery
          </button>

          {/* Manual Lead Add */}
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Lead
          </button>
        </div>
      </div>

      {/* Queue View Tabs */}
      <div className="flex items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 pb-2">
        <button
          onClick={() => setQueueTab("all")}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
            queueTab === "all"
              ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
              : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
          }`}
        >
          All Leads ({leads.length})
        </button>
        <button
          onClick={() => setQueueTab("outreach")}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${
            queueTab === "outreach"
              ? "bg-indigo-600 text-white"
              : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
          }`}
        >
          <Send className="h-3 w-3" />
          Outreach Queue ({leads.filter(l => ["followed", "contacted", "replied", "interested"].includes(l.outreach_status)).length})
        </button>
        <button
          onClick={() => setQueueTab("discovered")}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
            queueTab === "discovered"
              ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
              : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
          }`}
        >
          Discovered / New ({leads.filter(l => ["new", "draft", "reviewed"].includes(l.outreach_status)).length})
        </button>
        <button
          onClick={() => setQueueTab("converted")}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
            queueTab === "converted"
              ? "bg-emerald-600 text-white"
              : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
          }`}
        >
          Won / In Discussion ({leads.filter(l => ["converted", "consultation_requested", "proposal_sent"].includes(l.outreach_status)).length})
        </button>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-white p-3 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        <form onSubmit={handleSearchSubmit} className="flex flex-1 items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-zinc-400" />
            <input
              type="text"
              placeholder="Search business name, category, or notes..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-zinc-200 bg-zinc-50 py-1.5 pl-8 pr-3 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 focus:outline-hidden"
            />
          </div>
          <button
            type="submit"
            className="rounded-md bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200"
          >
            Search
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* State Filter */}
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="rounded-md border border-zinc-200 bg-white py-1.5 px-2 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            {INDIAN_STATES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {/* Website Status */}
          <select
            value={webFilter}
            onChange={(e) => setWebFilter(e.target.value)}
            className="rounded-md border border-zinc-200 bg-white py-1.5 px-2 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <option value="">All Web States</option>
            <option value="no_website">No Website (High Opp)</option>
            <option value="broken_website">Broken Website</option>
            <option value="has_website">Has Website</option>
            <option value="uncertain">Uncertain</option>
          </select>

          {/* Outreach Status */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-zinc-200 bg-white py-1.5 px-2 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <option value="">All Outreach Statuses</option>
            {OUTREACH_STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Grid: Leads Table + Detail/Outreach Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Table Column (2 cols) */}
        <div className="lg:col-span-2 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-zinc-200 bg-zinc-50 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-800/50 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-semibold">Business / Profile</th>
                  <th className="px-3 py-3 font-semibold">Location</th>
                  <th className="px-3 py-3 font-semibold">Website & Opportunity</th>
                  <th className="px-3 py-3 font-semibold">Fit Score</th>
                  <th className="px-3 py-3 font-semibold">Outreach Stage</th>
                  <th className="px-4 py-3 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {loading ? (
                  <tr>
                    <td colSpan="6" className="py-12 text-center text-zinc-400">
                      Loading prospects...
                    </td>
                  </tr>
                ) : displayedLeads.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="py-12 text-center text-zinc-400">
                      No prospects found. Click &ldquo;Instagram Discovery&rdquo; to scan for local small businesses.
                    </td>
                  </tr>
                ) : (
                  displayedLeads.map((lead) => {
                    const isSelected = selectedLead?.id === lead.id;
                    const isAnalyzing = analyzingId === lead.id;
                    const isCheckingWeb = checkingWebId === lead.id;
                    const igHandle = lead.instagram_handle || (lead.instagram_url ? lead.instagram_url.split("/").filter(Boolean).pop() : "");

                    return (
                      <tr
                        key={lead.id}
                        onClick={() => setSelectedLead(lead)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-indigo-50/60 dark:bg-indigo-950/20"
                            : "hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
                        }`}
                      >
                        {/* Business Name & Instagram Handle */}
                        <td className="px-4 py-3">
                          <div className="font-semibold text-zinc-900 dark:text-zinc-100">
                            {lead.business_name}
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            {igHandle && (
                              <a
                                href={lead.instagram_url || `https://instagram.com/${igHandle}`}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-[11px] font-medium text-pink-600 hover:underline dark:text-pink-400"
                              >
                                <InstagramIcon className="h-3 w-3" />
                                @{igHandle}
                              </a>
                            )}
                            {lead.industry && (
                              <span className="text-[10px] text-zinc-400">
                                • {lead.industry}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Location */}
                        <td className="px-3 py-3 text-zinc-600 dark:text-zinc-400 text-[11px]">
                          <div>{lead.city || lead.state || "India"}</div>
                        </td>

                        {/* Web & Opportunity */}
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-1.5">
                            {(() => {
                              const b = getWebsiteStatusBadge(lead.website_status);
                              return (
                                <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border ${b.className}`}>
                                  {b.label}
                                </span>
                              );
                            })()}
                            {lead.website_url && (
                              <a
                                href={lead.website_url.startsWith("http") ? lead.website_url : `https://${lead.website_url}`}
                                target="_blank"
                                rel="noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-zinc-400 hover:text-blue-500"
                              >
                                <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            )}
                          </div>
                          <div className="mt-1 max-w-[170px] truncate text-[10px] text-zinc-500" title={lead.observed_problems || lead.opportunity || "Pending verification"}>
                            {lead.observed_problems || lead.opportunity || "Ready for review"}
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
                          {lead.suggested_service && (
                            <div className="max-w-[130px] truncate text-[10px] text-zinc-400" title={lead.suggested_service}>
                              {lead.suggested_service}
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
                              title="Qualify with AI"
                              className="inline-flex items-center gap-1 rounded bg-zinc-900 px-2 py-1 text-[11px] font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                            >
                              <Sparkles className={`h-3 w-3 ${isAnalyzing ? "animate-spin" : ""}`} />
                              <span>{isAnalyzing ? "..." : "AI"}</span>
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

        {/* Lead Detail & Safe Outreach Queue Drawer (1 col) */}
        <div className="rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
          {selectedLead ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
                <div>
                  <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">
                    {selectedLead.business_name}
                  </h2>
                  <p className="text-xs text-zinc-500">
                    ID #{selectedLead.id} • {selectedLead.city || selectedLead.state}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-indigo-600 dark:text-indigo-400">
                    {selectedLead.lead_score || "—"}/100
                  </div>
                  <span className="text-[10px] text-zinc-400">Fit Score</span>
                </div>
              </div>

              {/* Instagram & Digital Presence Bar */}
              <div className="flex flex-wrap items-center gap-2">
                {(selectedLead.instagram_url || selectedLead.instagram_handle) && (
                  <a
                    href={selectedLead.instagram_url || `https://instagram.com/${selectedLead.instagram_handle}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-pink-600 via-rose-600 to-amber-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-90"
                  >
                    <InstagramIcon className="h-3.5 w-3.5" />
                    Open Profile ({selectedLead.instagram_handle ? `@${selectedLead.instagram_handle}` : "Instagram"})
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                {selectedLead.website_url && (
                  <a
                    href={selectedLead.website_url.startsWith("http") ? selectedLead.website_url : `https://${selectedLead.website_url}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-md border border-zinc-200 px-2.5 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300"
                  >
                    <Globe className="h-3 w-3 text-blue-500" />
                    Visit Website
                  </a>
                )}
              </div>

              {/* Website Verification & Opportunity Detail */}
              <div className="rounded-md border border-zinc-200 bg-zinc-50/70 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-800/40 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-semibold text-zinc-900 dark:text-zinc-100">
                    <Globe className="h-3.5 w-3.5 text-blue-500" />
                    <span>Website Presence & Verification</span>
                  </div>
                  {(() => {
                    const b = getWebsiteStatusBadge(selectedLead.website_status);
                    return (
                      <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold border ${b.className}`}>
                        {b.label}
                      </span>
                    );
                  })()}
                </div>

                <div className="text-[11px] text-zinc-600 dark:text-zinc-300">
                  <span className="font-medium text-zinc-500 dark:text-zinc-400">URL: </span>
                  {selectedLead.website_url ? (
                    <a
                      href={selectedLead.website_url.startsWith("http") ? selectedLead.website_url : `https://${selectedLead.website_url}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 underline dark:text-blue-400 break-all"
                    >
                      {selectedLead.website_url}
                    </a>
                  ) : (
                    <span className="text-zinc-400 italic">No website URL detected in public records</span>
                  )}
                </div>

                <div className="text-[11px] text-zinc-700 dark:text-zinc-300">
                  <span className="font-semibold text-zinc-900 dark:text-zinc-100">Observed Opportunity: </span>
                  {selectedLead.observed_problems || selectedLead.opportunity || "Ready for verification."}
                </div>

                {/* Concrete Evidence Summary */}
                {(selectedLead.evidence_json?.website_check?.evidence_summary || selectedLead.evidence_json?.evidence_summary) && (
                  <div className="rounded bg-white p-2 text-[10px] border border-zinc-200 text-zinc-600 dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-400">
                    <span className="font-bold text-zinc-800 dark:text-zinc-200">Verified Evidence: </span>
                    {selectedLead.evidence_json?.website_check?.evidence_summary || selectedLead.evidence_json?.evidence_summary}
                  </div>
                )}

                {selectedLead.suggested_service && (
                  <div className="text-[11px] text-purple-700 dark:text-purple-300 font-medium">
                    Suggested Abenzo Service: <strong>{selectedLead.suggested_service}</strong>
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1 border-t border-zinc-200/60 dark:border-zinc-700/60">
                  <button
                    onClick={() => handleCheckWebsite(selectedLead)}
                    disabled={checkingWebId === selectedLead.id}
                    className="inline-flex items-center gap-1 rounded bg-white px-2 py-1 text-[10px] font-medium border border-zinc-300 hover:bg-zinc-50 text-zinc-700 dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-300 disabled:opacity-50"
                  >
                    <RefreshCw className={`h-2.5 w-2.5 ${checkingWebId === selectedLead.id ? "animate-spin" : ""}`} />
                    {checkingWebId === selectedLead.id ? "Verifying..." : "Verify / Recheck Website"}
                  </button>
                  <button
                    onClick={() => handleRecalculateLead(selectedLead.id)}
                    disabled={recalculatingId === selectedLead.id}
                    className="inline-flex items-center gap-1 rounded bg-white px-2 py-1 text-[10px] font-medium border border-zinc-300 hover:bg-zinc-50 text-purple-700 dark:bg-zinc-800 dark:border-zinc-700 dark:text-purple-400 disabled:opacity-50"
                  >
                    <Sparkles className="h-2.5 w-2.5" />
                    {recalculatingId === selectedLead.id ? "Recalculating..." : "Recalculate Fit"}
                  </button>
                </div>
              </div>

              {/* Score Breakdown if present */}
              {selectedLead.score_breakdown_json && Object.keys(selectedLead.score_breakdown_json).length > 0 && (
                <div className="rounded-md bg-zinc-50 p-2.5 text-[10px] dark:bg-zinc-800/40">
                  <span className="font-semibold text-zinc-600 dark:text-zinc-300 block mb-1">
                    Score Breakdown:
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(selectedLead.score_breakdown_json).map(([k, v]) => (
                      <span key={k} className="rounded bg-white px-1.5 py-0.5 border border-zinc-200 dark:bg-zinc-800 dark:border-zinc-700">
                        {k.replace(/_/g, " ")}: +{v}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Personalized Cold-Outreach DM Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
                    Personalized Outreach Draft (30-50 words)
                  </label>
                  {editDraft && (
                    <button
                      onClick={() => handleCopyDM(editDraft, selectedLead.id)}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
                    >
                      {copiedId === selectedLead.id ? (
                        <>
                          <Check className="h-3.5 w-3.5" /> Copied Draft
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
                  placeholder="Personalized outreach draft will appear here..."
                  className="w-full rounded-md border border-zinc-300 p-2 text-xs leading-relaxed dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 focus:outline-hidden"
                />
              </div>

              {/* Send Message / Outreach Action */}
              <div className="rounded-md border border-indigo-200 bg-indigo-50/40 p-3.5 dark:border-indigo-900/40 dark:bg-indigo-950/20 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                    <Send className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
                    Dashboard Outreach Action
                  </span>
                  {loadingMessagingStatus ? (
                    <span className="text-[10px] text-zinc-400 animate-pulse">Checking Meta policy...</span>
                  ) : messagingStatus?.can_send ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Eligible for Direct Send
                    </span>
                  ) : (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
                      Manual Outreach Required
                    </span>
                  )}
                </div>

                {/* Policy guidance or eligible notice */}
                {messagingStatus && !messagingStatus.can_send && (
                  <div className="rounded bg-white p-2.5 text-[11px] leading-relaxed border border-amber-200 text-amber-900 dark:bg-zinc-900 dark:border-amber-800/60 dark:text-amber-200">
                    <div className="font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-1 mb-0.5">
                      <Info className="h-3 w-3 text-amber-600" />
                      Meta Platform Policy
                    </div>
                    <p className="text-[10px]">
                      {messagingStatus.reason || "Under Meta's Platform Policy, businesses cannot initiate cold outbound direct messages via API to accounts that haven't messaged the business. Use Copy Message and Open Profile to conduct manual outreach on Instagram."}
                    </p>
                  </div>
                )}

                {sendSuccess && (
                  <div className="rounded bg-emerald-100 p-2 text-[11px] font-medium text-emerald-900 border border-emerald-300 dark:bg-emerald-950/80 dark:text-emerald-200 dark:border-emerald-800 flex items-center gap-1.5">
                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                    Message delivered via Meta API! (ID: {sendSuccess.meta_message_id})
                  </div>
                )}

                {sendError && (
                  <div className="rounded bg-red-100 p-2 text-[11px] text-red-900 border border-red-300 dark:bg-red-950/80 dark:text-red-200 dark:border-red-800">
                    {sendError}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {messagingStatus?.can_send ? (
                    <button
                      onClick={handleSendLeadDM}
                      disabled={sendingMessage || Boolean(sendSuccess)}
                      className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      <Send className="h-3.5 w-3.5" />
                      {sendingMessage ? "Sending to Instagram..." : sendSuccess ? "Delivered" : "Send Message"}
                    </button>
                  ) : null}

                  <button
                    onClick={() => handleCopyDM(editDraft, selectedLead.id)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                  >
                    {copiedId === selectedLead.id ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" /> Copied Draft
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5" /> Copy Message
                      </>
                    )}
                  </button>

                  {(selectedLead.instagram_url || selectedLead.instagram_handle) && (
                    <a
                      href={selectedLead.instagram_url || `https://instagram.com/${selectedLead.instagram_handle}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-pink-600 via-rose-600 to-amber-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:opacity-90"
                    >
                      <InstagramIcon className="h-3.5 w-3.5" />
                      Open Profile ({selectedLead.instagram_handle ? `@${selectedLead.instagram_handle}` : "Instagram"})
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
                <p className="text-[10px] text-zinc-400">
                  * Copied drafts are never presented as delivered messages. Delivery status is updated only when the API confirms delivery.
                </p>
              </div>

              {/* Human-Reviewed Outreach Queue Action Buttons */}
              <div className="border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-semibold text-zinc-700 dark:text-zinc-300">
                    Lead Lifecycle Status:
                  </span>
                  {selectedLead.outreach_action_at && (
                    <span className="text-[10px] text-zinc-400">
                      Last action: {new Date(selectedLead.outreach_action_at).toLocaleString()}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "followed")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "followed"
                        ? "bg-pink-600 text-white"
                        : "bg-pink-50 text-pink-700 border border-pink-200 hover:bg-pink-100 dark:bg-pink-950/40 dark:text-pink-300 dark:border-pink-800"
                    }`}
                  >
                    Followed
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "contacted")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "contacted"
                        ? "bg-blue-600 text-white"
                        : "bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800"
                    }`}
                  >
                    Contacted
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "replied")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "replied"
                        ? "bg-purple-600 text-white"
                        : "bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100 dark:bg-purple-950/40 dark:text-purple-300 dark:border-purple-800"
                    }`}
                  >
                    Replied
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "interested")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "interested"
                        ? "bg-indigo-600 text-white"
                        : "bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-300 dark:border-indigo-800"
                    }`}
                  >
                    Interested
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "consultation_requested")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "consultation_requested"
                        ? "bg-teal-600 text-white"
                        : "bg-teal-50 text-teal-700 border border-teal-200 hover:bg-teal-100 dark:bg-teal-950/40 dark:text-teal-300 dark:border-teal-800"
                    }`}
                  >
                    Consultation Requested
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "proposal_sent")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "proposal_sent"
                        ? "bg-sky-600 text-white"
                        : "bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-800"
                    }`}
                  >
                    Proposal Sent
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "won")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "won" || selectedLead.outreach_status === "converted"
                        ? "bg-emerald-600 text-white"
                        : "bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
                    }`}
                  >
                    Won
                  </button>
                  <button
                    onClick={() => handleStatusChange(selectedLead.id, "lost")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      selectedLead.outreach_status === "lost" || selectedLead.outreach_status === "not_interested"
                        ? "bg-zinc-700 text-white"
                        : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
                    }`}
                  >
                    Lost
                  </button>
                </div>
              </div>

              {/* Lead Qualification & Voluntary Contact Fields */}
              <div className="border-t border-zinc-100 pt-3 dark:border-zinc-800 space-y-2.5">
                <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                  <UserCheck className="h-3.5 w-3.5 text-blue-500" />
                  Lead Qualification & Contact Details
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Contact Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Rahul"
                      value={editContactName}
                      onChange={(e) => setEditContactName(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Phone / WhatsApp</label>
                    <input
                      type="text"
                      placeholder="e.g. +91 9876543210"
                      value={editPhone}
                      onChange={(e) => setEditPhone(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Email</label>
                    <input
                      type="email"
                      placeholder="e.g. contact@brand.in"
                      value={editEmail}
                      onChange={(e) => setEditEmail(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Interested Service</label>
                    <input
                      type="text"
                      placeholder="e.g. WhatsApp Catalog"
                      value={editService}
                      onChange={(e) => setEditService(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Timeline</label>
                    <input
                      type="text"
                      placeholder="e.g. 2-3 weeks"
                      value={editTimeline}
                      onChange={(e) => setEditTimeline(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Budget (if volunteered)</label>
                    <input
                      type="text"
                      placeholder="e.g. ₹35,000 - ₹50,000"
                      value={editBudget}
                      onChange={(e) => setEditBudget(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Follow-up Date</label>
                    <input
                      type="date"
                      value={editFollowUp}
                      onChange={(e) => setEditFollowUp(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 block mb-0.5">Consent / Source</label>
                    <input
                      type="text"
                      placeholder="e.g. Public Bio / Voluntary DM"
                      value={editConsent}
                      onChange={(e) => setEditConsent(e.target.value)}
                      className="w-full rounded border border-zinc-200 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                    />
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleSaveLeadDetails}
                    disabled={savingLead}
                    className="w-full rounded bg-zinc-900 py-1.5 text-xs font-semibold text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                  >
                    {savingLead ? "Saving Details..." : "Save Qualification & Draft"}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-zinc-500">
              Select a lead from the table to view verified Instagram evidence, inspect digital gaps, and copy the personalized outreach draft.
            </div>
          )}
        </div>
      </div>

      {/* Discover Leads Modal */}
      {showDiscoverModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 overflow-y-auto">
          <div className="w-full max-w-4xl max-h-[92vh] flex flex-col rounded-xl bg-white shadow-2xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between bg-zinc-50/70 dark:bg-zinc-800/40">
              <div className="flex items-center gap-2.5">
                <div className="rounded-lg bg-gradient-to-tr from-pink-500 via-rose-500 to-amber-500 p-2 text-white">
                  <InstagramIcon className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">
                    Instagram-First Customer Acquisition
                  </h2>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Discover verified local small businesses & founders needing websites, e-commerce, or web apps.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowDiscoverModal(false)}
                className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                ✕
              </button>
            </div>

            {/* Discovery Query Form & Quick Filters */}
            <div className="p-4 border-b border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900 space-y-3">
              <form onSubmit={handleRunDiscovery} className="space-y-3 text-xs">
                {/* Search Source Mode Toggle */}
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-semibold text-zinc-700 dark:text-zinc-300">Discovery Mode:</span>
                  <button
                    type="button"
                    onClick={() => setDiscoveryQuery({ ...discoveryQuery, source_mode: "instagram_only" })}
                    className={`rounded-full px-3 py-1 font-medium transition-colors ${
                      discoveryQuery.source_mode === "instagram_only"
                        ? "bg-pink-600 text-white"
                        : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300"
                    }`}
                  >
                    Instagram Profiles Only (Recommended)
                  </button>
                  <button
                    type="button"
                    onClick={() => setDiscoveryQuery({ ...discoveryQuery, source_mode: "all_sources" })}
                    className={`rounded-full px-3 py-1 font-medium transition-colors ${
                      discoveryQuery.source_mode === "all_sources"
                        ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                        : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300"
                    }`}
                  >
                    All Public Business Sources
                  </button>
                </div>

                {/* Primary Query Inputs */}
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-2.5">
                  <div className="sm:col-span-1">
                    <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                      Business Niche *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Clothing Boutiques"
                      value={discoveryQuery.niche}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, niche: e.target.value })}
                      className="w-full rounded border border-zinc-300 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                    />
                  </div>

                  <div className="sm:col-span-1">
                    <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                      City / Region *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Kochi, Kerala"
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
                      placeholder="e.g. order, catalog, DM"
                      value={discoveryQuery.keywords}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, keywords: e.target.value })}
                      className="w-full rounded border border-zinc-300 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                    />
                  </div>

                  <div className="sm:col-span-1 flex items-end">
                    <button
                      type="submit"
                      disabled={discovering}
                      className="w-full inline-flex items-center justify-center gap-1.5 rounded bg-gradient-to-r from-pink-600 via-rose-600 to-indigo-600 py-2 px-3 text-xs font-semibold text-white hover:opacity-95 disabled:opacity-50 transition-opacity"
                    >
                      <Search className={`h-3.5 w-3.5 ${discovering ? "animate-spin" : ""}`} />
                      {discovering ? "Scanning Profiles..." : "Discover Prospects"}
                    </button>
                  </div>
                </div>

                {/* Quick Niche Chips */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[11px] text-zinc-400">Niches:</span>
                  {POPULAR_NICHES.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setDiscoveryQuery({ ...discoveryQuery, niche: n })}
                      className={`rounded px-2 py-0.5 text-[10px] transition-colors ${
                        discoveryQuery.niche === n
                          ? "bg-pink-100 text-pink-800 font-semibold dark:bg-pink-950/60 dark:text-pink-300"
                          : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>

                {/* Quick Location Chips */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-zinc-400">Locations:</span>
                  {POPULAR_LOCATIONS.map((loc) => (
                    <button
                      key={loc}
                      type="button"
                      onClick={() => setDiscoveryQuery({ ...discoveryQuery, location: loc })}
                      className={`rounded px-2 py-0.5 text-[10px] transition-colors ${
                        discoveryQuery.location === loc
                          ? "bg-indigo-100 text-indigo-800 font-semibold dark:bg-indigo-950/60 dark:text-indigo-300"
                          : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
                      }`}
                    >
                      {loc}
                    </button>
                  ))}
                </div>

                {/* Additional Filters: Stage, Website Status, Min Score, Exclude CRM */}
                <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-zinc-100 dark:border-zinc-800 text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <span className="text-zinc-500">Stage:</span>
                    <select
                      value={discoveryQuery.stage}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, stage: e.target.value })}
                      className="rounded border border-zinc-200 bg-white p-1 text-[11px] dark:border-zinc-700 dark:bg-zinc-800"
                    >
                      <option value="all">All Stages</option>
                      <option value="small_business">Small Business</option>
                      <option value="startup">Early-Stage Startup</option>
                      <option value="local_brand">Local Brand</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-zinc-500">Website:</span>
                    <select
                      value={discoveryQuery.website_filter}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, website_filter: e.target.value })}
                      className="rounded border border-zinc-200 bg-white p-1 text-[11px] dark:border-zinc-700 dark:bg-zinc-800"
                    >
                      <option value="all">All Web Statuses</option>
                      <option value="no_website">No Website (High Opportunity)</option>
                      <option value="needs_improvement">Broken / Needs Improvement</option>
                      <option value="has_website">Has Website</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-zinc-500">Provider:</span>
                    <select
                      value={discoveryQuery.search_provider || "auto"}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, search_provider: e.target.value })}
                      className="rounded border border-zinc-200 bg-white p-1 text-[11px] dark:border-zinc-700 dark:bg-zinc-800"
                    >
                      <option value="serper">Google (Serper API)</option>
                      <option value="auto">Auto (DDG + Serper Fallback)</option>
                      <option value="duckduckgo">DuckDuckGo (Free)</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-zinc-500">Min Fit:</span>
                    <select
                      value={discoveryQuery.min_score}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, min_score: e.target.value })}
                      className="rounded border border-zinc-200 bg-white p-1 text-[11px] dark:border-zinc-700 dark:bg-zinc-800"
                    >
                      <option value="0">Any Score</option>
                      <option value="60">60+ (Qualified)</option>
                      <option value="75">75+ (High Priority)</option>
                      <option value="85">85+ (Prime Opportunity)</option>
                    </select>
                  </div>

                  <label className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={discoveryQuery.exclude_crm}
                      onChange={(e) => setDiscoveryQuery({ ...discoveryQuery, exclude_crm: e.target.checked })}
                      className="rounded text-indigo-600 focus:ring-indigo-500"
                    />
                    Exclude Existing CRM Leads
                  </label>
                </div>
              </form>

              {discoveryError && (
                <div className="rounded bg-red-50 p-2.5 text-xs text-red-700 border border-red-200 dark:bg-red-950/40 dark:border-red-800 dark:text-red-400">
                  {discoveryError}
                </div>
              )}
            </div>

            {/* Results Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[260px]">
              {discovering ? (
                <div className="flex flex-col items-center justify-center py-12 text-center text-zinc-500 space-y-3">
                  <RefreshCw className="h-8 w-8 animate-spin text-pink-600" />
                  <div>
                    <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                      Querying Public Instagram Profiles & Business Listings...
                    </p>
                    <p className="text-xs text-zinc-400 mt-1">
                      Filtering out listicles, verifying individual profiles, evaluating digital gaps, and calculating opportunity scores.
                    </p>
                  </div>
                </div>
              ) : discoveryResults.length > 0 ? (
                <div className="space-y-3">
                  {discoveryDiagnostics && (
                    <div className="rounded-md bg-zinc-100/80 p-2.5 text-[11px] text-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-300 space-y-1.5 border border-zinc-200/60 dark:border-zinc-700/60">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-zinc-800 dark:text-zinc-200">
                            Provider: {discoveryDiagnostics.selected_provider || discoveryDiagnostics.provider_used || "DuckDuckGo"}
                          </span>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            discoveryDiagnostics.key_configured
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                              : "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300"
                          }`}>
                            {discoveryDiagnostics.key_configured ? "Key Configured" : "Key Not Configured"}
                          </span>
                          {discoveryDiagnostics.provider_request_status && (
                            <span className="rounded bg-zinc-200/80 px-1.5 py-0.5 text-[10px] text-zinc-700 dark:bg-zinc-700/70 dark:text-zinc-300 font-mono">
                              {discoveryDiagnostics.provider_request_status}
                            </span>
                          )}
                          {discoveryDiagnostics.fallback_used && (
                            <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                              Fallback Used
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-zinc-500 dark:text-zinc-400">
                          <span>{discoveryDiagnostics.raw_results_count} raw fetched</span>
                          <span>•</span>
                          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{discoveryResults.length} verified profiles</span>
                          {discoveryDiagnostics.rejected_counts?.non_profile_path > 0 && (
                            <>
                              <span>•</span>
                              <span>{discoveryDiagnostics.rejected_counts.non_profile_path} posts/reels rejected</span>
                            </>
                          )}
                          {discoveryDiagnostics.duplicates_removed > 0 && (
                            <>
                              <span>•</span>
                              <span>{discoveryDiagnostics.duplicates_removed} duplicates removed</span>
                            </>
                          )}
                        </div>
                      </div>

                      {discoveryDiagnostics.fallback_attempts?.length > 0 && (
                        <div className="text-[10px] text-zinc-500 dark:text-zinc-400 pt-1 border-t border-zinc-200/60 dark:border-zinc-700/50">
                          <span className="font-semibold text-zinc-700 dark:text-zinc-300">Provider Attempts: </span>
                          {discoveryDiagnostics.fallback_attempts.join(" • ")}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between text-xs text-zinc-500 border-b border-zinc-100 pb-2 dark:border-zinc-800">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleSelectAllCandidates}
                        className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 font-semibold text-xs flex items-center gap-1"
                      >
                        <CheckSquare className="h-3.5 w-3.5" />
                        Select / Deselect All ({discoveryResults.filter(r => !r.is_duplicate).length} eligible)
                      </button>
                      <span>•</span>
                      <span>{discoveryResults.length} prospects returned</span>
                    </div>
                    <span>{selectedCandidates.length} selected for import</span>
                  </div>

                  <div className="space-y-3">
                    {discoveryResults.map((item, idx) => {
                      const isSelected = selectedCandidates.includes(idx);
                      const igUser = item.instagram_username || item.instagram_handle;

                      return (
                        <div
                          key={idx}
                          onClick={() => !item.is_duplicate && handleToggleCandidate(idx)}
                          className={`rounded-lg border p-3.5 transition-colors text-xs ${
                            item.is_duplicate
                              ? "border-zinc-200 bg-zinc-50/50 opacity-60 dark:border-zinc-800 dark:bg-zinc-800/20 cursor-not-allowed"
                              : isSelected
                              ? "border-indigo-300 bg-indigo-50/40 dark:border-indigo-800 dark:bg-indigo-950/20 cursor-pointer shadow-xs"
                              : "border-zinc-200 bg-white hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 cursor-pointer"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                disabled={item.is_duplicate}
                                onChange={() => handleToggleCandidate(idx)}
                                onClick={(e) => e.stopPropagation()}
                                className="mt-1 rounded text-indigo-600 focus:ring-indigo-500"
                              />
                              <div className="space-y-1.5">
                                {/* Header: Business Name & Instagram Badge */}
                                <div className="flex flex-wrap items-center gap-2">
                                  <h3 className="font-bold text-zinc-900 dark:text-zinc-100 text-sm">
                                    {item.business_name}
                                  </h3>
                                  {igUser && (
                                    <span className="inline-flex items-center gap-1 rounded bg-pink-100 px-2 py-0.5 text-[10px] font-semibold text-pink-700 dark:bg-pink-950/60 dark:text-pink-300">
                                      <InstagramIcon className="h-3 w-3" />
                                      @{igUser}
                                    </span>
                                  )}
                                  {item.is_duplicate && (
                                    <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300">
                                      Already in CRM
                                    </span>
                                  )}
                                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                                    item.website_status === "no_website"
                                      ? "bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-800"
                                      : item.website_status === "broken_website"
                                      ? "bg-red-50 text-red-700 border border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800"
                                      : "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800"
                                  }`}>
                                    {item.website_status === "no_website" ? "No Standalone Website" : item.website_status}
                                  </span>
                                </div>

                                {/* External Links & Contact Verification */}
                                <div className="flex flex-wrap items-center gap-3 text-zinc-500 text-[11px]">
                                  {igUser && (
                                    <a
                                      href={item.instagram_url || `https://instagram.com/${igUser}`}
                                      target="_blank"
                                      rel="noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      className="text-pink-600 hover:underline dark:text-pink-400 inline-flex items-center gap-1 font-medium"
                                    >
                                      <InstagramIcon className="h-3 w-3" />
                                      Open Profile <ExternalLink className="h-2.5 w-2.5" />
                                    </a>
                                  )}
                                  {item.website_url && (
                                    <a
                                      href={item.website_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      className="text-blue-600 hover:underline dark:text-blue-400 inline-flex items-center gap-1"
                                    >
                                      <Globe className="h-3 w-3" />
                                      {item.domain || "Website"} <ExternalLink className="h-2.5 w-2.5" />
                                    </a>
                                  )}
                                  {item.public_phone && <span>📞 {item.public_phone}</span>}
                                  {item.public_email && <span>✉️ {item.public_email}</span>}
                                </div>

                                {/* Observed Opportunity / Problem */}
                                {item.observed_problems && (
                                  <div className="rounded bg-amber-50/70 p-2 text-[11px] text-amber-900 border border-amber-200/50 dark:bg-amber-950/20 dark:text-amber-200 dark:border-amber-800/30">
                                    <strong>Opportunity:</strong> {item.observed_problems}
                                    {item.suggested_service && (
                                      <div className="text-indigo-700 dark:text-indigo-300 mt-0.5">
                                        Suggested Service: <strong>{item.suggested_service}</strong>
                                      </div>
                                    )}
                                  </div>
                                )}

                                {/* Score Reasons Breakdown */}
                                {item.score_reasons && item.score_reasons.length > 0 && (
                                  <div className="flex flex-wrap gap-1 pt-0.5">
                                    {item.score_reasons.map((reason, rIdx) => (
                                      <span key={rIdx} className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                                        ✓ {reason}
                                      </span>
                                    ))}
                                  </div>
                                )}

                                {/* Personalized Outreach Draft Preview */}
                                {item.personalized_dm && (
                                  <div className="mt-1 rounded border border-zinc-100 bg-zinc-50/70 p-2 text-[11px] text-zinc-600 dark:border-zinc-800 dark:bg-zinc-800/30 dark:text-zinc-300">
                                    <div className="flex items-center justify-between font-semibold text-zinc-700 dark:text-zinc-200 mb-1">
                                      <span>Outreach Draft Preview:</span>
                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleCopyDM(item.personalized_dm, `cand_${idx}`);
                                        }}
                                        className="text-indigo-600 hover:text-indigo-700 text-[10px] inline-flex items-center gap-1"
                                      >
                                        {copiedId === `cand_${idx}` ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                        {copiedId === `cand_${idx}` ? "Copied" : "Copy"}
                                      </button>
                                    </div>
                                    <p className="italic leading-relaxed">{item.personalized_dm}</p>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Fit Score Display */}
                            <div className="text-right shrink-0">
                              <div className="flex items-center justify-end gap-1">
                                <span className={`text-base font-bold ${
                                  item.lead_score >= 80 ? "text-emerald-600 dark:text-emerald-400" :
                                  item.lead_score >= 60 ? "text-indigo-600 dark:text-indigo-400" : "text-amber-600"
                                }`}>
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
              ) : discoveryDiagnostics && (discoveryDiagnostics.provider_status === "rate_limited_202" || discoveryDiagnostics.provider_status === "rate_limited_429" || discoveryDiagnostics.provider_status === "unauthorized_401") ? (
                /* Condition A: Provider Rate-Limited / Bot Challenged (HTTP 202) / Unauthorized */
                <div className="p-6 text-left text-xs bg-amber-50/60 rounded-lg border border-amber-300/80 dark:bg-amber-950/30 dark:border-amber-700/60 space-y-3">
                  <div className="flex items-start gap-2.5">
                    <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <h4 className="font-bold text-amber-950 dark:text-amber-200 text-sm">
                        {discoveryDiagnostics.provider_used || discoveryDiagnostics.selected_provider || "Search Provider"} — {discoveryDiagnostics.provider_request_status || "Rate Limited"}
                      </h4>
                      <p className="mt-1 text-amber-900/90 dark:text-amber-300/90 leading-relaxed">
                        {discoveryLimitation || "Search provider challenge or rate-limit prevented retrieving live profile listings."}
                      </p>
                    </div>
                  </div>

                  {/* Safe Diagnostics Stats Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-center">
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-amber-200 dark:border-zinc-700">
                      <div className="text-xs font-bold text-zinc-900 dark:text-zinc-100 truncate">
                        {discoveryDiagnostics.selected_provider || discoveryDiagnostics.provider_used || "DuckDuckGo"}
                      </div>
                      <div className="text-[10px] text-zinc-500">Provider</div>
                    </div>
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-amber-200 dark:border-zinc-700">
                      <div className={`text-xs font-bold ${discoveryDiagnostics.key_configured ? "text-emerald-600" : "text-amber-600"}`}>
                        {discoveryDiagnostics.key_configured ? "Configured (Yes)" : "Not Set (No)"}
                      </div>
                      <div className="text-[10px] text-zinc-500">API Key</div>
                    </div>
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-amber-200 dark:border-zinc-700">
                      <div className="text-xs font-bold text-amber-700 dark:text-amber-400 font-mono">
                        {discoveryDiagnostics.provider_request_status || "HTTP 202"}
                      </div>
                      <div className="text-[10px] text-zinc-500">Status</div>
                    </div>
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-amber-200 dark:border-zinc-700">
                      <div className="text-xs font-bold text-zinc-900 dark:text-zinc-100">
                        {discoveryDiagnostics.raw_results_count || 0}
                      </div>
                      <div className="text-[10px] text-zinc-500">Raw Results</div>
                    </div>
                  </div>

                  {discoveryDiagnostics.fallback_attempts?.length > 0 && (
                    <div className="rounded bg-amber-100/60 p-2.5 text-[11px] text-amber-950 dark:bg-amber-900/30 dark:text-amber-200 space-y-1">
                      <p className="font-semibold">Provider Fallback Attempts:</p>
                      <ul className="list-disc list-inside space-y-0.5 font-mono text-[10px]">
                        {discoveryDiagnostics.fallback_attempts.map((att, i) => (
                          <li key={i}>{att}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="rounded-md bg-amber-100/70 p-3 text-[11px] text-amber-950 dark:bg-amber-900/40 dark:text-amber-200 border border-amber-300/60">
                    <p className="font-semibold mb-1">💡 Solution for Fast, Reliable Discovery on Cloud Servers:</p>
                    <p className="leading-relaxed">
                      Datacenter hosting platforms (like Render) are frequently bot-challenged by DuckDuckGo. Switch Provider to <strong>Google (Serper API)</strong> or ensure <code>SERPER_API_KEY</code> is set in Render environment variables.
                    </p>
                  </div>
                </div>
              ) : discoveryDiagnostics && discoveryDiagnostics.raw_results_count > 0 && discoveryDiagnostics.valid_profiles_count === 0 ? (
                /* Condition B: Raw Results Received but Rejected by Validation */
                <div className="p-6 text-left text-xs bg-indigo-50/50 rounded-lg border border-indigo-200/80 dark:bg-indigo-950/20 dark:border-indigo-800/60 space-y-3">
                  <div className="flex items-start gap-2.5">
                    <Filter className="h-5 w-5 text-indigo-600 shrink-0 mt-0.5" />
                    <div>
                      <h4 className="font-bold text-indigo-950 dark:text-indigo-200 text-sm">
                        Results Received but Rejected by Profile Validation
                      </h4>
                      <p className="mt-1 text-indigo-900/90 dark:text-indigo-300/90 leading-relaxed">
                        The search provider ({discoveryDiagnostics.selected_provider || discoveryDiagnostics.provider_used}) returned {discoveryDiagnostics.raw_results_count} results, but none passed strict validation for genuine, individual business Instagram profiles.
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-center">
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                      <div className="text-base font-bold text-zinc-900 dark:text-zinc-100">{discoveryDiagnostics.raw_results_count}</div>
                      <div className="text-[10px] text-zinc-500">Raw Results</div>
                    </div>
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                      <div className="text-base font-bold text-rose-600 dark:text-rose-400">{discoveryDiagnostics.rejected_counts?.non_profile_path || 0}</div>
                      <div className="text-[10px] text-zinc-500">Posts / Reels / Popular</div>
                    </div>
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                      <div className="text-base font-bold text-amber-600 dark:text-amber-400">{discoveryDiagnostics.rejected_counts?.aggregator_or_listicle || 0}</div>
                      <div className="text-[10px] text-zinc-500">Directories / Listicles</div>
                    </div>
                    <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                      <div className="text-base font-bold text-indigo-600 dark:text-indigo-400">{discoveryDiagnostics.duplicates_removed || 0}</div>
                      <div className="text-[10px] text-zinc-500">Duplicates / In CRM</div>
                    </div>
                  </div>

                  {discoveryDiagnostics.fallback_attempts?.length > 0 && (
                    <div className="text-[10px] text-zinc-500 dark:text-zinc-400 pt-1">
                      <span className="font-semibold text-zinc-700 dark:text-zinc-300">Provider Attempts: </span>
                      {discoveryDiagnostics.fallback_attempts.join(" • ")}
                    </div>
                  )}

                  <p className="text-[11px] text-zinc-500 dark:text-zinc-400 pt-1">
                    Tip: Try searching for a specific niche category (e.g. &ldquo;Clothing Boutiques&rdquo; or &ldquo;Cafes & Roasteries&rdquo;) or switch from &ldquo;Instagram Profiles Only&rdquo; to &ldquo;All Public Business Sources&rdquo;.
                  </p>
                </div>
              ) : discoveryLimitation ? (
                /* Condition C: Provider Returned Zero Results */
                <div className="p-6 text-center text-xs text-zinc-600 dark:text-zinc-400 bg-zinc-50/70 rounded-lg border border-zinc-200 dark:bg-zinc-800/40 dark:border-zinc-700/60 space-y-3">
                  <Info className="h-6 w-6 text-zinc-400 mx-auto" />
                  <p className="font-semibold text-zinc-800 dark:text-zinc-200">{discoveryLimitation}</p>

                  {/* Safe Diagnostics Info Card */}
                  {discoveryDiagnostics && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center max-w-lg mx-auto py-1">
                      <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                        <div className="text-xs font-bold text-zinc-900 dark:text-zinc-100 truncate">
                          {discoveryDiagnostics.selected_provider || discoveryDiagnostics.provider_used || "DuckDuckGo"}
                        </div>
                        <div className="text-[10px] text-zinc-500">Provider</div>
                      </div>
                      <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                        <div className={`text-xs font-bold ${discoveryDiagnostics.key_configured ? "text-emerald-600" : "text-zinc-500"}`}>
                          {discoveryDiagnostics.key_configured ? "Configured (Yes)" : "Not Set (No)"}
                        </div>
                        <div className="text-[10px] text-zinc-500">API Key</div>
                      </div>
                      <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                        <div className="text-xs font-bold text-zinc-700 dark:text-zinc-300 font-mono">
                          {discoveryDiagnostics.provider_request_status || "HTTP 200 OK"}
                        </div>
                        <div className="text-[10px] text-zinc-500">Status</div>
                      </div>
                      <div className="p-2 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">
                        <div className="text-xs font-bold text-zinc-900 dark:text-zinc-100">
                          {discoveryDiagnostics.raw_results_count || 0}
                        </div>
                        <div className="text-[10px] text-zinc-500">Raw Results</div>
                      </div>
                    </div>
                  )}

                  {discoveryDiagnostics?.fallback_attempts?.length > 0 && (
                    <div className="text-[10px] text-zinc-500 dark:text-zinc-400">
                      <strong>Provider Attempts:</strong> {discoveryDiagnostics.fallback_attempts.join(" • ")}
                    </div>
                  )}

                  {discoveryDiagnostics?.queries_executed?.length > 0 && (
                    <p className="text-[11px] text-zinc-400">
                      Queries executed: {discoveryDiagnostics.queries_executed.join(" • ")}
                    </p>
                  )}
                  <p className="text-[11px] text-zinc-500">
                    Tip: Try selecting one of the popular quick niches (e.g. &ldquo;Clothing Boutiques&rdquo; or &ldquo;Cafes & Roasteries&rdquo;) or switch to &ldquo;All Public Business Sources&rdquo;.
                  </p>
                </div>
              ) : (
                <div className="p-12 text-center text-xs text-zinc-500">
                  Select a business niche and location above, then click &ldquo;Discover Prospects&rdquo; to query live public Instagram profiles.
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-zinc-100 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-800/40 flex items-center justify-between">
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
                  className="rounded bg-gradient-to-r from-pink-600 to-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:opacity-95 disabled:opacity-50 transition-opacity"
                >
                  {importingDiscovered
                    ? "Importing Prospects..."
                    : `Import Selected (${selectedCandidates.length})`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Manual Add Lead Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800">
            <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100 mb-3">
              Add New Business Prospect
            </h2>

            {formError && (
              <div className="mb-3 rounded bg-red-50 p-2 text-xs text-red-600 dark:bg-red-950/50 dark:text-red-400">
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
                    Industry / Niche
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Cafe & Coffee"
                    value={newLead.industry}
                    onChange={(e) => setNewLead({ ...newLead, industry: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>

                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    City / State
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Kochi"
                    value={newLead.city}
                    onChange={(e) => setNewLead({ ...newLead, city: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Instagram Profile or @handle
                </label>
                <input
                  type="text"
                  placeholder="e.g. https://instagram.com/malabarroastery or @malabarroastery"
                  value={newLead.instagram_url}
                  onChange={(e) => setNewLead({ ...newLead, instagram_url: e.target.value })}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
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

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Phone / WhatsApp
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. +91 9876543210"
                    value={newLead.public_phone}
                    onChange={(e) => setNewLead({ ...newLead, public_phone: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
                <div>
                  <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                    Contact Email
                  </label>
                  <input
                    type="email"
                    placeholder="e.g. hello@malabarroastery.in"
                    value={newLead.public_email}
                    onChange={(e) => setNewLead({ ...newLead, public_email: e.target.value })}
                    className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
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
                  {formSubmitting ? "Saving..." : "Create Lead"}
                </button>
              </div>
            </form>
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
