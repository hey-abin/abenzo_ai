"use client";

import { useEffect, useState } from "react";
import { 
  BookOpen, 
  Sparkles, 
  RefreshCw, 
  Plus, 
  ExternalLink, 
  CheckCircle, 
  Clock, 
  AlertCircle, 
  Trash2, 
  Edit3, 
  Globe, 
  Search, 
  Check, 
  X,
  ShieldCheck
} from "lucide-react";
import { 
  fetchKnowledgeItems, 
  importWebsiteKnowledge, 
  updateKnowledgeItem, 
  deleteKnowledgeItem, 
  createKnowledgeItem 
} from "@/lib/api";

const CATEGORIES = [
  { id: "all", label: "All Knowledge" },
  { id: "package", label: "Packages & Pricing" },
  { id: "service", label: "Specialized Services" },
  { id: "portfolio", label: "Portfolio Projects" },
  { id: "faq", label: "Approved FAQs" },
  { id: "process", label: "Project Process" },
  { id: "contact", label: "Contact & HQ" },
];

const CATEGORY_COLORS = {
  package: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800",
  service: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800",
  portfolio: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800",
  faq: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800",
  process: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-400 dark:border-cyan-800",
  contact: "bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700",
};

export default function KnowledgePage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [activeCategory, setActiveCategory] = useState("all");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // Edit State
  const [editingItem, setEditingItem] = useState(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");

  // Add Fact Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [newCategory, setNewCategory] = useState("package");
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newSource, setNewSource] = useState("https://abenzo.vercel.app");

  const loadKnowledge = () => {
    setLoading(true);
    fetchKnowledgeItems({
      category: activeCategory !== "all" ? activeCategory : undefined,
      status: statusFilter !== "all" ? statusFilter : undefined,
      search: search || undefined
    })
      .then((data) => {
        setItems(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Knowledge fetch error:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadKnowledge();
  }, [activeCategory, statusFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadKnowledge();
  };

  const handleImport = async () => {
    setImporting(true);
    try {
      const res = await importWebsiteKnowledge("https://abenzo.vercel.app");
      alert(`Knowledge Import Complete!\nExtracted: ${res.items_extracted} items (${res.inserted} new, ${res.updated} updated).`);
      loadKnowledge();
    } catch (err) {
      alert("Import error: " + err.message);
    } finally {
      setImporting(false);
    }
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      const updated = await updateKnowledgeItem(id, { verification_status: newStatus });
      setItems((prev) => prev.map((item) => (item.id === id ? updated : item)));
    } catch (err) {
      alert("Failed to update status");
    }
  };

  const handleSaveEdit = async () => {
    if (!editingItem) return;
    try {
      const updated = await updateKnowledgeItem(editingItem.id, {
        title: editTitle,
        content: editContent
      });
      setItems((prev) => prev.map((item) => (item.id === editingItem.id ? updated : item)));
      setEditingItem(null);
    } catch (err) {
      alert("Failed to save changes: " + err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Are you sure you want to remove this fact from the Knowledge Base?")) return;
    try {
      await deleteKnowledgeItem(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      alert("Failed to delete item: " + err.message);
    }
  };

  const handleCreateFact = async (e) => {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) {
      alert("Title and content are required.");
      return;
    }
    try {
      await createKnowledgeItem({
        category: newCategory,
        title: newTitle.trim(),
        content: newContent.trim(),
        source_url: newSource.trim() || "Manual",
        verification_status: "approved"
      });
      setShowAddModal(false);
      setNewTitle("");
      setNewContent("");
      loadKnowledge();
    } catch (err) {
      alert("Failed to add fact: " + err.message);
    }
  };

  const approvedCount = items.filter(i => i.verification_status === "approved").length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-zinc-800 dark:text-zinc-200" />
            Website Knowledge Base
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Verified packages, starting prices, services, portfolio, and FAQs imported from{" "}
            <a href="https://abenzo.vercel.app" target="_blank" rel="noreferrer" className="text-blue-600 underline dark:text-blue-400">
              abenzo.vercel.app
            </a>. Only approved facts are used by Ollama.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleImport}
            disabled={importing}
            className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${importing ? "animate-spin" : ""}`} />
            {importing ? "Importing..." : "Sync from abenzo.vercel.app"}
          </button>

          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Fact
          </button>

          <button
            onClick={loadKnowledge}
            disabled={loading}
            className="rounded-md border border-zinc-300 bg-white p-2 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
            title="Refresh list"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Safety Notice Card */}
      <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4 text-xs text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
        <div className="flex items-start gap-2.5">
          <ShieldCheck className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <span className="font-semibold">
              Ground-Truth Knowledge Guardrails Active ({approvedCount} Approved Facts in SQLite)
            </span>
            <p className="text-emerald-800/80 dark:text-emerald-300/80">
              The local Ollama AI model references these exact facts when drafting replies and lead opportunities. The AI is strictly instructed to quote only verified starting prices (Starter: ₹15,000+, Business: ₹30,000+, Professional: ₹50,000+, Custom Software: ₹75,000+) and will never fabricate fixed deadlines or unauthorized discounts.
            </p>
          </div>
        </div>
      </div>

      {/* Category Tabs & Search Bar */}
      <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        {/* Category Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-zinc-100 pb-3 dark:border-zinc-800">
          {CATEGORIES.map((cat) => {
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }`}
              >
                {cat.label}
              </button>
            );
          })}
        </div>

        {/* Search & Status Filter */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between pt-1">
          <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-zinc-400" />
            <input
              type="text"
              placeholder="Search packages, services, questions, prices..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded border border-zinc-300 bg-transparent py-1.5 pl-8 pr-3 text-xs placeholder:text-zinc-400 dark:border-zinc-700 dark:text-zinc-100 focus:outline-hidden"
            />
          </form>

          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded border border-zinc-300 bg-white py-1 px-2 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
            >
              <option value="all">All Statuses</option>
              <option value="approved">Approved Only</option>
              <option value="pending_review">Pending Review</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>
      </div>

      {/* Knowledge Items Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {items.length === 0 ? (
          <div className="col-span-full rounded-lg border border-dashed border-zinc-200 p-12 text-center text-xs text-zinc-500 dark:border-zinc-800">
            {loading
              ? "Loading knowledge items..."
              : "No knowledge facts found matching filter. Click 'Sync from abenzo.vercel.app' above to import."}
          </div>
        ) : (
          items.map((item) => {
            const isEditing = editingItem?.id === item.id;
            const categoryBadge = CATEGORY_COLORS[item.category] || CATEGORY_COLORS.contact;

            return (
              <div
                key={item.id}
                className="rounded-lg border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-900 flex flex-col justify-between"
              >
                <div className="space-y-2.5">
                  {/* Category & Status Row */}
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold border ${categoryBadge}`}>
                      {item.category.toUpperCase()}
                    </span>

                    <select
                      value={item.verification_status}
                      onChange={(e) => handleStatusChange(item.id, e.target.value)}
                      className={`rounded border text-[10px] font-medium py-0.5 px-1.5 ${
                        item.verification_status === "approved"
                          ? "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-400"
                          : item.verification_status === "pending_review"
                          ? "bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-950/60 dark:text-amber-400"
                          : "bg-red-50 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-400"
                      }`}
                    >
                      <option value="approved">Approved</option>
                      <option value="pending_review">Pending Review</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  </div>

                  {/* Title & Content */}
                  {isEditing ? (
                    <div className="space-y-2 pt-1">
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        className="w-full rounded border border-zinc-300 p-1.5 text-xs font-semibold dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                      />
                      <textarea
                        rows="4"
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        className="w-full rounded border border-zinc-300 p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                      />
                      <div className="flex justify-end gap-1.5 pt-1">
                        <button
                          onClick={() => setEditingItem(null)}
                          className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] text-zinc-600 dark:border-zinc-700"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSaveEdit}
                          className="rounded bg-zinc-900 px-2.5 py-0.5 text-[11px] font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <h3 className="font-bold text-sm text-zinc-900 dark:text-zinc-100 mb-1.5">
                        {item.title}
                      </h3>
                      <p className="text-xs text-zinc-600 dark:text-zinc-300 whitespace-pre-line leading-relaxed">
                        {item.content}
                      </p>
                    </div>
                  )}
                </div>

                {/* Footer metadata & actions */}
                {!isEditing && (
                  <div className="mt-4 pt-3 border-t border-zinc-100 dark:border-zinc-800 flex items-center justify-between text-[10px] text-zinc-400">
                    <div className="flex items-center gap-1 truncate max-w-[220px]" title={item.source_url}>
                      <Globe className="h-3 w-3 shrink-0" />
                      <a
                        href={item.source_url.startsWith("http") ? item.source_url : "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="truncate hover:underline text-blue-600 dark:text-blue-400"
                      >
                        {item.source_url}
                      </a>
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setEditingItem(item);
                          setEditTitle(item.title);
                          setEditContent(item.content);
                        }}
                        title="Edit fact"
                        className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
                      >
                        <Edit3 className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => handleDelete(item.id)}
                        title="Delete fact"
                        className="rounded p-1 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/50"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Add Custom Fact Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800">
            <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 mb-4">
              Add Verified Business Fact
            </h2>

            <form onSubmit={handleCreateFact} className="space-y-3 text-xs">
              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Category
                </label>
                <select
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                >
                  <option value="package">Package & Pricing</option>
                  <option value="service">Specialized Service</option>
                  <option value="portfolio">Portfolio Project</option>
                  <option value="faq">Approved FAQ</option>
                  <option value="process">Project Process</option>
                  <option value="contact">Contact & HQ</option>
                </select>
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Title / Subject *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Starter Package (₹15,000+)"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Fact Details & Inclusions *
                </label>
                <textarea
                  rows="4"
                  required
                  placeholder="Provide exact factual details. Note that final quotes depend strictly on scope."
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  className="w-full rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                />
              </div>

              <div>
                <label className="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                  Source Reference URL
                </label>
                <input
                  type="text"
                  placeholder="https://abenzo.vercel.app/services"
                  value={newSource}
                  onChange={(e) => setNewSource(e.target.value)}
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
                  className="rounded bg-zinc-900 px-3 py-1.5 font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900"
                >
                  Add to Knowledge Base
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
