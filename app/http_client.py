import time

import httpx


DEFAULT_USER_AGENT = "Meowstreet/1.0"
BROWSER_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT_SECONDS = 30.0

BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Dnt": "1",
    "Sec-Gpc": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i",
    "Cache-Control": "max-age=0",
}


class HttpClient:
    def __init__(
        self, transport=None, sleep=time.sleep, default_timeout=30.0, max_attempts=3
    ):
        self._transport = transport
        self._sleep = sleep
        self._default_timeout = default_timeout
        self._max_attempts = max_attempts

    def request(
        self,
        method,
        url,
        *,
        params=None,
        data=None,
        json=None,
        headers=None,
        timeout=None,
        browser=False,
    ):
        if browser:
            merged_headers = dict(BROWSER_HEADERS)
            if headers:
                merged_headers.update(headers)
        else:
            merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
            if headers:
                merged_headers.update(headers)

        effective_timeout = timeout if timeout is not None else self._default_timeout

        last_exception = None
        for attempt in range(self._max_attempts):
            try:
                with httpx.Client(
                    transport=self._transport, follow_redirects=True
                ) as client:
                    response = client.request(
                        method,
                        url,
                        params=params,
                        data=data,
                        json=json,
                        headers=merged_headers,
                        timeout=effective_timeout,
                    )
                    response.read()
                    if response.status_code in (429,) or response.status_code >= 500:
                        if attempt < self._max_attempts - 1:
                            retry_after = _parse_retry_after(response)
                            if retry_after is None:
                                retry_after = 2.0**attempt
                            self._sleep(retry_after)
                            continue
                    response.raise_for_status()
                    return response
            except httpx.ReadTimeout as exc:
                last_exception = exc
                if attempt < self._max_attempts - 1:
                    self._sleep(2.0**attempt)
                continue
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                last_exception = exc
                if attempt < self._max_attempts - 1:
                    self._sleep(2.0**attempt)
                continue
        raise last_exception


def _parse_retry_after(response):
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        parsed = float(value)
        if parsed >= 0:
            return parsed
    except (ValueError, TypeError):
        pass
    return None
