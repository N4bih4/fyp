"""Local commands for exact tabs and explicit YouTube media state."""
import re
import unicodedata
from .base import Plan, PlanAction
from .speech_commands import normalize_speech, NEGATIONS
from .command_language import END, LINK, OPEN

TAB = r"(?:tab|ٹیب|टैब)"
CLOSE = r"(?:close|off|band|بند|کلوز|اف|آف|बंद|क्लोज|ऑफ)"
SITES = {"یوٹیوب": "youtube", "यूट्यूब": "youtube", "گوگل ڈرائیو": "google drive", "गूगल ड्राइव": "google drive",
         "واٹس ایپ": "whatsapp", "व्हाट्सएप": "whatsapp", "جی میل": "gmail", "जीमेल": "gmail",
         "اوپن اے آئی": "openai", "ओपन एआई": "openai", "چیٹ جی پی ٹی": "chatgpt", "चैट जीपीटी": "chatgpt"}


def tab_target(value):
    """Remove only recognized spoken descriptors around one known site.

    Keep meaningful unknown title words intact; never reduce 'YouTube lecture'
    or a request naming two sites to an arbitrary website close.
    """
    raw = value.strip()
    aliases = {**{name: name for name in SITES.values()}, **SITES}
    names = "|".join(re.escape(name) for name in sorted(aliases, key=len, reverse=True))
    matches = list(re.finditer(rf"(?<!\w)({names})(?!\w)", raw, re.I))
    if len(matches) != 1:
        return raw
    match = matches[0]
    remaining = normalize_speech(raw[:match.start()] + " " + raw[match.end():]).split()
    descriptors = set("the my that this one tab browser chrome google edge in on is opened open which was it wala wali woh wo jo ka ki ke mein me par khula khuli khuli hui hua hai hui hay کروم گوگل ایج براؤزر میں پر کھلا کھلی کلی ہوا ہوئی ہے ہیں وہ والا والی جو یہ کا کی کے ٹیب क्रोम गूगल एज ब्राउज़र में पर खुला खुली हुआ हुई है वह वाला वाली जो यह का की के टैब".split())
    if all(word in descriptors for word in remaining):
        return aliases[match.group(1).casefold()]
    return raw


_ORDINALS = {"first": 1, "1st": 1, "pehli": 1, "pehla": 1, "second": 2, "2nd": 2, "doosri": 2, "doosra": 2, "dusri": 2, "third": 3, "3rd": 3, "teesri": 3,
             "teesra": 3, "fourth": 4, "4th": 4, "chauthi": 4, "fifth": 5, "5th": 5, "paanchvi": 5, "sixth": 6, "6th": 6, "seventh": 7, "7th": 7,
             "eighth": 8, "8th": 8, "ninth": 9, "9th": 9, "tenth": 10, "10th": 10}
_NUM = r"(\d{1,4}(?:\.\d+)?)"
_SITE_WORDS = {"youtube": "youtube", "gmail": "gmail", "whatsapp": "whatsapp", "google drive": "google drive", "drive": "google drive", "chatgpt": "chatgpt", "openai": "openai"}


def _bc(action, **args):
    return Plan(actions=[PlanAction(tool="control_browser", args={"action": action, "target": "youtube", **args})])


