"""Paced page reads. Slows down when asked to and stops when refused."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

INTERVAL_S = 1.0  # between request starts; one polite reader, so no concurrency
ATTEMPTS = 3
MAX_RETRY_AFTER_S = 120.0


class GoneError(Exception):
    """This one page is not available: removed, moved or not found."""


class UnavailableError(Exception):
    """The page could not be read after retries."""


class BlockedError(Exception):
    """OLX refused us. The run must stop, not work around it."""


class NetworkError(Exception):
    """No answer at all; worth another attempt."""


@dataclass(frozen=True, slots=True)
class Reply:
    status: int
    text: str = ""
    retry_after: str = ""


class Transport(Protocol):
    def get(self, url: str) -> Reply:
        """Raises NetworkError. A redirect must come back as its own 3xx status."""


class Client:
    def __init__(
        self,
        transport: Transport,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._next_start = 0.0

    def get(self, url: str) -> str:
        reason = ""
        for attempt in range(1, ATTEMPTS + 1):
            if attempt > 1:
                self._sleep(2.0**attempt)
            self._pace()
            try:
                reply = self._transport.get(url)
            except NetworkError as error:
                reason = f"network: {error}"
                continue
            if reply.status == 429:
                self._wait_as_told(reply)
            elif reply.status < 500:
                return _body(reply)
            reason = f"HTTP {reply.status}"
        failure = f"{reason} after {ATTEMPTS} attempts"
        raise BlockedError(failure) if reason == "HTTP 429" else UnavailableError(failure)

    def _pace(self) -> None:
        wait = self._next_start - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._next_start = self._clock() + INTERVAL_S

    def _wait_as_told(self, reply: Reply) -> None:
        if not reply.retry_after.isdecimal():
            return
        seconds = float(reply.retry_after)
        if seconds > MAX_RETRY_AFTER_S:
            raise BlockedError(f"HTTP 429, Retry-After {reply.retry_after} s")
        self._sleep(seconds)


def _body(reply: Reply) -> str:
    if reply.status in (401, 403):
        raise BlockedError(f"HTTP {reply.status}")
    if reply.status != 200:
        raise GoneError(f"HTTP {reply.status}")
    return reply.text
