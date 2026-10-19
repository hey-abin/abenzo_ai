import httpx
import json
import time
import re
from typing import Dict, Any, Optional, List
from backend.app.config import settings
from backend.app.schemas import OllamaHealth, LeadQualificationOutput
from backend.app.services.knowledge_service import get_approved_knowledge_summary

def clean_json_markdown(text: str) -> str:
    """Safely extracts JSON string from raw model output, stripping markdown code fences."""
    cleaned = text.strip()
    fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)
    match = fence_pattern.match(cleaned)
    if match:
        cleaned = match.group(1).strip()
    return cleaned

def parse_ai_json(raw_text: str) -> Dict[str, Any]:
    """Parses JSON safely, falling back to substring search if model returned preamble."""
    cleaned = clean_json_markdown(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end+1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"AI provider returned invalid JSON: {str(e)}")

async def check_ollama_health() -> OllamaHealth:
    """
    Checks health of the configured AI provider.
    Maintains OllamaHealth schema for backward compatibility with frontend settings.
    Never exposes provider API keys in health responses.
    """
    start_time = time.time()
    provider = getattr(settings, "AI_PROVIDER", "ollama").lower().strip()

    if provider == "openai_compatible":
        base_url = (settings.AI_BASE_URL or "").strip()
        model = (settings.AI_MODEL or "").strip()
        api_key = (settings.AI_API_KEY or "").strip()

        if not base_url:
            return OllamaHealth(
                reachable=False,
                base_url="",
                model=model,
                model_installed=False,
                available_models=[],
                error_message="AI_BASE_URL is not configured for hosted inference.",
                provider="openai_compatible"
            )

        if not api_key:
            return OllamaHealth(
                reachable=False,
                base_url=base_url,
                model=model,
                model_installed=False,
                available_models=[],
                error_message="AI_API_KEY is not configured.",
                provider="openai_compatible"
            )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        url = f"{base_url.rstrip('/')}/models"

        try:
            timeout = float(getattr(settings, "AI_TIMEOUT_SECONDS", 10))
            async with httpx.AsyncClient(timeout=min(timeout, 8.0)) as client:
                resp = await client.get(url, headers=headers)
                latency = round((time.time() - start_time) * 1000.0, 1)
                if resp.status_code == 200:
                    data = resp.json()
                    all_models = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
                    chat_models = [m for m in all_models if not any(x in m.lower() for x in ["whisper", "guard", "audio", "orpheus"])]
                    has_model = (model in all_models) if model else bool(chat_models)
                    err_msg = None
                    if model and not has_model:
                        rec = ", ".join(chat_models[:3]) if chat_models else "check provider console"
                        err_msg = f"Configured model '{model}' is unavailable on provider. Recommended chat models: {rec}"

                    return OllamaHealth(
                        reachable=True,
                        base_url=base_url,
                        model=model or (chat_models[0] if chat_models else "default"),
                        model_installed=has_model,
                        available_models=chat_models[:10] if chat_models else all_models[:10],
                        latency_ms=latency,
                        error_message=err_msg,
                        provider="openai_compatible"
                    )
                elif resp.status_code in (401, 403):
                    return OllamaHealth(
                        reachable=False,
                        base_url=base_url,
                        model=model,
                        model_installed=False,
                        available_models=[],
                        latency_ms=latency,
                        error_message="Authentication failed: invalid AI_API_KEY.",
                        provider="openai_compatible"
                    )
                elif resp.status_code == 429:
                    return OllamaHealth(
                        reachable=True,
                        base_url=base_url,
                        model=model,
                        model_installed=True,
                        available_models=[],
                        latency_ms=latency,
                        error_message="Hosted AI provider rate limit reached (HTTP 429).",
                        provider="openai_compatible"
                    )
                else:
                    return OllamaHealth(
                        reachable=False,
                        base_url=base_url,
                        model=model,
                        model_installed=False,
                        available_models=[],
                        error_message=f"Hosted AI provider returned HTTP {resp.status_code}",
                        provider="openai_compatible"
                    )
        except httpx.TimeoutException:
            return OllamaHealth(
                reachable=False,
                base_url=base_url,
                model=model,
                model_installed=False,
                available_models=[],
                error_message=f"Connection timed out reaching hosted provider at {base_url}",
                provider="openai_compatible"
            )
        except Exception as e:
            return OllamaHealth(
                reachable=False,
                base_url=base_url,
                model=model,
                model_installed=False,
                available_models=[],
                error_message=f"Connection error reaching {base_url}: {type(e).__name__}",
                provider="openai_compatible"
            )

    # Default: Ollama provider (Local Mac)
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            latency = (time.time() - start_time) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                has_model = any(settings.OLLAMA_MODEL in m for m in models)
                return OllamaHealth(
                    reachable=True,
                    base_url=settings.OLLAMA_BASE_URL,
                    model=settings.OLLAMA_MODEL,
                    model_installed=has_model,
                    available_models=models,
                    latency_ms=round(latency, 1),
                    error_message=None if has_model else f"Model '{settings.OLLAMA_MODEL}' not found. Run 'ollama pull {settings.OLLAMA_MODEL}'",
                    provider="ollama"
                )
            elif resp.status_code == 429:
                return OllamaHealth(
                    reachable=True,
                    base_url=settings.OLLAMA_BASE_URL,
                    model=settings.OLLAMA_MODEL,
                    model_installed=False,
                    available_models=[],
                    error_message="Ollama rate limit reached (HTTP 429)",
                    provider="ollama"
                )
            else:
                return OllamaHealth(
                    reachable=False,
                    base_url=settings.OLLAMA_BASE_URL,
                    model=settings.OLLAMA_MODEL,
                    model_installed=False,
                    available_models=[],
                    error_message=f"Ollama returned HTTP status {resp.status_code}",
                    provider="ollama"
                )
    except Exception as e:
        return OllamaHealth(
            reachable=False,
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            model_installed=False,
            available_models=[],
            error_message=f"Could not connect to Ollama at {settings.OLLAMA_BASE_URL}: {str(e)}",
            provider="ollama"
        )

