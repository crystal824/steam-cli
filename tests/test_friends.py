import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steam_cli.commands.friends import _profile_detail_lines


def test_profile_detail_lines_reads_correct_field_names():
    player = {
        "personaname": "tester",
        "realname": "Test Person",
        "loccountrycode": "US",
        "locstatecode": "CA",
        "loccityid": 12345,
    }
    lines = _profile_detail_lines(player)
    assert ("Real name", "Test Person") in lines
    assert ("Country", "US") in lines
    assert ("State", "CA") in lines
    assert ("City", "12345") in lines


def test_profile_detail_lines_ignores_old_incorrect_field_names():
    # Regression: the code used to read "locacountryid"/"locastateid"/
    # "locacityid", which GetPlayerSummaries never actually returns, so
    # Country/State/City silently never printed.
    player = {"locacountryid": "US", "locastateid": "CA", "locacityid": 12345}
    assert _profile_detail_lines(player) == []


def test_profile_detail_lines_omits_absent_fields():
    assert _profile_detail_lines({"personaname": "tester"}) == []
