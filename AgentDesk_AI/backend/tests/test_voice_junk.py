import pytest

from app.voice.junk import junk_reason


@pytest.mark.parametrize("text", [".", "Ffff!", "Danke.", "Thanks for watching!", "Haa, yuk, yuk, yuk, yuk, yuk", "", "...", "mm"])
def test_noise_is_rejected(text):
    assert junk_reason(text)


@pytest.mark.parametrize("text", ["open notepad", "youtube pe gana chala do", "pause", "volume 50", "نوٹ پیڈ کھولو", "yes", "no", "stop", "kholo"])
def test_commands_are_kept(text):
    assert junk_reason(text) is None


def test_whisper_doubt_rejects_but_confident_speech_passes():
    assert junk_reason("play music", no_speech_prob=0.9, avg_logprob=-1.0)
    assert junk_reason("play music", compression_ratio=3.1)
    assert junk_reason("play music", no_speech_prob=0.05, avg_logprob=-0.3, compression_ratio=1.2) is None


def test_answers_are_written_in_latin_letters_for_hindi_and_urdu_speech(monkeypatch):
    from app.config import get_settings
    from app.voice.reply_script import reply_lang
    assert reply_lang("hi") == "roman_ur" and reply_lang("ur") == "roman_ur" and reply_lang("en") == "en" and reply_lang("roman_ur") == "roman_ur"
    monkeypatch.setattr(get_settings(), "reply_script", "native")
    assert reply_lang("hi") == "hi" and reply_lang("ur") == "ur"


def test_the_noise_heard_in_the_live_session_is_junk():
    from app.voice.junk import junk_reason
    for text in ["Aduh!", "Thank you.", "Aduly-Subs.com", 'ms-screenclip="http://www.hamskey.com.au/.html', "Thanks.", "wow"]:
        assert junk_reason(text), text


def test_real_commands_and_answers_are_not_junk():
    from app.voice.junk import junk_reason
    for text in ["open youtube.com", "haan", "yes", "ok", "C drive ko open karo", "go to www.example.com", "Firefox kholo"]:
        assert junk_reason(text) is None, text


def test_words_in_a_script_nobody_here_speaks_are_junk_but_urdu_and_hindi_are_not():
    from app.voice.junk import junk_reason
    assert junk_reason("Админиферентисы, тушетон")
    assert junk_reason("ご視聴ありがとう")
    assert junk_reason("کروم کھولو") is None and junk_reason("क्रोम खोलो") is None


def test_a_sentence_in_a_language_nobody_speaks_to_the_assistant_is_junk():
    from app.voice.junk import junk_reason
    assert junk_reason("Buongiorno a tutti, sono Attilio", language="italian")
    assert junk_reason("KFC gov so", language="somali")
    assert junk_reason("chrome kholo", language="english") is None
    assert junk_reason("chrome kholo", language="Urdu") is None
    assert junk_reason("chrome kholo", language=None) is None
