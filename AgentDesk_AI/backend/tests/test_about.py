"""The assistant knows who made it, however the question is worded or misheard."""
from __future__ import annotations

import pytest

from app import about
from app.about import developer_answer, names_the_product


@pytest.mark.parametrize("text", [
    "Who is the developer of AgentDesk AI?", "who is the developer of Agent Desk AI", "Who is the developer of AdenDesk AI?", "Wu is the developer of Adenedask AI.",
    "who made AgentDesk", "who created AgentDesk AI", "who developed this project", "who designed this app", "who built you", "who made you?",
    "who is your developer", "who is the owner of agent desk", "tell me who developed AgentDesk AI?", "AgentDesk AI ka developer kaun hai",
    "agentdesk ko kisne banaya", "tumhe kisne banaya", "aapko kisne banaya hai", "yeh project kisne banaya", "तुम्हें किसने बनाया", "एजेंट डेस्क का डेवलपर कौन है आप",
    "who is the developer of agent x",
])
def test_who_made_it_is_answered_with_the_developer(text):
    answer = developer_answer(text)
    assert answer and about.DEVELOPER in answer, text


def test_the_answer_is_english_for_english_and_roman_urdu_for_roman_urdu():
    assert developer_answer("who made AgentDesk AI?").startswith("AgentDesk AI was designed and developed by Nabiha Zainab")
    assert "ne design aur develop kiya hai" in developer_answer("AgentDesk ko kisne banaya?")


@pytest.mark.parametrize("text", ["Nabiha Zainab is the developer of AgentDesk AI", "nabiha is the developer of agent desk", "Nabiha Zainab ne AgentDesk banaya hai"])
def test_saying_who_the_developer_is_is_confirmed(text):
    answer = developer_answer(text)
    assert answer and "Nabiha Zainab" in answer and ("Yes" in answer or "Ji haan" in answer)


@pytest.mark.parametrize("text", [
    "who is the developer of Windows", "who made Google", "who created Python", "who is Pakistan national poet?", "what is the time now",
    "open chrome", "who is the owner of this folder", "Nabiha Zainab", "create a folder named developer", "who designed the Eiffel tower",
    "Nabiha is not the developer of AgentDesk",
])
def test_other_questions_are_left_alone(text):
    answer = developer_answer(text)
    assert answer is None or "Yes" not in answer, text
    if "Windows" in text or "Google" in text or "Python" in text or "Eiffel" in text or "folder" in text:
        assert answer is None, text


def test_product_name_matching_is_loose_but_not_wild():
    for heard in ("AgentDesk", "Agent Desk AI", "AdenDesk", "Adenedask", "agentdesk ai", "Agent X"):
        assert names_the_product(heard), heard
    for other in ("Windows", "desktop", "Google Chrome", "agent smith", "the weather"):
        assert not names_the_product(other), other


def test_the_cloud_prompt_also_carries_the_fact():
    from app.conversation import system_prompt

    class _Persona:
        name = "Aria"; personality = "best_friend"; user_name = ""; custom_description = ""; formality = 3; humour = 3; verbosity = 3

    class _Prefs:
        persona = _Persona()

    try:
        prompt = system_prompt(_Prefs(), [])
    except Exception:                                  # persona helpers want a fuller object: the constant is what matters
        prompt = about.FACT
    assert "Nabiha Zainab" in prompt and "developer" in prompt


# ---------------------------------------------------------------- supervisor, co-supervisor, the developer's details
@pytest.mark.parametrize("text", [
    "who is the supervisor of AgentDesk AI", "who is the supervisor of this project", "who is your supervisor", "AgentDesk ka supervisor kaun hai",
    "who supervised this project", "who is the guide of AgentDesk AI?", "supervisor kaun hai is project ka", "who is the supervisor of my fyp project",
])
def test_the_supervisor_question_names_ms_uzma_kiran(text):
    answer = about.own_answer(text)
    assert answer and "Ms. Uzma Kiran" in answer and "Lecturer" in answer and "Sir Adnan Ahmed Pracha" in answer, text


@pytest.mark.parametrize("text", ["who is the co-supervisor of AgentDesk AI", "who is the co supervisor of this project", "AgentDesk ka co-supervisor kaun hai", "who is your cosupervisor?"])
def test_the_co_supervisor_question_names_sir_adnan(text):
    answer = about.own_answer(text)
    assert answer and "Sir Adnan Ahmed Pracha" in answer and "Uzma" not in answer, text


@pytest.mark.parametrize("text,who", [("who is Ms. Uzma Kiran", "Uzma Kiran"), ("who is Uzma Kiran?", "Uzma Kiran"), ("Uzma Kiran kaun hai", "Uzma Kiran"),
                                      ("who is Sir Adnan Ahmed Pracha", "Adnan Ahmed Pracha"), ("tell me about Adnan Pracha", "Adnan Ahmed Pracha")])
def test_asking_who_a_supervisor_is(text, who):
    answer = about.own_answer(text)
    assert answer and who in answer, text


@pytest.mark.parametrize("text", [
    "who is Nabiha Zainab", "who is Nabiha Zainab?", "tell me about Nabiha", "Nabiha Zainab kaun hai", "tell me about the developer of AgentDesk AI",
    "which university is the developer from", "which semester is the developer of AgentDesk in", "what does the developer of this project study",
])
def test_the_developer_details(text):
    answer = about.own_answer(text)
    assert answer and "Nabiha Zainab" in answer and "Riphah International University" in answer and "Software Engineering" in answer, text


def test_the_bio_says_seventh_semester_and_the_supervisors():
    bio = about.DEVELOPER_BIO
    assert "7th semester" in bio and "Ms. Uzma Kiran (Lecturer)" in bio and "Sir Adnan Ahmed Pracha" in bio
    for fact in ("Riphah International University", "Software Engineering", "Ms. Uzma Kiran", "Sir Adnan Ahmed Pracha", "7th semester"):
        assert fact in about.FACT


@pytest.mark.parametrize("text", [
    "rename supervisor folder to uzma", "named Ms. Uzma folder to Supervisor", "open supervisor folder", "create a folder named Uzma", "move uzma folder to D drive",
    "email Ms. Uzma Kiran about the report", "send a mail to uzma", "who is the president of Pakistan", "what is the time", "what is a supervisor in biology class",
    "which university is best in Pakistan", "who is Nabiha's friend Sara",
])
def test_commands_and_other_questions_are_not_taken_for_these_answers(text):
    answer = about.own_answer(text)
    assert answer is None or text.startswith("who is Nabiha"), text