def youtube_player_plan(raw):
    """Spoken controls for the YouTube tab that is open: skip / rewind, speed, full screen, next video, volume, mute, results, scroll.

    Each one needs a number or an explicit word (video, youtube, seconds) so it can never be confused with a system command:
    "volume down" is the PC's volume, "youtube volume 40" is the player's; "go back" is left alone, "go back 10 seconds" rewinds.
    """
    text = re.sub(r"\s+", " ", re.sub(r"[,!?\u06d4\u0964]", " ", unicodedata.normalize("NFKC", raw).casefold())).strip()   # keeps the "." of 1.5
    m = re.fullmatch(rf"(?:please )?(?:skip|forward|fast forward|go forward|jump ahead|jump forward|aage)(?: by)? {_NUM} ?(seconds?|secs?|s|minutes?|mins?)?(?: forward| ahead)?", text)
    if m:
        n = float(m.group(1)) * (60 if (m.group(2) or "").startswith("min") else 1)
        return _bc("seek", seconds=int(n))
    m = re.fullmatch(rf"(?:please )?(?:rewind|skip back|skip backward|jump back|go back|back|replay)(?: by)? {_NUM} ?(seconds?|secs?|s|minutes?|mins?)", text) or \
        re.fullmatch(rf"(?:please )?rewind(?: by)? {_NUM}", text)
    if m:
        unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
        return _bc("seek", seconds=-int(float(m.group(1)) * (60 if (unit or "").startswith("min") else 1)))
    m = re.fullmatch(rf"{_NUM} ?(?:seconds?|secs?|second|sec) ?(aage|agay|forward|ahead)(?: karo| kar do| kardo)?", text)
    if m:
        return _bc("seek", seconds=int(float(m.group(1))))
    m = re.fullmatch(rf"{_NUM} ?(?:seconds?|secs?|second|sec) ?(peeche|pichhe|piche|back)(?: karo| kar do| kardo)?", text)
    if m:
        return _bc("seek", seconds=-int(float(m.group(1))))
    m = re.fullmatch(rf"(?:set |change |make |video |youtube )?(?:playback )?speed(?: to)? {_NUM} ?x?", text) or re.fullmatch(rf"{_NUM} ?x speed", text) \
        or re.fullmatch(rf"(?:play|run) (?:it |the video )?at {_NUM} ?x", text)
    if m:
        rate = float(m.group(1))
        if 0.25 <= rate <= 4:
            return _bc("speed", rate=rate)
    if re.fullmatch(r"(?:normal|regular) (?:playback )?speed|speed (?:normal|reset)", text):
        return _bc("speed", rate=1.0)
    if re.fullmatch(r"(?:go |make it |turn on |enter |video |youtube )?full ?screen(?: mode)?(?: (?:video|on))?|fullscreen kar do|full screen karo", text):
        return _bc("fullscreen")
    if re.fullmatch(r"(?:exit|leave|close|stop|turn off) full ?screen(?: mode)?", text):
        return _bc("fullscreen", exit=True)
    if re.fullmatch(r"(?:play |go to )?(?:the )?next video|agli video(?: chalao| chala do)?|next video chalao", text):
        return _bc("next")
    m = re.fullmatch(r"(?:youtube|video|player) volume(?: to)? (\d{1,3}) ?(?:percent|%)?", text) or re.fullmatch(r"(?:set )?(?:youtube|video|player) volume (?:to )?(\d{1,3}) ?(?:percent|%)?", text)
    if m and int(m.group(1)) <= 100:
        return _bc("volume", level=int(m.group(1)))
    if re.fullmatch(r"mute (?:the )?(?:video|youtube|player)|(?:video|youtube) (?:ko )?mute (?:karo|kar do)", text):
        return _bc("mute")
    if re.fullmatch(r"unmute (?:the )?(?:video|youtube|player)|(?:video|youtube) (?:ko )?unmute (?:karo|kar do)", text):
        return _bc("unmute")
    m = re.fullmatch(r"(?:play|open|click|choose|select|pick) (?:youtube )?(?:result|video|number|item) (?:number )?(\d{1,2})", text)
    if m and 1 <= int(m.group(1)) <= 20:
        return _bc("click_result", index=int(m.group(1)))
    if re.fullmatch(r"(?:read|list|what are|show) (?:me )?(?:the )?(?:youtube |video |search )?results", text):
        return _bc("results")
    m = re.fullmatch(r"(?:youtube )?scroll (down|up)(?: on youtube| the video page)?|scroll (down|up) youtube", text)
    if m and ("youtube" in text):
        return _bc("scroll", amount=1 if "down" in text else -1)
    m = re.fullmatch(r"switch to (?:the )?(youtube|gmail|whatsapp|google drive|drive|chatgpt|openai)(?: tab)?|(youtube|gmail|whatsapp|google drive|drive|chatgpt|openai) (?:tab )?(?:par|pe) jao", text)
    if m:
        return Plan(actions=[PlanAction(tool="control_browser", args={"action": "switch", "target": _SITE_WORDS[(m.group(1) or m.group(2))]})])
    if re.fullmatch(r"(?:what(?:'s| is) )?(?:the )?(?:page|tab) title|read (?:me )?(?:the )?(?:page |tab )?title|what page is this|is page ka naam kya hai", text):
        return Plan(actions=[PlanAction(tool="control_browser", args={"action": "read", "target": "active"})])
    return youtube_extra_plan(text) or web_page_plan(text, raw)


