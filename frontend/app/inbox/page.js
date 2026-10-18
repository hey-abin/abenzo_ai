"use client";

import { useEffect, useState } from "react";
import { 
  Inbox, 
  MessageSquare, 
  Sparkles, 
  Check, 
  CheckCircle, 
  AlertCircle, 
  Plus, 
  RefreshCw, 
  ShieldAlert, 
  Send,
  User,
  Info
} from "lucide-react";
import InstagramIcon from "@/components/InstagramIcon";
import { 
  fetchConversations, 
  approveEvent, 
  sendEventReply,
  sendConversationReply,
  createSampleConversation, 
  fetchMetaStatus,
  syncInstagramMessages
} from "@/lib/api";

export default function InboxPage() {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedConv, setSelectedConv] = useState(null);
  const [editedReply, setEditedReply] = useState("");
  const [approving, setApproving] = useState(false);
  const [sending, setSending] = useState(false);
  const [creatingSample, setCreatingSample] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [metaStatus, setMetaStatus] = useState(null);
  const [filterNeedsHuman, setFilterNeedsHuman] = useState("all");

  const loadInbox = () => {
    setLoading(true);
    fetchConversations({
      needs_human: filterNeedsHuman === "needs_human" ? 1 : undefined
    })
      .then((data) => {
        setConversations(data);
        if (data.length > 0 && !selectedConv) {
          setSelectedConv(data[0]);
          const pendingEvent = data[0].events?.find((e) => e.delivery_status === "draft_pending");
          setEditedReply(pendingEvent?.ai_draft || "");
        } else if (selectedConv) {
          const updated = data.find((c) => c.id === selectedConv.id);
          if (updated) setSelectedConv(updated);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error("Inbox load error:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadInbox();
    fetchMetaStatus().then(setMetaStatus).catch(() => {});
  }, [filterNeedsHuman]);

  const handleSelectConv = (conv) => {
    setSelectedConv(conv);
    const activeEvent = conv.events?.find((e) => 
      e.delivery_status === "draft_pending" || e.delivery_status === "approved" || e.delivery_status === "failed"
    );
    setEditedReply(activeEvent?.approved_text || activeEvent?.ai_draft || "");
  };

  const handleApprove = async (eventId) => {
    if (!editedReply.trim()) {
      alert("Reply text cannot be blank.");
      return;
    }
    setApproving(true);
    try {
      await approveEvent(eventId, editedReply);
      loadInbox();
      alert("Response approved and saved. Ready to dispatch.");
    } catch (err) {
      alert("Approval error: " + err.message);
    } finally {
      setApproving(false);
    }
  };

  const handleSendMessage = async (activeEventId = null) => {
    if (!editedReply.trim()) {
      alert("Reply text cannot be blank.");
      return;
    }

    const isInstagram = selectedConv?.platform === "instagram";
    const promptMsg = isInstagram 
      ? "Dispatch this reply directly to the recipient on Instagram via Meta Graph API?" 
      : "Send this simulated message to the sample thread?";

    if (!confirm(promptMsg)) {
      return;
    }

    setSending(true);
    try {
      if (activeEventId) {
        const res = await sendEventReply(activeEventId, editedReply);
        alert(isInstagram 
          ? `Message successfully dispatched to Instagram!\nMeta Message ID: ${res.meta_message_id || "confirmed"}`
          : "Simulated reply recorded in sample thread.");
      } else {
        const res = await sendConversationReply(selectedConv.id, editedReply);
        alert(isInstagram 
          ? `Message successfully dispatched to Instagram!\nMeta Message ID: ${res.meta_message_id || "confirmed"}`
          : "Simulated reply recorded in sample thread.");
      }
      setEditedReply("");
      loadInbox();
    } catch (err) {
      alert("Send Error: " + err.message);
      loadInbox();
    } finally {
      setSending(false);
    }
  };

  const handleCreateSample = async () => {
    setCreatingSample(true);
    try {
      await createSampleConversation();
      loadInbox();
    } catch (err) {
      alert("Failed to create sample conversation: " + err.message);
    } finally {
      setCreatingSample(false);
    }
  };

  const handleSyncInstagram = async () => {
    setSyncing(true);
    try {
      const res = await syncInstagramMessages();
      alert(`Instagram Sync: ${res.new_messages_synced} new messages synced from ${res.threads_checked} threads.`);
      loadInbox();
    } catch (err) {
      alert("Instagram Sync: " + err.message);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            Inbound Messages & DMs
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Review inbound inquiries, inspect AI draft answers based on approved FAQs, and approve responses.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {metaStatus?.configured && (
            <button
              onClick={handleSyncInstagram}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 rounded-md border border-pink-200 bg-pink-50 px-3 py-1.5 text-xs font-medium text-pink-700 hover:bg-pink-100 dark:border-pink-800 dark:bg-pink-950/40 dark:text-pink-300"
            >
              <InstagramIcon className="h-3.5 w-3.5" />
              {syncing ? "Syncing..." : "Sync Instagram DMs"}
            </button>
          )}

          <button
            onClick={handleCreateSample}
            disabled={creatingSample}
            className="inline-flex items-center gap-1.5 rounded-md border border-purple-200 bg-purple-50 px-3 py-1.5 text-xs font-medium text-purple-700 hover:bg-purple-100 dark:border-purple-800 dark:bg-purple-950/40 dark:text-purple-300"
          >
            <Sparkles className={`h-3.5 w-3.5 ${creatingSample ? "animate-spin" : ""}`} />
            {creatingSample ? "Creating..." : "+ Add Sample Event (Test)"}
          </button>
          <button
            onClick={loadInbox}
            disabled={loading}
            className="rounded-md border border-zinc-300 bg-white p-2 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
            title="Refresh inbox"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Meta Webhook Status Notice */}
      <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-start gap-3">
          <Info className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
          <div className="text-xs space-y-1">
            <span className="font-semibold text-zinc-900 dark:text-zinc-100">
              Official Meta Graph API Status: {metaStatus?.status || "Checking..."}
            </span>
            <p className="text-zinc-600 dark:text-zinc-400">
              {metaStatus?.configured
                ? "Official webhook listener active at /api/meta/webhook."
                : "No live Meta credentials configured yet in .env. Manual inbox mode and local AI testing remain fully operational using sample inbound events."}
            </p>
          </div>
        </div>
      </div>

      {/* Main Inbox View: List + Active Conversation */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Conversation List */}
        <div className="rounded-lg border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-900 overflow-hidden">
          <div className="border-b border-zinc-200 p-3 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-800/40 flex items-center justify-between">
            <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
              Conversations ({conversations.length})
            </span>
            <select
              value={filterNeedsHuman}
              onChange={(e) => setFilterNeedsHuman(e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-0.5 text-[11px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            >
              <option value="all">All Threads</option>
              <option value="needs_human">Needs Attention</option>
            </select>
          </div>

          <div className="divide-y divide-zinc-100 dark:divide-zinc-800 max-h-[600px] overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="p-8 text-center text-xs text-zinc-500">
                {loading ? "Loading inbox..." : "No inbound conversations yet. Click '+ Add Sample Event (Test)' above to test the AI draft workflow."}
              </div>
            ) : (
              conversations.map((conv) => {
                const isSelected = selectedConv?.id === conv.id;
                const lastEvent = conv.events?.[conv.events.length - 1];
                return (
                  <div
                    key={conv.id}
                    onClick={() => handleSelectConv(conv)}
                    className={`cursor-pointer p-3.5 transition-colors ${
                      isSelected
                        ? "bg-zinc-50 dark:bg-zinc-800/60"
                        : "hover:bg-zinc-50/50 dark:hover:bg-zinc-800/30"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-xs text-zinc-900 dark:text-zinc-100 truncate max-w-[170px]">
                        {conv.contact_display_name}
                      </span>
                      {conv.needs_human ? (
                        <span className="rounded bg-amber-100 px-1.5 py-0.2 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/60 dark:text-amber-400">
                          Action Needed
                        </span>
                      ) : (
                        <span className="rounded bg-emerald-100 px-1.5 py-0.2 text-[10px] font-medium text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-400">
                          Approved
                        </span>
                      )}
                    </div>

                    <p className="text-[11px] text-zinc-500 line-clamp-2">
                      {lastEvent ? lastEvent.message_text : "No messages yet"}
                    </p>

                    <div className="mt-2 flex items-center justify-between text-[10px] text-zinc-400">
                      <span className="capitalize">{conv.platform.replace("_", " ")}</span>
                      <span>Temp: {conv.lead_temperature}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Selected Conversation & AI Drafting Pane */}
        <div className="lg:col-span-2 rounded-lg border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900 flex flex-col justify-between">
          {selectedConv ? (
            <div className="space-y-4">
              {/* Header */}
              <div className="flex items-center justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
                <div>
                  <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100">
                    {selectedConv.contact_display_name}
                  </h2>
                  <div className="flex items-center gap-2 text-xs text-zinc-500">
                    <span className="capitalize">{selectedConv.platform.replace("_", " ")}</span>
                    <span>•</span>
                    <span>Lead Temperature: <strong className="text-zinc-800 dark:text-zinc-200">{selectedConv.lead_temperature}</strong></span>
                  </div>
                </div>

                {selectedConv.needs_human ? (
                  <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800">
                    Human Review Required
                  </span>
                ) : (
                  <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800">
                    Resolved / Approved
                  </span>
                )}
              </div>

              {/* Message Thread */}
              <div className="space-y-3 max-h-[300px] overflow-y-auto p-2 bg-zinc-50/50 rounded-md dark:bg-zinc-950/30 border border-zinc-100 dark:border-zinc-800">
                {selectedConv.events?.map((ev) => (
                  <div
                    key={ev.id}
                    className={`flex flex-col ${ev.direction === "inbound" ? "items-start" : "items-end"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-lg p-3 text-xs leading-relaxed ${
                        ev.direction === "inbound"
                          ? "bg-white text-zinc-900 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:border-zinc-700"
                          : "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                      }`}
                    >
                      <div className="font-semibold text-[10px] text-zinc-400 mb-1 flex items-center justify-between gap-2">
                        <span>
                          {ev.direction === "inbound" ? "Prospect" : "Abenzo Outbound"} • {new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                        {ev.delivery_status === "sent" && (
                          <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-medium text-emerald-400">
                            Sent {ev.meta_message_id ? `(${ev.meta_message_id.slice(-6)})` : ""}
                          </span>
                        )}
                        {ev.delivery_status === "sending" && (
                          <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[9px] font-medium text-blue-400">
                            Sending...
                          </span>
                        )}
                        {ev.delivery_status === "approved" && (
                          <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[9px] font-medium text-blue-300">
                            Approved (Ready)
                          </span>
                        )}
                        {ev.delivery_status === "failed" && (
                          <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[9px] font-medium text-red-400">
                            Failed
                          </span>
                        )}
                      </div>
                      <p>{ev.approved_text || ev.message_text}</p>
                      {ev.delivery_status === "failed" && ev.error_details && (
                        <div className="mt-1.5 rounded bg-red-950/40 p-1.5 text-[10px] text-red-300 border border-red-900/50">
                          {ev.error_details}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Response & Compose Box */}
              {(() => {
                const activeEvent = selectedConv.events?.find((e) => 
                  e.delivery_status === "draft_pending" || 
                  e.delivery_status === "approved" || 
                  e.delivery_status === "failed"
                );

                const isInstagram = selectedConv.platform === "instagram";
                const isSample = selectedConv.platform === "instagram_sample" || selectedConv.platform === "manual";
                const hasValidRecipient = Boolean(
                  selectedConv.recipient_id || 
                  (selectedConv.external_thread_id && !selectedConv.external_thread_id.startsWith("sample_") && !selectedConv.external_thread_id.startsWith("manual_"))
                );

                return (
                  <div className="rounded-md border border-purple-200 bg-purple-50/30 p-4 space-y-3 dark:border-purple-900/50 dark:bg-purple-950/20">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-purple-900 dark:text-purple-300 flex items-center gap-1.5">
                        <Sparkles className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                        {activeEvent ? (
                          activeEvent.delivery_status === "draft_pending"
                            ? "AI Suggested Reply Draft (Review & Dispatch)"
                            : activeEvent.delivery_status === "approved"
                            ? "Approved Response (Ready to Dispatch)"
                            : "Reply Delivery Failed (Review & Retry)"
                        ) : (
                          "Compose Message / Follow-up"
                        )}
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        {isInstagram ? (
                          <span className="text-pink-600 font-semibold flex items-center gap-1">
                            <InstagramIcon className="h-3 w-3 inline" /> Live Instagram DM
                          </span>
                        ) : (
                          <span className="text-purple-600 font-medium">Sample Thread (Demo Mode)</span>
                        )}
                        {activeEvent ? ` • STATUS: ${activeEvent.delivery_status.toUpperCase()}` : ""}
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-[11px] font-medium text-zinc-700 dark:text-zinc-300">
                          {activeEvent ? "Response Text (Human Approval Mandatory):" : "Reply Text:"}
                        </label>
                        {activeEvent?.ai_draft && editedReply !== activeEvent.ai_draft && (
                          <button
                            type="button"
                            onClick={() => setEditedReply(activeEvent.ai_draft)}
                            className="text-[10px] text-purple-600 hover:text-purple-800 dark:text-purple-400"
                          >
                            Reset to AI Draft
                          </button>
                        )}
                      </div>
                      <textarea
                        rows="3"
                        placeholder="Type your reply to this prospect..."
                        value={editedReply}
                        onChange={(e) => setEditedReply(e.target.value)}
                        className="w-full rounded border border-zinc-300 p-2.5 text-xs bg-white text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100 dark:border-zinc-700 focus:outline-hidden"
                      />
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pt-1">
                      <span className="text-[11px] text-zinc-500 flex items-center gap-1">
                        <ShieldAlert className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                        {isInstagram 
                          ? "Dispatches directly to recipient via official Meta Graph API."
                          : "Simulated send for sample conversation testing."}
                      </span>

                      <div className="flex items-center gap-2">
                        {activeEvent && (
                          <button
                            type="button"
                            onClick={() => handleApprove(activeEvent.id)}
                            disabled={approving || sending}
                            className="inline-flex items-center gap-1.5 rounded border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                          >
                            <Check className="h-3.5 w-3.5 text-blue-500" />
                            {approving ? "Saving..." : "Approve Only"}
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => handleSendMessage(activeEvent?.id)}
                          disabled={approving || sending || (isInstagram && !hasValidRecipient)}
                          className="inline-flex items-center gap-1.5 rounded bg-zinc-900 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
                        >
                          <Send className="h-3.5 w-3.5 text-emerald-400" />
                          {sending 
                            ? "Sending..." 
                            : isInstagram
                            ? (activeEvent?.delivery_status === "failed" ? "Retry Send to IG" : "Send to Instagram")
                            : "Send Message (Sample)"}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          ) : (
            <div className="p-12 text-center text-xs text-zinc-500">
              Select a conversation to view message history, inspect the AI draft, and approve responses.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