async def call_ai_completion(prompt: str, temperature: float = 0.2) -> str:
    """
    Executes a structured completion against the configured AI provider.
    Defaults to local Ollama. Switches to OpenAI-compatible hosted provider when AI_PROVIDER=openai_compatible.
    Never exposes provider credentials in exceptions or error logs.
    """
    provider = getattr(settings, "AI_PROVIDER", "ollama").lower().strip()

    if provider == "openai_compatible":
        base_url = (settings.AI_BASE_URL or "").strip()
        api_key = (settings.AI_API_KEY or "").strip()
        model = (settings.AI_MODEL or "").strip()
        timeout = float(getattr(settings, "AI_TIMEOUT_SECONDS", 30))

        if not base_url:
            raise RuntimeError("Hosted AI inference failed: AI_BASE_URL is not configured.")
        if not api_key:
            raise RuntimeError("Hosted AI inference failed: AI_API_KEY is not configured.")
        if not model:
            raise RuntimeError("Hosted AI inference failed: AI_MODEL is not configured.")

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a sales assistant for Abenzo, an Indian web development agency. You must strictly output valid raw JSON adhering to the requested schema. Never output markdown outside the JSON."
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)

                # If the configured model is deprecated or not found (HTTP 404), auto-fallback to an active chat model
                if resp.status_code == 404 and any(phrase in resp.text.lower() for phrase in ["does not exist", "not have access", "not found"]):
                    models_resp = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                    if models_resp.status_code == 200:
                        all_models = [m.get("id", "") for m in models_resp.json().get("data", []) if isinstance(m, dict)]
                        chat_models = [m for m in all_models if not any(x in m.lower() for x in ["whisper", "guard", "audio", "orpheus"])]
                        for cand in chat_models:
                            if cand == model:
                                continue
                            payload["model"] = cand
                            retry_resp = await client.post(url, json=payload, headers=headers)
                            if retry_resp.status_code == 200:
                                resp = retry_resp
                                break

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise RuntimeError("Hosted AI provider returned empty choices list.")
                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        raise RuntimeError("Hosted AI provider returned empty message content.")
                    return content
                elif resp.status_code == 429:
                    raise RuntimeError("Hosted AI provider rate limit exceeded (HTTP 429). Please try again shortly.")
                elif resp.status_code in (401, 403):
                    raise RuntimeError("Hosted AI provider authentication failed (HTTP 401/403). Please verify AI_API_KEY.")
                else:
                    err_msg = f"Hosted AI inference error (HTTP {resp.status_code})"
                    try:
                        err_json = resp.json().get("error", {})
                        if isinstance(err_json, dict) and err_json.get("message"):
                            err_msg += f": {err_json['message']}"
                    except Exception:
                        pass
                    raise RuntimeError(err_msg)
        except httpx.TimeoutException:
            raise RuntimeError(f"Hosted AI inference timed out after {timeout} seconds.")
        except httpx.ConnectError:
            raise RuntimeError(f"Could not connect to hosted AI provider at {base_url}.")

    # Default: Local Ollama
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }
    timeout = float(settings.OLLAMA_TIMEOUT_SECONDS)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                raise RuntimeError("Ollama rate limit exceeded (HTTP 429).")
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama inference error (HTTP {resp.status_code}): {resp.text}")

            result_json = resp.json()
            return result_json.get("response", "{}")
    except httpx.TimeoutException:
        raise RuntimeError(f"Ollama inference timed out after {timeout} seconds.")
    except httpx.ConnectError:
        raise RuntimeError(f"Could not connect to Ollama at {settings.OLLAMA_BASE_URL}.")