_QUALITY = {"144": "tiny", "240": "small", "360": "medium", "480": "large", "720": "hd720", "1080": "hd1080", "1440": "hd1440", "2160": "hd2160", "4k": "hd2160"}


def youtube_extra_plan(text):
    """previous video, theatre, captions, quality, loop, skip the ad, like, subscribe, what is playing. Each names the video / youtube / a clear word."""
    if re.fullmatch(r"(?:play |go to )?(?:the )?(?:previous|last) video|pichli video(?: chalao| chala do)?|previous video chalao", text):
        return _bc("previous")
    m = re.fullmatch(r"(?:turn |switch |put )?(on|off)? ?theat(?:re|er) mode(?: (on|off))?", text) or re.fullmatch(r"(exit|leave) theat(?:re|er) mode", text)
    if m:
        word = next((g for g in m.groups() if g), "on")
        return _bc("theatre", enable=word not in ("off", "exit", "leave"))
    m = re.fullmatch(r"(?:turn |switch |put )?(on|off) (?:the )?(?:captions|subtitles|closed captions|cc)|(?:captions|subtitles|cc) (on|off)|(?:show|hide) (?:the )?(?:captions|subtitles)", text)
    if m:
        word = next((g for g in m.groups() if g), "")
        enable = word == "on" or (not word and text.startswith("show"))
        return _bc("captions", enable=enable)
    m = re.fullmatch(r"(?:set |change |make )?(?:the )?(?:video )?(?:quality|resolution)(?: to)? (auto|\d{3,4}p?|4k|automatic)|(auto|\d{3,4}p?|4k) quality", text) or \
        re.fullmatch(r"(?:play (?:it |the video )?in|switch to) (\d{3,4})p?(?: quality)?", text)
    if m:
        word = next((g for g in m.groups() if g), "auto").rstrip("p")
        level = "auto" if word in ("auto", "automatic") else _QUALITY.get(word)
        if level:
            return _bc("quality", quality=level)
    if re.fullmatch(r"(?:turn |switch )?(on|off)? ?(?:the )?(?:video )?loop(?: (?:this |the )?video)?(?: (on|off))?|(?:repeat|loop) (?:this|the) video", text):
        return _bc("loop", enable=not re.search(r"\boff\b", text))
    if re.fullmatch(r"skip (?:the )?(?:ad|ads|advert|advertisement)|ad skip karo|ad skip kar do", text):
        return _bc("skip_ad")
    if re.fullmatch(r"(?:like|thumbs up) (?:this |the )?(?:video|youtube video)|like (?:it|this)|video (?:ko )?like (?:karo|kar do)", text):
        return _bc("like")
    if re.fullmatch(r"subscribe(?: to)?(?: this| the)?(?: channel)?|channel (?:ko )?subscribe (?:karo|kar do)", text):
        return _bc("subscribe")
    if re.fullmatch(r"what(?:'s| is) (?:playing|this video|this song)(?: on youtube| now)?|which (?:song|video) is this|(?:yeh|ye) kaun sa (?:gana|video) hai|kya chal raha hai", text):
        return _bc("now_playing")
    return None


def _wc(action, **args):
    return Plan(actions=[PlanAction(tool="control_browser", args={"action": action, "target": "active", **args})])


