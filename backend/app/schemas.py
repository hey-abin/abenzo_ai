from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any

# Lead schemas
class LeadCreate(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    industry: Optional[str] = ""
    state: Optional[str] = ""
    city: Optional[str] = ""
    source_url: Optional[str] = ""
    instagram_url: Optional[str] = ""
    instagram_handle: Optional[str] = ""
    website_url: Optional[str] = ""
    contact_name: Optional[str] = ""
    public_phone: Optional[str] = ""
    public_email: Optional[str] = ""
    project_timeline: Optional[str] = ""
    budget: Optional[str] = ""
    consent_source: Optional[str] = ""
    follow_up_date: Optional[str] = ""

class LeadUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    source_url: Optional[str] = None
    instagram_url: Optional[str] = None
    instagram_handle: Optional[str] = None
    website_url: Optional[str] = None
    website_status: Optional[str] = None
    evidence_json: Optional[Dict[str, Any]] = None
    business_summary: Optional[str] = None
    lead_score: Optional[int] = None
    confidence: Optional[str] = None
    opportunity: Optional[str] = None
    recommended_service: Optional[str] = None
    suggested_service: Optional[str] = None
    observed_problems: Optional[str] = None
    score_breakdown_json: Optional[Dict[str, Any]] = None
    personalized_dm: Optional[str] = None
    reasoning_summary: Optional[str] = None
    next_best_action: Optional[str] = None
    outreach_status: Optional[str] = None
    contact_name: Optional[str] = None
    public_phone: Optional[str] = None
    public_email: Optional[str] = None
    project_timeline: Optional[str] = None
    budget: Optional[str] = None
    consent_source: Optional[str] = None
    follow_up_date: Optional[str] = None
    outreach_action_at: Optional[str] = None
    conversation_id: Optional[int] = None

class LeadResponse(BaseModel):
    id: int
    business_name: str
    industry: str
    state: str
    city: Optional[str] = ""
    source_url: str
    instagram_url: str
    instagram_handle: Optional[str] = ""
    website_url: str
    website_status: str
    evidence_json: Dict[str, Any]
    business_summary: str
    lead_score: int
    confidence: str
    opportunity: str
    recommended_service: str
    suggested_service: Optional[str] = ""
    observed_problems: Optional[str] = ""
    score_breakdown_json: Optional[Dict[str, Any]] = {}
    personalized_dm: str
    reasoning_summary: str
    next_best_action: str
    contact_name: Optional[str] = ""
    public_phone: Optional[str] = ""
    public_email: Optional[str] = ""
    project_timeline: Optional[str] = ""
    budget: Optional[str] = ""
    consent_source: Optional[str] = ""
    follow_up_date: Optional[str] = ""
    outreach_action_at: Optional[str] = ""
    conversation_id: Optional[int] = None
    source_media_id: Optional[str] = ""
    source_media_url: Optional[str] = ""
    source_caption: Optional[str] = ""
    discovery_hashtag: Optional[str] = ""
    campaign_id: Optional[int] = None
    outreach_status: str
    created_at: str
    updated_at: str

class LeadQualificationOutput(BaseModel):
    business_summary: str = Field(..., description="1-2 sentences summarizing business based only on provided evidence")
    industry: str = Field(..., description="Detected industry")
    website_status: str = Field(..., description="'found', 'not_found', or 'uncertain'")
    website_evidence_summary: str = Field(..., description="Factual justification for website status")
    lead_score: int = Field(..., ge=0, le=100, description="Fit score 0-100 based on website need and digital opportunity")
    confidence: str = Field(..., description="'high', 'medium', or 'low'")
    opportunity: str = Field(..., description="Specific opportunity for Abenzo web development services")
    recommended_service: str = Field(..., description="Service best matching the lead's state")
    personalized_dm: str = Field(..., description="Short 30-60 word polite, non-pushy message referencing real observation")
    reasoning_summary: str = Field(..., description="Why this lead was scored and recommended this way")
    next_best_action: str = Field(..., description="Actionable next step for Abin")

class WebsiteCheckResult(BaseModel):
    url: str
    status: str  # 'found', 'not_found', 'uncertain'
    status_code: Optional[int] = None
    title: Optional[str] = None
    evidence_summary: str
    meta_description: Optional[str] = None
    has_contact_or_inquiry: bool = False
    is_mobile_responsive_indicated: bool = False
    raw_details: Dict[str, Any] = {}

class ConversationEventCreate(BaseModel):
    conversation_id: int
    external_event_id: Optional[str] = None
    event_type: str = "dm"
    direction: str = "inbound"
    message_text: str
    delivery_status: str = "received"

class ConversationEventResponse(BaseModel):
    id: int
    conversation_id: int
    external_event_id: Optional[str] = None
    event_type: str
    direction: str
    message_text: str
    ai_draft: str
    approved_text: str
    delivery_status: str
    meta_message_id: Optional[str] = ""
    error_details: Optional[str] = ""
    sent_at: Optional[str] = ""
    created_at: str

class ConversationResponse(BaseModel):
    id: int
    platform: str
    external_thread_id: Optional[str] = None
    recipient_id: Optional[str] = ""
    contact_display_name: str
    lead_id: Optional[int] = None
    last_message_at: Optional[str] = None
    status: str
    needs_human: int
    lead_temperature: str
    notes: str
    conversation_summary: Optional[str] = ""
    lead_context: Optional[Dict[str, Any]] = {}
    conversion_stage: Optional[str] = "lead"
    auto_reply_paused: Optional[int] = 0
    created_at: str
    updated_at: str
    events: List[ConversationEventResponse] = []

class ConversationUpdate(BaseModel):
    needs_human: Optional[int] = None
    lead_temperature: Optional[str] = None
    conversion_stage: Optional[str] = None
    auto_reply_paused: Optional[int] = None
    notes: Optional[str] = None

class SendReplyRequest(BaseModel):
    event_id: int
    approved_text: Optional[str] = None

class ConversationReplyRequest(BaseModel):
    message_text: str

class SendReplyResponse(BaseModel):
    status: str  # 'sent' or 'failed'
    event_id: int
    delivery_status: str
    meta_message_id: Optional[str] = ""
    recipient_id: str
    sent_at: Optional[str] = ""
    error_details: Optional[str] = ""

class LeadDiscoveryQuery(BaseModel):
    niche: Optional[str] = ""
    city_or_state: Optional[str] = ""
    keywords: Optional[str] = ""
    source_mode: Optional[str] = "instagram_only"  # 'instagram_only' or 'all_sources'
    stage: Optional[str] = "all"  # 'all', 'small_business', 'startup', 'local_brand'
    website_filter: Optional[str] = "all"  # 'all', 'has_website', 'no_website', 'needs_improvement', 'unknown'
    min_score: Optional[int] = 0
    limit: Optional[int] = 10
    exclude_crm: Optional[bool] = False
    search_provider: Optional[str] = None  # None (auto), 'serper', 'duckduckgo', 'tavily', 'brave', 'serpapi'

class LeadDiscoveryItem(BaseModel):
    business_name: str
    instagram_username: Optional[str] = ""
    instagram_handle: Optional[str] = ""
    instagram_url: Optional[str] = ""
    website_url: Optional[str] = ""
    domain: Optional[str] = ""
    contact_details: Optional[str] = ""
    public_phone: Optional[str] = ""
    public_email: Optional[str] = ""
    source_url: str = ""
    industry: Optional[str] = ""
    business_category: Optional[str] = ""
    state: Optional[str] = ""
    city: Optional[str] = ""
    snippet: Optional[str] = ""
    business_stage: Optional[str] = "small_business"
    website_status: Optional[str] = "unknown"
    observed_problems: Optional[str] = ""
    suggested_service: Optional[str] = ""
    personalized_dm: Optional[str] = ""
    lead_score: int = 50
    score_reasons: List[str] = []
    score_breakdown: Optional[Dict[str, int]] = {}
    already_exists: bool = False
    is_duplicate: bool = False
    existing_lead_id: Optional[int] = None
    reachable: bool = True
    status_code: Optional[int] = 200
    discovered_at: Optional[str] = ""
    provider_source: Optional[str] = ""

class DiscoveryDiagnostics(BaseModel):
    queries_executed: List[str] = []
    raw_results_count: int = 0
    instagram_urls_count: int = 0
    rejected_counts: Dict[str, int] = {
        "non_profile_path": 0,
        "aggregator_or_listicle": 0,
        "invalid_username": 0,
        "other": 0
    }
    valid_profiles_count: int = 0
    duplicates_removed: int = 0
    provider_errors: int = 0
    timeouts: int = 0
    rate_limits: int = 0
    provider_status: str = "ok"  # 'ok', 'rate_limited_202', 'timeout', 'error', 'no_results'
    provider_used: str = ""
    provider_error_message: Optional[str] = None
    fallback_used: bool = False
    selected_provider: str = ""
    key_configured: bool = False
    provider_request_status: str = ""
    fallback_attempts: List[str] = []

class LeadDiscoveryResponse(BaseModel):
    status: str
    query: str
    provider: str
    results: List[LeadDiscoveryItem] = []
    total_found: int = 0
    source_mode: Optional[str] = "instagram_only"
    limitation_notice: Optional[str] = None
    error_message: Optional[str] = None
    diagnostics: Optional[DiscoveryDiagnostics] = None

class ImportDiscoveredRequest(BaseModel):
    items: List[LeadDiscoveryItem]

class BusinessProfile(BaseModel):
    agency_name: str = "Abenzo"
    tagline: str = "Web Development Agency serving businesses across India"
    services: List[str] = []
    portfolio_urls: List[str] = []
    contact_email: str = "hello@abenzo.in"
    contact_phone: Optional[str] = ""
    service_areas: str = "All Indian States"
    approved_faq: List[Dict[str, str]] = []
    starting_prices: Optional[str] = ""
    discovery_call_url: Optional[str] = ""
    tone_guidelines: str = ""
    allowed_claims: str = ""
    auto_reply_faq_enabled: bool = False

class OllamaHealth(BaseModel):
    reachable: bool
    base_url: str
    model: str
    model_installed: bool
    available_models: List[str]
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    provider: Optional[str] = "ollama"

class MetaStatus(BaseModel):
    configured: bool
    status: str # 'not_configured', 'awaiting_authorization', 'connected', 'permission_missing', 'error'
    app_id_set: bool
    access_token_set: bool
    verify_token_set: bool
    account_id: Optional[str] = None
    username: Optional[str] = None
    account_type: Optional[str] = None
    profile_name: Optional[str] = None
    profile_picture_url: Optional[str] = None
    api_host: str = "graph.instagram.com"
    granted_permissions: List[str] = []
    missing_permissions: List[str] = []
    capabilities: Dict[str, bool] = {}
    guidance: str = ""
    error_details: Optional[str] = None
    tested_at: Optional[str] = None

class LeadSendMessageRequest(BaseModel):
    message_text: Optional[str] = None

class LeadSendMessageResponse(BaseModel):
    status: str
    delivery_status: str
    meta_message_id: Optional[str] = ""
    event_id: Optional[int] = None
    conversation_id: Optional[int] = None
    lead_id: int
    sent_at: Optional[str] = ""
    error_details: Optional[str] = ""

class LeadMessagingStatusResponse(BaseModel):
    eligible: bool
    can_send: bool
    conversation_id: Optional[int] = None
    recipient_id: Optional[str] = ""
    platform: str = "manual"
    within_messaging_window: bool = False
    meta_connected: bool = False
    reason: str
    suggested_action: str  # 'dashboard_send' | 'manual_outreach'
    outreach_status: str = "new"
    draft_message: Optional[str] = ""

class AutomationSettings(BaseModel):
    auto_reply_enabled: bool = True
    auto_reply_paused_global: bool = False
    require_human_approval: bool = False

class AutomationSettingsResponse(BaseModel):
    auto_reply_enabled: bool
    auto_reply_paused_global: bool
    require_human_approval: bool
    meta_status: Dict[str, Any]
    messaging_policy: str = "Meta Graph API policy strictly prohibits automated cold outbound DMs to users who have not previously initiated contact. Inbound messages are supported within a 24-hour window."

# ---------------------------------------------------------------------------
# Autonomous Prospecting Campaign Schemas
# ---------------------------------------------------------------------------

class ResearchedHashtagItem(BaseModel):
    hashtag: str
    rationale: str = ""
    service_fit: str = ""
    times_used: int = 0
    last_used_at: Optional[str] = ""
    prospects_found: int = 0
    qualified_found: int = 0

class CampaignProspectItem(BaseModel):
    lead_id: Optional[int] = None
    business_name: str
    instagram_handle: Optional[str] = ""
    instagram_url: Optional[str] = ""
    source_media_url: Optional[str] = ""
    source_media_id: Optional[str] = ""
    source_caption: Optional[str] = ""
    website_url: Optional[str] = ""
    website_status: str = "uncertain"
    lead_score: int = 0
    confidence: str = "medium"
    opportunity: str = ""
    recommended_service: str = ""
    evidence: List[str] = []
    personalized_dm: str = ""
    discovery_hashtag: str = ""
    outreach_status: str = "draft"
    is_duplicate: bool = False
    rejection_reason: Optional[str] = None

class CampaignResponse(BaseModel):
    id: int
    status: str  # 'running', 'completed', 'failed', 'cancelled'
    stage: str   # 'checking_apis', 'researching_hashtags', 'discovering_media', 'analyzing_prospects', 'qualifying', 'generating_drafts', 'saving_crm', 'completed', 'failed', 'cancelled'
    current_step_text: str = ""
    selected_hashtags: List[Dict[str, Any]] = []
    meta_status: Dict[str, Any] = {}
    discovered_posts_count: int = 0
    unique_profiles_count: int = 0
    qualified_prospects_count: int = 0
    drafts_generated_count: int = 0
    duplicates_count: int = 0
    rejected_count: int = 0
    provider_failures: List[str] = []
    results_summary: List[Dict[str, Any]] = []
    error_message: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = ""
    created_at: str
    updated_at: str

class CampaignStartRequest(BaseModel):
    max_hashtags: Optional[int] = 4
    limit_per_hashtag: Optional[int] = 5

