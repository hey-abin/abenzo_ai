from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any

# Lead schemas
class LeadCreate(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    industry: Optional[str] = ""
    state: Optional[str] = ""
    source_url: Optional[str] = ""
    instagram_url: Optional[str] = ""
    website_url: Optional[str] = ""

class LeadUpdate(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    state: Optional[str] = None
    source_url: Optional[str] = None
    instagram_url: Optional[str] = None
    website_url: Optional[str] = None
    website_status: Optional[str] = None
    evidence_json: Optional[Dict[str, Any]] = None
    business_summary: Optional[str] = None
    lead_score: Optional[int] = None
    confidence: Optional[str] = None
    opportunity: Optional[str] = None
    recommended_service: Optional[str] = None
    personalized_dm: Optional[str] = None
    reasoning_summary: Optional[str] = None
    next_best_action: Optional[str] = None
    outreach_status: Optional[str] = None

class LeadResponse(BaseModel):
    id: int
    business_name: str
    industry: str
    state: str
    source_url: str
    instagram_url: str
    website_url: str
    website_status: str
    evidence_json: Dict[str, Any]
    business_summary: str
    lead_score: int
    confidence: str
    opportunity: str
    recommended_service: str
    personalized_dm: str
    reasoning_summary: str
    next_best_action: str
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
    created_at: str
    updated_at: str
    events: List[ConversationEventResponse] = []

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
