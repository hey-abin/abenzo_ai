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
                    models = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
                    has_model = True if not model else any(model in m for m in models) or bool(models)
                    return OllamaHealth(
                        reachable=True,
                        base_url=base_url,
                        model=model or (models[0] if models else "default"),
                        model_installed=has_model,
                        available_models=models[:10],
                        latency_ms=latency,
                        error_message=None,
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
    agency_profile: Dict[str, Any]
) -> Dict[str, Any]:
    knowledge_context = get_approved_knowledge_summary()

    prompt = f"""You are the sales assistant for Abenzo, an Indian web development agency.
A customer has sent an inbound message or question.

STRICT KNOWLEDGE & HONESTY RULES:
1. Use ONLY the approved information from the Abenzo Knowledge Base below.
2. NEVER invent exact quotes, discounts, delivery dates, or guarantees.
3. For package pricing:
   - Quote ONLY starting prices:
     * Starter Package: Starting at ₹15,000+ (3–5 pages, WhatsApp integration, basic SEO)
     * Business Package: Starting at ₹30,000+ (5–10 pages, custom UI/UX, lead capture, analytics)
     * Professional Package: Starting at ₹50,000+ (custom UI/UX, advanced animations, database, APIs)
     * Custom Software / SaaS: Starting at ₹75,000+ (tailored SaaS, CRM, booking portals, dashboards)
   - ALWAYS state that final pricing depends strictly on project requirements and scope.
4. If the user asks for a specific price, exact timeline, or something NOT in the knowledge base:
   - State that Abin and the team will confirm the exact details or provide a tailored proposal after discussing requirements.
5. In your internal reasoning, include the exact source reference (e.g. source URL / package name).
6. Assess lead temperature: 'early', 'qualified', or 'ready_for_human'.

APPROVED ABENZO KNOWLEDGE BASE (PACKAGES, SERVICES, PORTFOLIO, FAQS, CONTACT):
{knowledge_context}

INCOMING MESSAGE:
"{incoming_message}"

RECENT CONVERSATION CONTEXT:
{json.dumps(conversation_history[-4:] if conversation_history else [])}

Return ONLY a valid JSON object matching:
{{
  "ai_draft": "Your suggested polite, concise reply text quoting only approved info",
  "reasoning": "Why this reply is suggested and how it aligns with verified facts",
  "lead_temperature": "early|qualified|ready_for_human",
  "needs_human_decision": true,
  "matched_faq_question": "string or null",
  "source_references": ["List of package or page sources used, e.g. https://abenzo.co.in/llms.txt"]
}}
"""

    raw_response = await call_ai_completion(prompt, temperature=0.2)
    return parse_ai_json(raw_response)
