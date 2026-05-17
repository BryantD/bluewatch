# atproto / Bluesky `httpx` TLS-fingerprint workaround

## Symptom

`atproto.Client().login(...)` raises `UnauthorizedError` with HTTP 403 even when
credentials (handle + app password) are known-good. The response body is HTML:

```
<html>
<head><title>403 Forbidden</title></head>
<body>
<center><h1>403 Forbidden</h1></center>
</body>
</html>
```

and the response `server` header is `awselb/2.0`. Bluesky's real API errors
come back as JSON from an Express server, so this means the request is being
rejected by Bluesky's AWS load balancer **before** it ever reaches the API.

Hit in the wild as of May 2026. Not filed in `MarshalX/atproto` at time of
writing — the SDK has no awareness of this.

## Root cause

Bluesky's AWS WAF is rejecting requests with the TLS fingerprint (JA3/JA4)
that `python-httpx` produces. The `atproto` SDK uses `httpx` internally.

Quick confirmation on any affected host:

```bash
# both should succeed (proper 401 JSON from Bluesky):
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://bsky.social/xrpc/com.atproto.server.createSession \
  -H 'Content-Type: application/json' -d '{"identifier":"x","password":"x"}'

uv run python -c "import requests; print(requests.post('https://bsky.social/xrpc/com.atproto.server.createSession', json={'identifier':'x','password':'x'}).status_code)"

# this fails (403 HTML from awselb):
uv run python -c "import httpx; print(httpx.post('https://bsky.social/xrpc/com.atproto.server.createSession', json={'identifier':'x','password':'x'}).status_code)"
```

If `curl` and `requests` get 401 but `httpx` gets 403, this is the bug.

## Fix: route atproto through `curl_cffi`

`curl_cffi` impersonates a real browser's TLS fingerprint and gets through
the WAF. `atproto` exposes a `Client(request=...)` extension point
(MarshalX/atproto #594), so this is a clean plug-in — no monkey-patching.

### 1. Add the dependency

`curl-cffi>=0.15.0`. For a PEP 723 script, also add it to the inline
`# /// script` header.

### 2. Create `atproto_tls_shim.py` (or whatever you want to call it)

```python
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
  2. Drop the matching import + workaround block in the calling module.
  3. Replace ``make_client()`` callsites with ``Client()``.
  4. Drop ``curl-cffi`` from the dependency list.
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
```

### 3. Use it at the `Client()` call sites

In the calling module:

```python
# === TLS-fingerprint workaround (remove when MarshalX/atproto is fixed) ===
# See atproto_tls_shim.py for context and removal steps.
from atproto_tls_shim import make_client  # noqa: E402
# === end workaround ======================================================
```

Replace every `client = Client()` with `client = make_client()`. If the
module has a `try: from atproto import Client` availability check whose
only purpose was the now-unused `Client(...)` call, slap a `# noqa: F401`
on the import (keeps the friendly ImportError UX, satisfies ruff).

For async code: the same pattern applies with `AsyncRequest` /
`AsyncClient`, and `curl_cffi.requests.AsyncSession`. Not included here —
add if your project needs it.

## Why a shim and not direct `requests` calls

The atproto SDK does a lot of work besides HTTP: lexicon validation,
model (de)serialization, session refresh, namespacing, async support.
Hand-rolling the XRPC calls means giving all that up. The shim keeps
the SDK and only swaps the transport.

## Notes on the `content=` vs `data=` translation

`atproto` 0.0.65 (and httpx ≥ 0.27) use `content=` as the kwarg for raw
request bodies (bytes or str). `curl_cffi.requests.Session.request()`
uses `data=`. The shim translates one to the other. If pinned to an
older atproto where `data=` was already the body kwarg, the translation
is a no-op.

## Other transport quirks (not handled by the minimal shim)

- `_handle_request_errors()` in `atproto_client.request` maps
  `httpx.TimeoutException` and `httpx.NetworkError` to
  `exceptions.InvokeTimeoutError` / `exceptions.NetworkError`. With
  `curl_cffi` those raise `curl_cffi.curl.CurlError` instead, which won't
  be wrapped. If your code catches those specific exceptions, add a
  translator.
- `clone()` on `CurlCffiRequest` (inherited from `Request`) will
  `type(self)()` a new instance with default impersonation. Fine for
  default use; override `clone()` if you need to preserve a non-default
  impersonate value.

## Filing upstream

When you have a moment, file at https://github.com/MarshalX/atproto/issues
with: the symptom, the `curl`/`requests` vs `httpx` reproducer above,
and a note that `Client(request=CurlCffiRequest())` is the current
workaround. The fix on their side is either switching transports or
exposing a documented hook to do so without subclassing private classes.
