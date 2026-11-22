import pytest

from app.agents.splitter import split_command


@pytest.mark.parametrize("text,expected", [
    ("open notepad and open calculator and take a screenshot", ["open notepad", "open calculator", "take a screenshot"]),
    ("notepad aur calculator kholo", ["notepad kholo", "calculator kholo"]),
    ("open notepad and calculator", ["open notepad", "open calculator"]),
    ("youtube kholo aur volume kam karo", ["youtube kholo", "volume kam karo"]),
    ("open youtube and then play a song", ["open youtube and then play a song"]),
    ("youtube kholo phir gana chalao", ["youtube kholo phir gana chalao"]),
    ("write an email to Ali saying we are free and happy", ["write an email to Ali saying we are free and happy"]),
    ("play music", ["play music"]),
    ("mute the video, take a screenshot", ["mute the video", "take a screenshot"]),
    ("یوٹیوب کھولو اور گانا چلاؤ", ["یوٹیوب کھولو اور گانا چلاؤ"]),
])
def test_split(text, expected):
    assert split_command(text) == expected


def test_a_part_that_points_back_stays_with_the_part_before():
    assert split_command("notepad kholo and close it") == ["notepad kholo and close it"]
    assert split_command("open notepad and close that") == ["open notepad and close that"]
