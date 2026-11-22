import json

from app.tools import browser_profiles as bp

STATE = {"profile": {"info_cache": {
    "Default": {"name": "CH Zain", "gaia_name": "", "user_name": ""},
    "Profile 3": {"name": "Muhammad Zain", "gaia_name": "Muhammad Zain", "user_name": "zain@example.com"},
    "Profile 5": {"name": "Muhammad Zain", "gaia_name": "", "user_name": ""},
    "Profile 7": {"name": "Work", "gaia_name": "", "user_name": ""},
    "Profile 8": {"name": "Mary", "gaia_name": "", "user_name": ""}}}}


def profiles(tmp_path):
    (tmp_path / "Local State").write_text(json.dumps(STATE), encoding="utf-8")
    return bp.list_profiles("chrome", tmp_path)


def test_profiles_are_read_from_local_state(tmp_path):
    assert [p["dir"] for p in profiles(tmp_path)] == ["Default", "Profile 3", "Profile 5", "Profile 7", "Profile 8"]
    assert bp.list_profiles("chrome", tmp_path / "missing") == []


def test_a_clear_name_picks_one_profile(tmp_path):
    ps = profiles(tmp_path)
    assert bp.match_profile(ps, "work")[0]["dir"] == "Profile 7"
    assert bp.match_profile(ps, "Mary profile")[0]["dir"] == "Profile 8"
    assert bp.match_profile(ps, "profile 7")[0]["dir"] == "Profile 7"
    assert bp.match_profile(ps, "maryy")[0]["dir"] == "Profile 8"          # a small mishearing


def test_two_profiles_with_one_name_are_asked_not_guessed(tmp_path):
    chosen, candidates = bp.match_profile(profiles(tmp_path), "muhammad zain")
    assert chosen is None and {c["dir"] for c in candidates} == {"Profile 3", "Profile 5"}


def test_an_unknown_name_matches_nothing(tmp_path):
    assert bp.match_profile(profiles(tmp_path), "banana") == (None, [])
