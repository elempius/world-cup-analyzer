import httpx
import pytest
from unittest.mock import patch

from api.football import FINISHED_STATUSES, FootballAPI, FootballAPIError
from api.models import Team, WCFixture

REQ = httpx.Request("GET", "https://v3.football.api-sports.io/teams")
OK_RESP = httpx.Response(
    200,
    json={"errors": [], "response": [{"team": {"id": 1, "name": "X", "code": "X"}}]},
    request=REQ,
)
ERR_RESP = httpx.Response(
    200,
    json={"errors": {"rateLimit": "Too many requests"}, "response": []},
    request=REQ,
)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return FootballAPI("fake-key")


def test_plan_error_raises_immediately(api):
    plan_err = httpx.Response(
        200,
        json={"errors": {"plan": "This endpoint is not available on your plan"}, "response": []},
        request=REQ,
    )
    with patch.object(api.client, "get", return_value=plan_err) as mock_get:
        with pytest.raises(FootballAPIError, match="plan"):
            api._get("/teams", {"search": "x"}, "teams")
    assert mock_get.call_count == 1  # not worth retrying


def test_rate_limit_retried_then_raises(api):
    with patch.object(api.client, "get", return_value=ERR_RESP) as mock_get, \
         patch("api.football.time.sleep"):
        with pytest.raises(FootballAPIError, match="rateLimit"):
            api._get("/teams", {"search": "x"}, "teams")
    assert mock_get.call_count == 3


def test_rate_limit_recovers_on_retry(api):
    with patch.object(api.client, "get", side_effect=[ERR_RESP, OK_RESP]), \
         patch("api.football.time.sleep"):
        result = api._get("/teams", {"search": "x"}, "teams")
    assert result[0]["team"]["name"] == "X"


def test_in_band_error_not_cached(api):
    with patch.object(api.client, "get", return_value=ERR_RESP), \
         patch("api.football.time.sleep"):
        with pytest.raises(FootballAPIError):
            api._get("/teams", {"search": "x"}, "teams")
    # next call with a healthy response must not be shadowed by a cached error
    with patch.object(api.client, "get", return_value=OK_RESP):
        result = api._get("/teams", {"search": "x"}, "teams")
    assert result[0]["team"]["name"] == "X"


def test_success_is_cached(api):
    with patch.object(api.client, "get", return_value=OK_RESP) as mock_get:
        api._get("/teams", {"search": "x"}, "teams")
        api._get("/teams", {"search": "x"}, "teams")
    assert mock_get.call_count == 1


def test_retries_transient_errors(api):
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectTimeout("boom")
        return OK_RESP

    with patch.object(api.client, "get", side_effect=flaky), patch("api.football.time.sleep"):
        result = api._fetch("/teams", {"search": "x"})
    assert calls["n"] == 2
    assert result[0]["team"]["id"] == 1


def test_exhausted_retries_raise(api):
    with patch.object(api.client, "get", side_effect=httpx.ConnectTimeout("boom")), \
         patch("api.football.time.sleep"):
        with pytest.raises(FootballAPIError, match="after 3 attempts"):
            api._fetch("/teams", {"search": "x"})


def _fx(fid: int, date: str, status: str) -> WCFixture:
    return WCFixture(
        fixture_id=fid, date=date, round="", venue="",
        home_team=Team(id=1, name="A"), away_team=Team(id=2, name="B"),
        status=status,
    )


def test_find_wc_fixture_prefers_nearest_unplayed(api):
    fixtures = [
        _fx(300, "2026-07-25T00:00:00+00:00", "NS"),
        _fx(100, "2026-06-15T00:00:00+00:00", "FT"),
        _fx(200, "2026-07-19T00:00:00+00:00", "NS"),
    ]
    with patch.object(api, "get_wc_fixtures", return_value=fixtures):
        assert api.find_wc_fixture(1, 2).fixture_id == 200
        assert api.find_wc_fixture(2, 1).fixture_id == 200  # order-insensitive


def test_find_wc_fixture_all_played_returns_most_recent(api):
    fixtures = [
        _fx(100, "2026-06-15T00:00:00+00:00", "FT"),
        _fx(101, "2026-07-01T00:00:00+00:00", "AET"),
    ]
    with patch.object(api, "get_wc_fixtures", return_value=fixtures):
        assert api.find_wc_fixture(1, 2).fixture_id == 101


def test_find_wc_fixture_no_match(api):
    with patch.object(api, "get_wc_fixtures", return_value=[_fx(1, "2026-06-15", "NS")]):
        assert api.find_wc_fixture(7, 8) is None


def test_finished_statuses_cover_knockout_outcomes():
    assert {"FT", "AET", "PEN"} <= FINISHED_STATUSES
