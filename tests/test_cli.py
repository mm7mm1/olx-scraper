from contextlib import nullcontext
from pathlib import Path

import pytest

from olx_scraper import cli
from tests import kit


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "olx.sqlite3"


def run(monkeypatch: pytest.MonkeyPatch, olx: kit.Olx, *argv: str) -> int:
    monkeypatch.setattr(cli, "open_browser", lambda: nullcontext(olx))
    monkeypatch.setattr("olx_scraper.fetch.INTERVAL_S", 0.0)
    monkeypatch.setattr("signal.signal", lambda *_: None)
    return cli.main(list(argv))


def test_exit_codes(monkeypatch: pytest.MonkeyPatch, db: Path) -> None:
    scrape = ("scrape", "--db", str(db))
    assert run(monkeypatch, kit.Olx([kit.search_html([1])]), *scrape) == 0
    assert run(monkeypatch, kit.Olx([kit.search_html([])]), *scrape) == 1


def test_export_before_scrape_fails_without_creating_a_database(db: Path) -> None:
    assert cli.main(["export", "listings", "--csv", "x.csv", "--db", str(db)]) == 1
    assert not db.exists()


def test_failed_run_does_not_replace_the_exported_one(
    monkeypatch: pytest.MonkeyPatch, db: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.csv"
    run(monkeypatch, kit.Olx([kit.search_html([1, 2])]), "scrape", "--db", str(db))
    run(monkeypatch, kit.Olx([kit.search_html([3])], {3: 403}), "scrape", "--db", str(db))
    assert cli.main(["export", "listings", "--csv", str(out), "--db", str(db)]) == 0
    assert len(out.read_text("utf-8").splitlines()) == 1 + 2


@pytest.mark.parametrize(
    "bad", [["--pages", "0"], ["--limit", "-1"], ["--category", "uk/search/?q=x"]]
)
def test_bad_arguments(bad: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["scrape", *bad])
