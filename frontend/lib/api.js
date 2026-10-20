const rawApiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api").trim().replace(/\/+$/, "");
const API_BASE = rawApiUrl.endsWith("/api") ? rawApiUrl : `${rawApiUrl}/api`;

export async function fetchMetrics() {
  const res = await fetch(`${API_BASE}/leads/metrics`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load metrics");
  return res.json();
}

export async function fetchLeads(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      query.append(k, v);
    }
  });
  const res = await fetch(`${API_BASE}/leads?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load leads");
  return res.json();
}

export async function createLead(data) {
  const res = await fetch(`${API_BASE}/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to create lead" }));
    throw new Error(err.detail || "Failed to create lead");
  }
  return res.json();
}

export async function updateLead(id, data) {
  const res = await fetch(`${API_BASE}/leads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update lead");
  return res.json();
}

export async function deleteLead(id) {
  const res = await fetch(`${API_BASE}/leads/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete lead");
  return res.json();
}

export async function checkWebsite(id) {
  const res = await fetch(`${API_BASE}/leads/${id}/check-website`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to verify website");
  return res.json();
}

export async function recalculateLeadQualification(id) {
  const res = await fetch(`${API_BASE}/leads/${id}/recalculate-qualification`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to recalculate lead qualification");
  return res.json();
}

export async function fetchLeadMessagingStatus(leadId) {
  const res = await fetch(`${API_BASE}/leads/${leadId}/messaging-status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load messaging status");
  return res.json();
}

export async function sendLeadMessage(leadId, messageText = "") {
  const res = await fetch(`${API_BASE}/leads/${leadId}/send-message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_text: messageText }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to send message" }));
    throw new Error(err.detail || "Failed to send message");
  }
  return res.json();
}

export async function qualifyLeadAI(id) {
  const res = await fetch(`${API_BASE}/leads/${id}/qualify-ai`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "AI qualification failed" }));
    throw new Error(err.detail || "AI qualification failed");
  }
  return res.json();
}

export async function importCSV(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/leads/import-csv`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("CSV import failed");
  return res.json();
}

export function getExportCSVUrl() {
  return `${API_BASE}/leads/export-csv`;
}

export async function fetchConversations(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") {
      query.append(k, v);
    }
  });
  const res = await fetch(`${API_BASE}/inbox/conversations?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load conversations");
  return res.json();
}

export async function approveEvent(eventId, approvedText) {
  const res = await fetch(`${API_BASE}/inbox/events/${eventId}/approve?approved_text=${encodeURIComponent(approvedText)}`, {
    method: "POST"
  });
  if (!res.ok) throw new Error("Failed to approve event response");
  return res.json();
}

export async function sendEventReply(eventId, approvedText) {
  const res = await fetch(`${API_BASE}/meta/send-reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, approved_text: approvedText }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to dispatch reply to Instagram" }));
    throw new Error(err.detail || "Failed to dispatch reply to Instagram");
  }
  return res.json();
}

export async function sendConversationReply(conversationId, messageText) {
  const res = await fetch(`${API_BASE}/inbox/conversations/${conversationId}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_text: messageText }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to dispatch reply" }));
    throw new Error(err.detail || "Failed to dispatch reply");
  }
  return res.json();
}

export async function createSampleConversation() {
  const res = await fetch(`${API_BASE}/inbox/sample-conversation`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to create sample conversation");
  return res.json();
}

export async function fetchSystemHealth() {
  const res = await fetch(`${API_BASE}/settings/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch system health");
  return res.json();
}

export async function fetchBusinessProfile() {
  const res = await fetch(`${API_BASE}/settings/profile`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch business profile");
  return res.json();
}

export async function updateBusinessProfile(profile) {
  const res = await fetch(`${API_BASE}/settings/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error("Failed to update profile");
  return res.json();
}

export async function fetchMetaStatus() {
  const res = await fetch(`${API_BASE}/meta/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch Meta status");
  return res.json();
}

export async function fetchAutomationSettings() {
  const res = await fetch(`${API_BASE}/settings/automation`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load automation settings");
  return res.json();
}

export async function updateAutomationSettings(data) {
  const res = await fetch(`${API_BASE}/settings/automation`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update automation settings");
  return res.json();
}

export async function testMetaConnection() {
  const res = await fetch(`${API_BASE}/meta/test-connection`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to test connection");
  return res.json();
}

export async function syncInstagramMessages() {
  const res = await fetch(`${API_BASE}/meta/sync`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Sync failed" }));
    throw new Error(err.detail || "Sync failed");
  }
  return res.json();
}

export async function fetchKnowledgeItems(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== "all") {
      query.append(k, v);
    }
  });
  const res = await fetch(`${API_BASE}/knowledge?${query.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load knowledge items");
  return res.json();
}

export async function importWebsiteKnowledge(siteUrl = "https://abenzo.vercel.app") {
  const res = await fetch(`${API_BASE}/knowledge/import?site_url=${encodeURIComponent(siteUrl)}`, {
    method: "POST"
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Knowledge import failed" }));
    throw new Error(err.detail || "Knowledge import failed");
  }
  return res.json();
}

export async function updateKnowledgeItem(id, data) {
  const res = await fetch(`${API_BASE}/knowledge/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update knowledge item");
  return res.json();
}

export async function deleteKnowledgeItem(id) {
  const res = await fetch(`${API_BASE}/knowledge/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete knowledge item");
  return res.json();
}

export async function createKnowledgeItem(data) {
  const res = await fetch(`${API_BASE}/knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create knowledge item");
  return res.json();
}

export async function discoverLeads(params) {
  const res = await fetch(`${API_BASE}/leads/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Lead discovery failed" }));
    throw new Error(err.detail || "Lead discovery failed");
  }
  return res.json();
}

export async function importDiscoveredLeads(items) {
  const res = await fetch(`${API_BASE}/leads/import-discovered`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Importing discovered leads failed" }));
    throw new Error(err.detail || "Importing discovered leads failed");
  }
  return res.json();
}

export async function updateConversation(id, data) {
  const res = await fetch(`${API_BASE}/inbox/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update conversation");
  return res.json();
}

// ---------------------------------------------------------------------------
// Autonomous Prospecting Campaign API
// ---------------------------------------------------------------------------

export async function startCampaign(params = {}) {
  const res = await fetch(`${API_BASE}/campaigns/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to start campaign" }));
    throw new Error(err.detail || "Failed to start campaign");
  }
  return res.json();
}

export async function fetchActiveCampaign() {
  const res = await fetch(`${API_BASE}/campaigns/active`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load active campaign");
  return res.json();
}

export async function fetchCampaign(id) {
  const res = await fetch(`${API_BASE}/campaigns/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load campaign");
  return res.json();
}

export async function cancelCampaign(id) {
  const res = await fetch(`${API_BASE}/campaigns/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to cancel campaign");
  return res.json();
}

export async function fetchCampaigns() {
  const res = await fetch(`${API_BASE}/campaigns`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load campaigns");
  return res.json();
}

export async function fetchResearchedHashtags() {
  const res = await fetch(`${API_BASE}/campaigns/hashtags`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load researched hashtags");
  return res.json();
}

export async function fetchMetaCapabilities() {
  const res = await fetch(`${API_BASE}/campaigns/meta-capabilities`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load Meta capabilities");
  return res.json();
}

