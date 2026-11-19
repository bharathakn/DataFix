"""Gemini access with failover (primary key -> retry -> backup key -> offline) and a PII safety net.

The only module allowed to import google.genai, lazily. Nothing here ever decides a cell value.
"""
import hashlib
import json
import os
import re
import time

from .privacy import mask_text

# each model has its own free-tier daily quota (2.5 Flash: 20 requests/day/project), so we fail over across models
DEFAULT_MODELS = "gemini-2.5-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite"


class LLMUnavailable(Exception):
    pass


def sanitize(obj):
    """Last line of defence: mask anything that looks like PII in every string we send."""
    if isinstance(obj, str):
        return mask_text(obj, "partial")
    if isinstance(obj, dict):
        return {k: sanitize(x) for k, x in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(x) for x in obj]
    return obj


class Gemini:
    def __init__(self):
        self.keys = [k.strip() for k in (os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_API_KEY_BACKUP", "")) if k.strip()]
        self.models = [m.strip() for m in (os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODELS).split(",") if m.strip()]
        self.model = self.models[0]
        self.timeout_ms = int(os.getenv("DATAFIX_LLM_TIMEOUT_MS", "15000"))
        self._clients = None
        self._cache: dict[str, str] = {}
        self.last_ok: bool | None = None
        self.last_error: str | None = None
        self.last_key: int | None = None
        self.cooldown: dict[str, float] = {}  # model -> time until which every key is rate-limited
        self.calls: list[dict] = []  # recent calls, for the status endpoint
        self.cooldown_s = float(os.getenv("DATAFIX_LLM_COOLDOWN_S", "60"))

    @property
    def enabled(self) -> bool:
        return bool(self.keys) and os.getenv("DATAFIX_OFFLINE", "") not in ("1", "true")

    def status(self) -> dict:
        now = time.time()
        return {"provider": "gemini" if self.enabled else "offline", "model": self.model if self.enabled else None,
                "models": self.models, "keys": len(self.keys), "ok": self.last_ok if self.enabled else False,
                "last_error": self.last_error, "using_backup_key": self.last_key == 1,
                "cooling_down": {m: round(t - now) for m, t in self.cooldown.items() if t > now},
                "recent_calls": self.calls[-8:]}

    def _get_clients(self):
        if self._clients is None:
            from google import genai
            from google.genai import types
            opts = types.HttpOptions(api_version="v1beta", timeout=self.timeout_ms)
            self._clients = [genai.Client(api_key=k, http_options=opts) for k in self.keys]
        return self._clients

    def generate(self, contents, config):
        """Try each model in order, each with every key. A 429 (quota) skips straight to the next key; if every key
        is rate-limited for a model, that model cools down and the next model is tried."""
        if not self.enabled:
            raise LLMUnavailable("no Gemini key configured (offline mode)")
        last = None
        now = time.time()
        for model in self.models:
            if self.cooldown.get(model, 0) > now:
                continue
            cfg = config.model_copy(update={"thinking_config": thinking_config(model)})
            limited, retry_s = 0, self.cooldown_s
            for idx, client in enumerate(self._get_clients()):
                for attempt in range(2):
                    t0 = time.time()
                    try:
                        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
                        self._log(model, idx, t0, "ok")
                        self.last_ok, self.last_error, self.last_key, self.model = True, None, idx, model
                        return resp
                    except Exception as e:  # quota, overload, timeout, network
                        last = e
                        msg = str(e)
                        self._log(model, idx, t0, msg[:60])
                        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                            limited += 1
                            delay = re.search(r"retryDelay['\"]?: ['\"]?(\d+)", msg)
                            if delay and "PerDay" in msg:  # daily quota: don't probe again until it resets
                                retry_s = max(retry_s, min(float(delay.group(1)), 6 * 3600))
                            break
                        if attempt == 0 and idx == 0:
                            time.sleep(1)  # transient overload: one retry on the primary key
                        else:
                            break
            if limited == len(self.keys):
                self.cooldown[model] = time.time() + retry_s
        self.last_ok, self.last_error = False, f"{type(last).__name__}: {str(last)[:200]}" if last else "all models cooling down"
        raise LLMUnavailable(self.last_error)

    def _log(self, model: str, key: int, t0: float, outcome: str) -> None:
        self.calls.append({"model": model, "key": key, "ms": int((time.time() - t0) * 1000), "outcome": outcome})
        del self.calls[:-50]

    def text(self, prompt: str, system: str | None = None) -> str:
        if not self.enabled:
            raise LLMUnavailable("no Gemini key configured (offline mode)")
        from google.genai import types
        prompt = sanitize(prompt)
        key = hashlib.sha256(json.dumps([system, prompt]).encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.2, thinking_config=thinking_config())
        resp = self.generate(prompt, cfg)
        out = (resp.text or "").strip()
        if not out:
            raise LLMUnavailable("empty response")
        self._cache[key] = out
        return out


_instance: Gemini | None = None


def thinking_config(model: str | None = None):
    """Thinking makes answers slow (2.5 Flash: ~6 s vs ~2 s). Summaries and tool choice don't need it:
    2.5 models get budget 0, Gemini 3 models get level 'minimal'. DATAFIX_LLM_THINKING overrides the 2.5 budget."""
    from google.genai import types
    if model and not model.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_level="minimal")
    return types.ThinkingConfig(thinking_budget=int(os.getenv("DATAFIX_LLM_THINKING", "0")))


def get_llm() -> Gemini:
    global _instance
    if _instance is None:
        _instance = Gemini()
    return _instance


def reset_llm() -> None:
    global _instance
    _instance = None


# ---------------------------------------------------------------- narrative helpers with template fallback

def causes_narrative(causes: list[dict]) -> tuple[str, str]:
    top = [{"title": c["title"], "explanation": c["explanation"]} for c in causes[:6]]
    template = " ".join(c["title"] + "." for c in top[:3]) or "No concentrated source of errors was found."
    if not top:
        return template, "offline"
    try:
        text = get_llm().text(
            "Summarise these data-quality root causes for a business user in at most 3 short sentences. "
            "Use only the facts given; keep the numbers exact; no bullet points.\n" + json.dumps(top, ensure_ascii=False),
            system="You explain data-quality findings precisely. Never invent numbers.")
        return text, "gemini"
    except LLMUnavailable:
        return template, "offline"


def explain_proposal(p) -> tuple[str, str]:
    if p.refusal_reason:
        return f"DataFix did not change this value: {p.refusal_reason}.", "offline"
    if not p.candidates:
        return "No repair proposed.", "offline"
    c = p.candidates[0]
    good = [s.detail for s in c.signals if not s.conflicting and s.reliability > 0][:3]
    bad = [s.detail for s in c.signals if s.conflicting][:2]
    template = f"DataFix suggests '{c.value}' ({c.confidence:.0%} confident) because " + "; ".join(good) + \
               (f". But: {'; '.join(bad)}" if bad else "") + "."
    try:
        text = get_llm().text(
            f"Explain in one or two plain sentences why '{p.original_value}' in column '{p.column}' should become "
            f"'{c.value}', using only this evidence: {json.dumps(good + bad, ensure_ascii=False)}. "
            f"Mention the confidence {c.confidence:.0%}.",
            system="You explain data repairs to non-technical reviewers. Use only the given evidence.")
        return text, "gemini"
    except LLMUnavailable:
        return template, "offline"
