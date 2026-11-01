import re

with open("backend/app/agent/adapters.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add logging import if not present
if "import logging" not in content:
    content = content.replace("import json\n", "import json\nimport logging\n", 1)
    content = content.replace("import json\r\n", "import json\r\nimport logging\r\n", 1)
if "logger = logging.getLogger" not in content:
    content = content.replace(
        "import httpx\n",
        "import httpx\n\nlogger = logging.getLogger(\"medivoice.gemini\")\n",
        1
    )
    content = content.replace(
        "import httpx\r\n",
        "import httpx\r\n\r\nlogger = logging.getLogger(\"medivoice.gemini\")\r\n",
        1
    )

# 2. Update GeminiReasoningAdapter.__init__
old_init_sig = """    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_tool_rounds: Optional[int] = None,
        http_client: Optional[httpx.Client] = None,
        strict_mode: bool = False,
        enable_model_fallback: bool = True,
    ):"""

new_init_sig = """    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_tool_rounds: Optional[int] = None,
        thinking_level: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        strict_mode: bool = False,
        enable_model_fallback: Optional[bool] = None,
    ):"""

# Normalize CRLF for replacement
if old_init_sig.replace("\n", "\r\n") in content:
    content = content.replace(old_init_sig.replace("\n", "\r\n"), new_init_sig.replace("\n", "\r\n"))
elif old_init_sig in content:
    content = content.replace(old_init_sig, new_init_sig)
else:
    print("Warning: old_init_sig not found directly, checking regex")

# Replace default model and enable_model_fallback in __init__
old_init_body = """        resolved_model = model or os.getenv("GEMINI_MODEL") or settings.GEMINI_MODEL or "gemini-2.5-flash"
        self.model: str = resolved_model.replace("models/", "").strip()"""

new_init_body = """        resolved_model = model or os.getenv("GEMINI_MODEL") or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.model: str = resolved_model.replace("models/", "").strip()"""

if old_init_body.replace("\n", "\r\n") in content:
    content = content.replace(old_init_body.replace("\n", "\r\n"), new_init_body.replace("\n", "\r\n"))
elif old_init_body in content:
    content = content.replace(old_init_body, new_init_body)

old_fallback_init = """        self.http_client = http_client
        self.strict_mode = strict_mode
        self.enable_model_fallback = enable_model_fallback
        self.last_error: Optional[str] = None
        self.last_model_used: Optional[str] = None"""

new_fallback_init = """        raw_thinking = (
            thinking_level
            if thinking_level is not None
            else os.getenv("GEMINI_THINKING_LEVEL", getattr(settings, "GEMINI_THINKING_LEVEL", "low"))
        )
        if raw_thinking and str(raw_thinking).strip().lower() not in ("", "none", "off", "false", "0"):
            self.thinking_level: Optional[str] = str(raw_thinking).strip().lower()
        else:
            self.thinking_level = None

        self.http_client = http_client
        self.strict_mode = strict_mode
        # Requirement 8: Do not silently fall back unless explicitly enabled
        if enable_model_fallback is not None:
            self.enable_model_fallback = bool(enable_model_fallback)
        else:
            self.enable_model_fallback = getattr(settings, "GEMINI_ENABLE_FALLBACK", False)
        self.last_error: Optional[str] = None
        self.last_model_used: Optional[str] = None"""

if old_fallback_init.replace("\n", "\r\n") in content:
    content = content.replace(old_fallback_init.replace("\n", "\r\n"), new_fallback_init.replace("\n", "\r\n"))
elif old_fallback_init in content:
    content = content.replace(old_fallback_init, new_fallback_init)

# 3. Update _call_provider logging and retry without thinkingConfig
old_call_provider_loop = """        for candidate_model in models_to_try:
            url = f"{self.GEMINI_API_BASE}/{candidate_model}:generateContent"
            try:
                if self.http_client is not None:
                    response = self.http_client.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
                else:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        response = client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                last_err = ReasoningAdapterError(
                    code="PROVIDER_TIMEOUT",
                    safe_message=f"Gemini API request timed out after {self.timeout_seconds}s.",
                )
                continue
            except httpx.HTTPError as exc:
                last_err = ReasoningAdapterError(
                    code="PROVIDER_NETWORK_ERROR",
                    safe_message="Network error while communicating with Gemini API.",
                )
                continue

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ReasoningAdapterError(
                        code="INVALID_PROVIDER_RESPONSE",
                        safe_message="Gemini API returned non-JSON response payload.",
                        status_code=response.status_code,
                    ) from exc

                self.last_model_used = candidate_model
                return data"""

new_call_provider_loop = """        for candidate_model in models_to_try:
            url = f"{self.GEMINI_API_BASE}/{candidate_model}:generateContent"
            logger.info("Executing turn with Gemini reasoning model: %s", candidate_model)
            try:
                if self.http_client is not None:
                    response = self.http_client.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
                else:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        response = client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                logger.warning("Gemini model '%s' timed out after %ss", candidate_model, self.timeout_seconds)
                last_err = ReasoningAdapterError(
                    code="PROVIDER_TIMEOUT",
                    safe_message=f"Gemini API request timed out after {self.timeout_seconds}s.",
                )
                continue
            except httpx.HTTPError as exc:
                logger.warning("Network error contacting Gemini model '%s': %s", candidate_model, exc)
                last_err = ReasoningAdapterError(
                    code="PROVIDER_NETWORK_ERROR",
                    safe_message="Network error while communicating with Gemini API.",
                )
                continue

            # Gracefully handle older rollback models that don't support thinkingConfig
            if response.status_code == 400 and "generationConfig" in payload and "thinkingConfig" in payload.get("generationConfig", {}):
                logger.info("Model '%s' returned 400 with thinkingConfig; retrying without thinkingConfig", candidate_model)
                retry_payload = {k: v for k, v in payload.items() if k != "generationConfig"}
                try:
                    if self.http_client is not None:
                        response = self.http_client.post(url, headers=headers, json=retry_payload, timeout=self.timeout_seconds)
                    else:
                        with httpx.Client(timeout=self.timeout_seconds) as client:
                            response = client.post(url, headers=headers, json=retry_payload)
                except Exception as retry_exc:
                    logger.warning("Retry without thinkingConfig failed: %s", retry_exc)

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ReasoningAdapterError(
                        code="INVALID_PROVIDER_RESPONSE",
                        safe_message="Gemini API returned non-JSON response payload.",
                        status_code=response.status_code,
                    ) from exc

                self.last_model_used = candidate_model
                logger.info("Turn successfully completed using Gemini model: %s (status=200)", candidate_model)
                return data"""

if old_call_provider_loop.replace("\n", "\r\n") in content:
    content = content.replace(old_call_provider_loop.replace("\n", "\r\n"), new_call_provider_loop.replace("\n", "\r\n"))
elif old_call_provider_loop in content:
    content = content.replace(old_call_provider_loop, new_call_provider_loop)

# 4. Add thinkingConfig to payload in plan_and_respond
old_payload_block = """                if tool_declarations:
                    payload["tools"] = [{"functionDeclarations": tool_declarations}]"""

new_payload_block = """                if tool_declarations:
                    payload["tools"] = [{"functionDeclarations": tool_declarations}]
                if self.thinking_level:
                    payload["generationConfig"] = {
                        "thinkingConfig": {
                            "thinkingLevel": self.thinking_level
                        }
                    }"""

if old_payload_block.replace("\n", "\r\n") in content:
    content = content.replace(old_payload_block.replace("\n", "\r\n"), new_payload_block.replace("\n", "\r\n"))
elif old_payload_block in content:
    content = content.replace(old_payload_block, new_payload_block)

with open("backend/app/agent/adapters.py", "w", encoding="utf-8") as f:
    f.write(content)

print("adapters.py updated successfully.")

