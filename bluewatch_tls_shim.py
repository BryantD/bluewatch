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

import typing as t

from atproto import Client
from atproto_client.request import RequestBase, Request, _handle_response
from curl_cffi import requests as curl_requests

_IMPERSONATE = "chrome131"


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
        return _handle_response(response)

    def close(self) -> None:
        self._session.close()


def make_client(*args: t.Any, **kwargs: t.Any) -> Client:
    kwargs.setdefault("request", CurlCffiRequest())
    return Client(*args, **kwargs)