def web_page_plan(text, raw=None):
    """The page in front (any website): read it, follow a link by its words, fill a named field, pick a search result, scroll, bookmarks, history, reopen a tab."""
    src = re.sub(r"\s+", " ", (raw or text).strip().rstrip("۔।.!?"))     # the original capitals: a fill keeps exactly what was said
    if re.fullmatch(r"read (?:me )?(?:this |the )?(?:web ?)?page|what(?:'s| is) on (?:this|the) page|read (?:the )?page aloud|is page ko parho", text):
        return _wc("read_page")
    m = re.fullmatch(r"(?:click|press|tap|open) (?:the )?(?:link|button) (?:called |named |that says |saying )?[\"']?(.{2,80}?)[\"']?", src, re.I)
    if m:
        return _wc("click_link", name=m.group(1).strip())
    m = re.fullmatch(r"(?:fill|type|enter|put) (.{1,300}?) (?:in|into) (?:the )?(.{2,60}?) (?:field|box|bar|input)", src, re.I)
    if m:
        return _wc("fill", field=m.group(2).strip(), text=m.group(1).strip().strip("\"'"))
    m = re.fullmatch(r"(?:fill|set) (?:the )?(.{2,60}?) (?:field|box|bar|input) (?:with|to) (.{1,300})", src, re.I)
    if m:
        return _wc("fill", field=m.group(1).strip(), text=m.group(2).strip().strip("\"'"))
    m = re.fullmatch(r"(?:open|click|go to|select) (?:search )?result (?:number )?(\d{1,2}) (?:on|in) (?:google|bing|duckduckgo|the search page)|(?:open|click) the (\w+) (?:google |bing )?(?:search )?result", text)
    if m:
        number = m.group(1) or str(_ORDINALS.get(m.group(2), ""))
        if number.isdigit() and 1 <= int(number) <= 20:
            return _wc("web_click_result", index=int(number))
    if re.fullmatch(r"(?:read|list|what are) (?:me )?(?:the )?(?:google|bing|duckduckgo|web|page) search results", text):
        return _wc("web_results")
    m = re.fullmatch(r"scroll (down|up) (?:the|this) (?:web ?)?page|scroll (?:the|this) (?:web ?)?page (down|up)", text)
    if m:
        return _wc("web_scroll", amount=1 if "down" in (m.group(1) or m.group(2)) else -1)
    m = re.fullmatch(r"(?:find|search|look for|open) (?:my )?bookmarks? (?:for |named |called |about )?(.{2,60})", text)
    if m:
        return _wc("bookmarks", query=m.group(1).strip())
    m = re.fullmatch(r"(?:open |find |search )?(?:the )?(?:page|site|website) (?:i had|i visited|from my history|i was on) (?:about |for |on )?(.{2,60})|search (?:my )?history for (.{2,60})", text)
    if m:
        return _wc("history", query=(m.group(1) or m.group(2)).strip())
    if re.fullmatch(r"reopen (?:the )?(?:last )?(?:closed )?tab|open (?:the )?(?:last )?closed tab again|undo close tab", text):
        return _wc("reopen")
    return None


def youtube_followup(raw, recent):
    """"play the second one" right after a YouTube search or result list: click that result. Needs the previous task to have been about YouTube
    search results; anything else ("the second one" after a file list) is left to the normal reference rules."""
    if recent is None or not getattr(recent, "actions", None):
        return None
    tools = {a.tool_name: a.args_json or "" for a in recent.actions}
    about_results = ("web_search" in tools and "youtube" in tools["web_search"].casefold()) or "play_youtube_video" in tools or \
        ("control_browser" in tools and any(w in tools["control_browser"] for w in ("results", "click_result")))
    if not about_results:
        return None
    text = normalize_speech(raw)
    m = re.fullmatch(r"(?:play|open|click|choose|select|pick|chalao|chala do)? ?(?:the )?([a-z0-9]+)(?: one| video| result| wali| wala| wali video)?(?: chalao| chala do| kholo)?", text)
    if m and m.group(1) in _ORDINALS:
        return _bc("click_result", index=_ORDINALS[m.group(1)])
    m = re.fullmatch(r"(?:play|open|click) (?:number|result|video) ?(\d{1,2})", text)
    if m:
        return _bc("click_result", index=int(m.group(1)))
    return None


