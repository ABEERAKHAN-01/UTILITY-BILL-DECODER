"""One thin wrapper over the three allowed providers: image prep, throttling, retries, JSON parsing."""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import threading
import time
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

MAX_RETRIES = 5
_FATAL_HINTS = ("api key not valid", "invalid api key", "incorrect api key", "api_key_invalid",
                "permission denied", "unauthorized", "authentication")


def parse_json(text: str):
    """Parse a model reply that should be JSON (tolerates ```json fences and stray prose)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"not valid JSON: {t[:120]!r}")


class LLM:
    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._images: dict = {}
        self._client = self._make_client()

    # ------------------------------------------------------------------ setup
    def _make_client(self):
        s = self.settings
        try:
            if s.provider == "google":
                from google import genai
                return genai.Client(api_key=s.api_key)
            if s.provider == "anthropic":
                import anthropic
                return anthropic.Anthropic(api_key=s.api_key)
            if s.provider == "openai":
                from openai import OpenAI
                return OpenAI(api_key=s.api_key)
        except ImportError as exc:
            raise SystemExit(f"Missing package for provider '{s.provider}': {exc}. "
                             "Run: pip install -r requirements.txt "
                             "(and requirements-optional.txt for anthropic/openai)") from exc
        raise SystemExit(f"Unsupported provider: {s.provider}")

    # ------------------------------------------------------------------ images
    def _prepare(self, image) -> tuple[bytes, str]:
        """EXIF auto-rotate, flatten transparency, downscale huge images, encode as JPEG."""
        p = Path(image)
        key = (str(p.resolve()), p.stat().st_mtime_ns, self.settings.max_image_side)
        if key in self._images:
            return self._images[key]
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            side = max(im.size)
            if side > self.settings.max_image_side:
                scale = self.settings.max_image_side / side
                im = im.resize((round(im.width * scale), round(im.height * scale)),
                               Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=92)
        self._images[key] = (buf.getvalue(), "image/jpeg")
        return self._images[key]

    # ------------------------------------------------------------------ calls
    def _throttle(self) -> None:
        """Global rate limit shared by all worker threads (free Gemini tier = 15 req/min)."""
        delay = self.settings.request_delay
        if delay <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + delay
        if wait > 0:
            time.sleep(wait)

    def ask(self, prompt: str, image=None, system: str | None = None, json_mode: bool = False) -> str:
        img = self._prepare(image) if image else None
        last: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                text = self._generate(prompt, img, system, json_mode)
                if not text or not text.strip():
                    raise RuntimeError("empty response")
                return text
            except Exception as exc:  # network, rate limit, 5xx, safety block ...
                last = exc
                if any(h in str(exc).lower() for h in _FATAL_HINTS):
                    raise RuntimeError(f"{self.settings.provider} rejected the request: {exc}. "
                                       "Check API_KEY in .env.") from exc
                wait = min(60, 5 * 2 ** (attempt - 1))
                log.warning("LLM call failed (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(wait)
        raise RuntimeError(f"{self.settings.provider} request failed after {MAX_RETRIES} attempts: {last}") from last

    def ask_json(self, prompt: str, image=None, system: str | None = None):
        last: Exception | None = None
        for _ in range(3):
            text = self.ask(prompt, image, system, json_mode=True)
            try:
                return parse_json(text)
            except ValueError as exc:
                last = exc
                log.warning("model returned invalid JSON, retrying (%s)", exc)
        raise ValueError(f"model did not return valid JSON: {last}")

    # ------------------------------------------------------------------ providers
    def _generate(self, prompt, img, system, json_mode) -> str:
        s = self.settings
        if s.provider == "google":
            from google.genai import types
            parts = []
            if img:
                parts.append(types.Part.from_bytes(data=img[0], mime_type=img[1]))
            parts.append(prompt)
            cfg = types.GenerateContentConfig(
                temperature=0, system_instruction=system, max_output_tokens=16384,
                response_mime_type="application/json" if json_mode else None)
            resp = self._client.models.generate_content(model=s.model, contents=parts, config=cfg)
            return resp.text or ""

        b64 = base64.b64encode(img[0]).decode() if img else None
        if s.provider == "anthropic":
            content = []
            if img:
                content.append({"type": "image",
                                "source": {"type": "base64", "media_type": img[1], "data": b64}})
            content.append({"type": "text", "text": prompt})
            kwargs = {"model": s.model, "max_tokens": 8192, "temperature": 0,
                      "messages": [{"role": "user", "content": content}]}
            if system:
                kwargs["system"] = system
            resp = self._client.messages.create(**kwargs)
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

        # openai
        content = [{"type": "text", "text": prompt}]
        if img:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{img[1]};base64,{b64}"}})
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": content}]
        kwargs = {"model": s.model, "messages": messages, "max_completion_tokens": 16000}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if not s.model.startswith("gpt-5"):
            kwargs["temperature"] = 0
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
