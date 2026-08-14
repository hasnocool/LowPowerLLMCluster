from __future__ import annotations

import aiohttp

from .http_runtime import AsyncHttpClient


class ResilientAsyncHttpClient(AsyncHttpClient):
    """HTTP client with bounded larger header parsing for legitimate vendor sites.

    aiohttp defaults to 8 KiB header fields. Some manufacturer/CDN responses exceed
    that while remaining otherwise valid. Keep a conservative 64 KiB ceiling rather
    than disabling validation or allowing unbounded headers.
    """

    def __init__(self, *args, max_line_size: int = 65536, max_field_size: int = 65536, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.max_line_size = max(8190, min(131072, int(max_line_size)))
        self.max_field_size = max(8190, min(131072, int(max_field_size)))

    async def start(self) -> None:
        if self._session is not None and not self._session.closed:
            return
        connector = aiohttp.TCPConnector(
            limit=self.concurrency,
            limit_per_host=self.per_host,
            ttl_dns_cache=600,
            keepalive_timeout=60.0,
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_s, connect=min(self.timeout_s, 10.0))
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            },
            auto_decompress=True,
            max_line_size=self.max_line_size,
            max_field_size=self.max_field_size,
        )

    def metrics(self):
        value = super().metrics()
        value["max_line_size"] = self.max_line_size
        value["max_field_size"] = self.max_field_size
        return value
