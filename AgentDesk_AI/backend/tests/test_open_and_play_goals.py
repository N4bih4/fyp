"""Goals: "open my seven semester folder" (any drive), "play Doraemon / Guzarish bajao" (YouTube), Roman Urdu."""
from app.nlu.local_matcher import match
from app.tools.filesystem import find_path_candidates


def test_spelled_and_ordinal_numbers_find_the_same_folder(tmp_path):
    (tmp_path / "Uni" / "7th Semester" / "FYP").mkdir(parents=True)
    for spoken in ("seven semester", "7 semester", "seventh semester"):
        found = find_path_candidates(spoken, [tmp_path])["candidates"]
        assert found == [str(tmp_path / "Uni" / "7th Semester")], spoken


def test_search_visits_shallow_folders_of_every_root_first(tmp_path):
    a, b = tmp_path / "C", tmp_path / "E"
    (a / "x" / "y").mkdir(parents=True)
    (b / "FYP").mkdir(parents=True)
    assert find_path_candidates("fyp", [a, b])["candidates"] == [str(b / "FYP")]


def _tool_and_arg(text):
    result = match(text)
    steps = result.plan.steps if result.plan else []
    return [(s.tool, s.args) for s in steps]


def test_named_song_or_video_is_a_youtube_play():
    for text, query in (("play doraemon", "doraemon"), ("play song guzarish", "guzarish"),
                        ("guzarish bajao", "guzarish"), ("doraemon play karo", "doraemon"),
                        ("guzarish gana chalao", "guzarish")):
        steps = _tool_and_arg(text)
        assert steps and steps[0][0] == "play_youtube_video", text
        assert steps[0][1]["query"].casefold() == query, text


def test_generic_music_commands_stay_media_keys():
    for text in ("agla gaana chalao", "gaana chalao"):
        steps = _tool_and_arg(text)
        assert not steps or steps[0][0] != "play_youtube_video", text
