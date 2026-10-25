import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scrapy.downloadermiddlewares.retry import RetryMiddleware


logger = logging.getLogger(__name__)


class RateLimitMiddleware(RetryMiddleware):
    def __init__(self, settings):
        super().__init__(settings)
        self.min_delay = settings.getint("RATE_LIMIT_MIN_DELAY", 1)
        self.max_delay = settings.getint("RATE_LIMIT_MAX_DELAY", 5)
        self.backoff = settings.getfloat("RATE_LIMIT_BACKOFF", 30)
        self.max_backoff = settings.getfloat("RATE_LIMIT_MAX_BACKOFF", 60)
        if not 1 <= self.min_delay <= self.max_delay:
            raise ValueError("Rate limit delays must satisfy 1 <= min <= max")
        if min(self.backoff, self.max_backoff) <= 0:
            raise ValueError("Rate limit settings must be positive")
        self.next_request_at = 0
        self.rate_limit_count = 0
        self.lock = asyncio.Lock()

    async def process_request(self, request):
        async with self.lock:
            await asyncio.sleep(random.randint(self.min_delay, self.max_delay))
            while (delay := self.next_request_at - time.monotonic()) > 0:
                await asyncio.sleep(delay)

    @staticmethod
    def retry_after(response):
        value = response.headers.get("Retry-After")
        if not value:
            return 0
        value = value.decode("ascii", errors="replace").strip()
        try:
            return max(0, int(value))
        except ValueError:
            try:
                deadline = parsedate_to_datetime(value)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                return max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                return 0

    def process_response(self, request, response):
        if response.status == 429:
            self.rate_limit_count += 1
            server_delay = self.retry_after(response)
            delay = min(
                self.max_backoff,
                max(server_delay, self.backoff * 2 ** min(self.rate_limit_count - 1, 20)),
            )
            self.next_request_at = max(self.next_request_at, time.monotonic() + delay)
            self.crawler.stats.inc_value("rate_limit/responses")
            logger.warning(
                "HTTP 429: pausing for %.1fs (Retry-After: %.1fs, cap: %.1fs)",
                delay, server_delay, self.max_backoff,
            )
        elif 200 <= response.status < 300:
            self.rate_limit_count = 0
        return super().process_response(request, response)
