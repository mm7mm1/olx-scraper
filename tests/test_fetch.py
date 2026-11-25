import pytest

from olx_scraper.fetch import (
    BlockedError,
    Client,
    GoneError,
    NetworkError,
    Reply,
    UnavailableError,
)


class Server:
    def __init__(self, *answers: Reply | Exception) -> None:
        self.answers = list(answers)
        self.calls = 0
        self.slept: list[float] = []
        self.client = Client(self, sleep=self.slept.append, clock=lambda: 0.0)

    def get(self, url: str) -> Reply:
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_requests_are_paced() -> None:
    server = Server(Reply(200, "a"), Reply(200, "b"))
    assert server.client.get("/1") + server.client.get("/2") == "ab"
    assert server.slept == [1.0]


def test_temporary_errors_are_retried() -> None:
    server = Server(NetworkError("down"), Reply(502), Reply(200, "ok"))
    assert server.client.get("/") == "ok"
    assert server.calls == 3


def test_retries_end() -> None:
    server = Server(*[Reply(500)] * 3)
    with pytest.raises(UnavailableError, match="HTTP 500 after 3 attempts"):
        server.client.get("/")


@pytest.mark.parametrize("code", [401, 403])
def test_refusal_is_not_retried(code: int) -> None:
    server = Server(Reply(code))
    with pytest.raises(BlockedError):
        server.client.get("/")
    assert server.calls == 1


def test_retry_after_is_respected() -> None:
    server = Server(Reply(429, retry_after="17"), Reply(200, "ok"))
    assert server.client.get("/") == "ok"
    assert 17.0 in server.slept


def test_long_retry_after_stops_at_once() -> None:
    server = Server(Reply(429, retry_after="3600"))
    with pytest.raises(BlockedError, match="3600"):
        server.client.get("/")
    assert server.calls == 1


def test_repeated_429_is_a_block() -> None:
    server = Server(*[Reply(429)] * 3)
    with pytest.raises(BlockedError):
        server.client.get("/")


@pytest.mark.parametrize("code", [301, 404, 410])
def test_missing_or_moved_page_is_gone(code: int) -> None:
    server = Server(Reply(code))
    with pytest.raises(GoneError):
        server.client.get("/")
    assert server.calls == 1