async def qualify_lead_with_ai(lead_data: Dict[str, Any], agency_profile: Dict[str, Any]) -> LeadQualificationOutput:
    knowledge_context = get_approved_knowledge_summary()

    prompt = f"""You are the sales assistant for Abenzo, a web development agency based in India.
Your task is to analyze a potential business lead based strictly on verified public evidence.

RULES:
1. Do NOT invent business facts or claim certainty about buying intent.
2. If website evidence indicates an active good site, lead score should be lower or focus on redesign/speed/conversion.
3. If no website was found or status is uncertain, highlight the opportunity for a professional online presence without assuming they have zero digital presence.
4. Recommend services or packages ONLY from the approved Abenzo Knowledge Base.
5. Draft a personalized DM (30 to 60 words maximum).
   - Polite, natural, friendly.
   - Reference one specific factual observation from the lead evidence.
   - Propose an open, helpful next step (e.g., sharing a couple of ideas or portfolio).
   - Never pressure or assume they already agreed to anything.
6. Return ONLY a valid JSON object matching this schema:
{{
  "business_summary": "1-2 sentence factual summary",
  "industry": "Industry category",
  "website_status": "{lead_data.get('website_status', 'uncertain')}",
  "website_evidence_summary": "Factual evidence recap",
  "lead_score": 75,
  "confidence": "high|medium|low",
  "opportunity": "Specific web development opportunity",
  "recommended_service": "One of Abenzo's approved services/packages",
  "personalized_dm": "30-60 word natural draft message",
  "reasoning_summary": "Why this score and message fit the evidence",
  "next_best_action": "Recommended next step for Abin"
}}

APPROVED ABENZO KNOWLEDGE BASE:
{knowledge_context}

LEAD DATA TO ANALYZE:
- Business Name: {lead_data.get('business_name')}
- Industry: {lead_data.get('industry', 'Not specified')}
- State/Location: {lead_data.get('state', 'India')}
- Source URL: {lead_data.get('source_url', '')}
- Instagram URL: {lead_data.get('instagram_url', '')}
- Website URL: {lead_data.get('website_url', '')}
- Verified Website Status: {lead_data.get('website_status', 'uncertain')}
- Verified Evidence Details: {json.dumps(lead_data.get('evidence_json', {}))}
"""

    raw_response = await call_ai_completion(prompt, temperature=0.3)
    parsed = parse_ai_json(raw_response)

    score = int(parsed.get("lead_score", 50))
    score = max(0, min(100, score))
    parsed["lead_score"] = score

    return LeadQualificationOutput(**parsed)