_YT_WORDS = {"youtube", "یوٹیوب", "یو", "ٹیوب", "यूट्यूब", "यू", "ट्यूब", "yt"}
_SAME_TAB = {"ishi", "isi", "usi", "same", "this", "current", "existing", "already", "khuli", "khule", "khula", "اسی", "اسی", "इसी", "उसी", "खुले", "کھلے"}
_PAGE_WORDS = {"page", "tab", "ٹیب", "پیج", "صفحہ", "पेज", "टैब"}
_SEARCH_VERBS = {"search", "serch", "find", "dhoondo", "dhundo", "dhoond", "talash", "سرچ", "تلاش", "ڈھونڈو", "सर्च", "खोजो", "ढूंढो"}
_PLAY_VERBS = {"play", "chala", "chalao", "chalado", "chalade", "laga", "lagao", "sunao", "چلا", "چلاؤ", "چلادو", "پلے", "لگاؤ", "चला", "चलाओ", "प्ले", "लगाओ", "सुनाओ"}
_QUERY_FILLER = {"ab", "ke", "ki", "ka", "ko", "par", "pe", "oper", "upar", "ooper", "andar", "mein", "me", "karo", "kar", "do", "dena", "de", "please", "plz", "i", "say",
                 "you", "the", "on", "in", "a", "an", "and", "aur", "phir", "abhi", "tum", "ye", "yeh", "then", "now", "for", "to",
                 "اب", "کے", "کی", "کا", "کو", "پر", "پہ", "اوپر", "میں", "کرو", "کر", "دو", "تم", "یہ", "और", "अब", "के", "की", "का", "को", "पर", "ऊपर", "उपर", "में", "करो", "कर", "दो", "तुम", "ये"}


def youtube_tab_search_plan(raw):
    """"search / play X on this (already open) YouTube page": the open YouTube tab goes to the results (and plays the first one), never a Google search.
    Needs a YouTube word, a same-tab or page / tab word, and a search or play verb, so "play X on YouTube" keeps its own flow."""
    words = [w for w in re.split(r"[\s,.;:!?।۔،]+", raw.casefold()) if w]    # split on spaces, not \w: Devanagari vowel signs are not word characters
    if not (set(words) & _YT_WORDS) or not (set(words) & (_SAME_TAB | _PAGE_WORDS)):
        return None
    searching, playing = set(words) & _SEARCH_VERBS, set(words) & _PLAY_VERBS
    if not (searching or playing):
        return None
    drop = _YT_WORDS | _SAME_TAB | _PAGE_WORDS | _SEARCH_VERBS | _PLAY_VERBS | _QUERY_FILLER
    query = " ".join(w for w in words if w not in drop).strip()
    if len(query) < 2 or len(query) > 100:
        return None
    actions = [PlanAction(tool="control_browser", args={"action": "search", "target": "youtube", "query": query})]
    if playing:
        actions.append(PlanAction(tool="control_browser", args={"action": "click_result", "target": "youtube", "index": 1}))
    return Plan(actions=actions)


