"""TLS-fingerprint workaround for atproto -> Bluesky login.

Bluesky's AWS WAF currently blocks requests bearing python-httpx's TLS
fingerprint, returning an HTML 403 from awselb/2.0 before the request
reaches the Bluesky API. The atproto SDK uses httpx internally, so
``Client.login()`` raises ``UnauthorizedError`` regardless of credentials.

This module substitutes a curl_cffi-backed Request implementation that
impersonates a real browser's TLS fingerprint. atproto exposes this
extension point via ``Client(request=...)`` (see MarshalX/atproto #594).

To remove once upstream is fixed:
  1. Delete this file.
  2. Drop the matching import + workaround block in bluewatch.py.
  3. Replace ``make_client()`` callsites with ``Client()``.
  4. Drop ``curl-cffi`` from the PEP 723 header and pyproject.toml.
"""

import json
import logging
import re
import typing as t

from atproto import Client
from atproto_client.request import RequestBase, Request, _handle_response
from curl_cffi import requests as curl_requests

logger = logging.getLogger(__name__)

_IMPERSONATE = "chrome131"

# === Unknown-embed workaround (remove when atproto models gallery embeds) ===
# Bluesky's AppView returns embed view types (e.g. app.bsky.embed.gallery#view)
# that atproto's strict Pydantic discriminated unions don't recognize, which
# makes it reject the *entire* feed response. bluewatch never reads embeds, so
# we rewrite any unknown embed view to a minimal valid images#view before
# atproto validates. Drop this block once atproto ships the missing models.
_EMBED_VIEW_RE = re.compile(r"^app\.bsky\.embed\.\w+#view$")
_KNOWN_EMBED_VIEWS = {
    "app.bsky.embed.images#view",
    "app.bsky.embed.video#view",
    "app.bsky.embed.external#view",
    "app.bsky.embed.record#view",
    "app.bsky.embed.recordWithMedia#view",
}
_EMBED_REPLACEMENT = {"$type": "app.bsky.embed.images#view", "images": []}


def _sanitize_embeds(obj: t.Any) -> int:
    """Recursively rewrite unknown embed views in-place. Returns count rewritten."""
    rewritten = 0
    if isinstance(obj, dict):
        embed_type = obj.get("$type")
        if (
            isinstance(embed_type, str)
            and _EMBED_VIEW_RE.match(embed_type)
            and embed_type not in _KNOWN_EMBED_VIEWS
        ):
            obj.clear()
            obj.update(_EMBED_REPLACEMENT)
            return 1
        for value in obj.values():
            rewritten += _sanitize_embeds(value)
    elif isinstance(obj, list):
        for item in obj:
            rewritten += _sanitize_embeds(item)
    return rewritten


class CurlCffiRequest(Request):
    def __init__(self, impersonate: str = _IMPERSONATE) -> None:
        RequestBase.__init__(self)
        self._session = curl_requests.Session(impersonate=impersonate)

    def _send_request(self, method: str, url: str, **kwargs: t.Any):
        headers = self.get_headers(kwargs.pop("headers", None))
        # atproto >= 0.0.65 follows httpx's convention of `content=` for raw
        # request bodies; curl_cffi spells it `data=`.
        if "content" in kwargs:
            kwargs["data"] = kwargs.pop("content")
        response = self._session.request(
            method=method, url=url, headers=headers, **kwargs
        )
        self._rewrite_unknown_embeds(response)
        return _handle_response(response)

    @staticmethod
    def _rewrite_unknown_embeds(response: t.Any) -> None:
        """Strip unknown embed view types from a successful JSON response body."""
        if not 200 <= response.status_code <= 299:
            return
        content_type = response.headers.get("content-type") or ""
        if "application/json" not in content_type.lower():
            return
        try:
            payload = json.loads(response.content)
        except (ValueError, TypeError):
            return
        rewritten = _sanitize_embeds(payload)
        if rewritten:
            logger.debug("Rewrote %d unknown embed view(s) in response", rewritten)
            response.content = json.dumps(payload).encode("utf-8")

    def close(self) -> None:
        self._session.close()


def make_client(*args: t.Any, **kwargs: t.Any) -> Client:
    kwargs.setdefault("request", CurlCffiRequest())
    return Client(*args, **kwargs)