async def draft_inbound_response_with_ai(
    incoming_message: str,
    conversation_history: list,
    agency_profile: Dict[str, Any],
    conversation_summary: str = "",
    lead_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    knowledge_context = get_approved_knowledge_summary()
    lead_context = lead_context or {}

    # Format history cleanly as chronological turns
    formatted_history = []
    for turn in (conversation_history[-8:] if conversation_history else []):
        if isinstance(turn, dict):
            role = turn.get("role") or ("user" if turn.get("direction") == "inbound" else "assistant")
            text = turn.get("content") or turn.get("message_text") or turn.get("approved_text") or turn.get("ai_draft") or ""
            if text:
                formatted_history.append({"role": role, "text": text})

    prompt = f"""You are a skilled, friendly, and natural sales consultant for Abenzo, an Indian web development agency.
You are chatting with a business owner / prospect on Instagram Direct Message.

CORE CONVERSATION BEHAVIORS:
1. Speak like a natural human consultant, not a corporate FAQ bot.
2. Conciseness is vital: Send 1 or 2 short sentences, ideally under 45 words.
3. Ask at most ONE relevant question per reply. Never ask multiple questions.
4. Respond directly to the customer's latest message and build upon what they already told you.
5. Never repeat greetings like "Hi! Thanks for reaching out" or robotic openings.
6. AVOID UNPROVOKED PRICING DUMPS:
   - If the customer says simple acknowledgments like "okay", "ohh okay", "cool", "thanks", "noted":
     * Do NOT dump the pricing list or push packages!
     * Acknowledge warmly and keep the door open or ask a gentle discovery question (e.g., "Sounds good! What features matter most for your shop?").
   - Quote pricing ONLY when:
     a) The customer explicitly asks about price/cost/packages, or
     b) You have understood enough requirements to give a useful starting estimate.
   - When discussing pricing, quote ONLY the single relevant starting price:
     * Starter: Starting at ₹15,000+ (3-5 pages, WhatsApp ordering, basic SEO)
     * Business: Starting at ₹30,000+ (5-10 pages, custom UI/UX, lead capture, analytics)
     * Professional: Starting at ₹50,000+ (custom UI/UX, database, advanced animations)
     * Custom SaaS / Web App: Starting at ₹75,000+ (tailored portals, CRM, workflows)
     Always state that final quote depends on their exact requirements. Never dump all four packages in one reply.
7. NEVER invent capabilities, guarantees, testimonials, discounts, or delivery timelines.
8. If the customer indicates interest in a call or moving to WhatsApp:
   - Acknowledge with enthusiasm, provide the official link (https://abenzo.in/contact), and STOP pitching.
9. Link presentation:
   - Include at most ONE relevant URL when helpful (e.g. portfolio https://abenzo.in/portfolio or contact https://abenzo.in/contact).
   - Use plain text URLs (no markdown brackets like [link](url) which break in Instagram DMs).

APPROVED ABENZO KNOWLEDGE BASE:
{knowledge_context}

EXISTING CONVERSATION SUMMARY:
{conversation_summary or "None yet (new conversation)."}

KNOWN STRUCTURED LEAD CONTEXT:
- Business Type: {lead_context.get("business_type", "Not yet known")}
- Requested Service: {lead_context.get("requested_service", "Not yet known")}
- Requirements: {lead_context.get("requirements", "Not yet known")}
- Budget: {lead_context.get("budget", "Not volunteered")}
- Timeline: {lead_context.get("timeline", "Not volunteered")}
- Objections: {lead_context.get("objections", "None")}
- Next Step: {lead_context.get("next_step", "Understand requirements")}

RECENT CONVERSATION HISTORY (Chronological):
{json.dumps(formatted_history)}

LATEST INCOMING MESSAGE:
"{incoming_message}"

Return ONLY a valid JSON object matching:
{{
  "ai_draft": "Your concise, natural 1-2 sentence reply (under 45 words, max 1 question)",
  "reasoning": "Brief rationale for why this reply fits the conversation progression",
  "lead_temperature": "early|qualified|ready_for_human",
  "needs_human_decision": false,
  "conversation_summary": "Updated 1-2 sentence summary of who they are and what they discussed",
  "lead_context": {{
    "business_type": "string",
    "requested_service": "string",
    "requirements": "string",
    "budget": "string",
    "timeline": "string",
    "objections": "string",
    "next_step": "string"
  }},
  "suggested_conversion_stage": "lead|qualified_lead|consultation_requested|proposal_requested|won|lost"
}}
"""

    raw_response = await call_ai_completion(prompt, temperature=0.25)
    parsed = parse_ai_json(raw_response)
    if "lead_context" not in parsed or not isinstance(parsed["lead_context"], dict):
        parsed["lead_context"] = lead_context
    if "conversation_summary" not in parsed:
        parsed["conversation_summary"] = conversation_summary
    return parsed