def browser_plan(command):
    raw = command.strip().rstrip("۔।!?")
    if any(word in NEGATIONS for word in normalize_speech(raw).split()):
        return None
    chrome = r"(?:chrome|google chrome|کروم|گوگل کروم|क्रोम|गूगल क्रोम)"
    inside = r"(?:in|ان|mein|میں|में|इन)"
    opened = re.fullmatch(rf"{OPEN}\s+(.+?)(?:\s+{inside}\s+({chrome}))?{END}", raw, re.I)
    if not opened:
        opened = re.fullmatch(rf"(.+?)\s+({chrome})\s+{inside}\s+{OPEN}{END}", raw, re.I)
    if opened:
        site = SITES.get(opened.group(1).strip().casefold(), opened.group(1).strip().casefold())
        urls = {"youtube": "https://www.youtube.com", "gmail": "https://mail.google.com", "google drive": "https://drive.google.com", "whatsapp": "https://web.whatsapp.com", "openai": "https://openai.com", "chatgpt": "https://chatgpt.com",
                "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com", "twitter": "https://twitter.com",
                "linkedin": "https://www.linkedin.com", "google": "https://www.google.com", "netflix": "https://www.netflix.com",
                "reddit": "https://www.reddit.com", "amazon": "https://www.amazon.com", "wikipedia": "https://www.wikipedia.org"}
        if site in urls:
            args = {"url": urls[site]}
            if opened.group(2):
                args["browser"] = "chrome"
            return Plan(actions=[PlanAction(tool="open_url", args=args)])
    # A named site's "off/close" refers to its tab, not the browser process.
    named = re.fullmatch(rf"(?:{CLOSE}\s+(.+?)|(.+?)\s+{CLOSE}){END}", raw, re.I)
    if named:
        target = (named.group(1) or named.group(2)).strip().casefold()
        target = SITES.get(target, target)
        if target in {"youtube", "gmail", "whatsapp", "google drive", "openai", "chatgpt"}:
            return Plan(actions=[PlanAction(tool="control_browser", args={"action": "close", "target": target})])
    patterns = [rf"(.+?){LINK}\s+{TAB}\s+{CLOSE}{END}",
                rf"{CLOSE}\s+(.+?){LINK}\s+{TAB}{END}",
                rf"{CLOSE}\s+{TAB}\s+(.+?){END}"]
    for pattern in patterns:
        match = re.fullmatch(pattern, raw, re.IGNORECASE)
        if match:
            target = re.sub(r"^the\s+", "", match.group(1).strip(), flags=re.IGNORECASE)
            args = {"action": "close", "target": tab_target(target)}
            if target.isdecimal():
                args["tab_id"] = int(target)
            return Plan(actions=[PlanAction(tool="control_browser", args=args)])
    player = youtube_player_plan(raw)
    if player is not None:
        return player
    in_tab = youtube_tab_search_plan(raw)
    if in_tab is not None:
        return in_tab
    text = normalize_speech(raw)
    tab_media = re.fullmatch(r"(pause|resume|play) (?:video in )?tab (\d+)", text)
    if tab_media:
        return Plan(actions=[PlanAction(tool="control_browser", args={"action": "pause" if tab_media.group(1) == "pause" else "resume", "target": "youtube", "tab_id": int(tab_media.group(2))})])
    if text in {"list tabs", "show tabs", "tabs dikhao", "ٹیب دکھاؤ"}:
        return Plan(actions=[PlanAction(tool="control_browser", args={"action": "inspect"})])
    aliases = {"ویڈیو": "video", "वीडियो": "video", "یوٹیوب": "youtube", "यूट्यूब": "youtube",
               "pause": "pause", "stop": "pause", "rok": "pause", "roko": "pause", "روک": "pause", "روکو": "pause", "پاز": "pause", "پوز": "pause", "रोक": "pause", "पॉज": "pause", "पॉज़": "pause",
               "resume": "resume", "play": "resume", "پلے": "resume", "chala": "resume", "chalao": "resume", "چلا": "resume", "چلاؤ": "resume", "چلادو": "resume", "चला": "resume", "चलाओ": "resume",
               "band": "pause", "بند": "pause", "बंद": "pause"}
    filler = {"the", "my", "meri", "mera", "ki", "ka", "ko", "par", "karo", "kar", "do", "please", "yeh", "this", "that", "یہ", "وہ", "ये", "इस", "کی", "کا", "کو", "پر", "کرو", "کر", "دو", "میری", "मेरा", "मेरी", "की", "का", "को", "पर", "कर", "करो", "दो"}
    words = [aliases.get(w, w) for w in text.split() if w not in filler]
    if words and set(words) <= {"youtube", "video", "pause", "resume"}:
        actions = set(words) & {"pause", "resume"}
        if len(actions) == 1 and ("youtube" in words or "video" in words):
            return Plan(actions=[PlanAction(tool="control_browser", args={"action": actions.pop(), "target": "youtube"})])
    named = [r"play (.+?) on youtube", r"(?:youtube|یوٹیوب|यूट्यूब) (?:par|پر|पर) (.+?) (?:chala do|چلا دو|चला दो)"]
    for pattern in named:
        match = re.fullmatch(pattern, raw, re.IGNORECASE)
        if match:
            return Plan(actions=[PlanAction(tool="play_youtube_video", args={"query": match.group(1)})])
    return None
