# Work documents (F6): research, plans, notes

Say: "research solar energy and make me a file", "write a detailed report on the Mughal empire in Urdu", "make a study plan for my exams", "summarise the 3 PDFs in Downloads into notes",
"summarise report.pdf and notes.docx into notes". Add "short / detailed", "in Urdu / Roman Urdu / Hindi / English", "as PDF / markdown" if you like.

**Flow**
1. A broad request (a short topic and nothing said about size or language) is answered with ONE question: "How detailed should it be (brief, standard or detailed), and in which language? For example say: 'standard, in English'." Your answer continues the same request. No approval is asked for the question.
2. You approve once (it writes a file and sends text to the cloud AI). Progress is shown and can be stopped: Searching -> Reading source n -> Planning the outline -> Writing section n of m -> Saving.
3. The file is saved in `Documents\AgentDesk` (a name is never overwritten: "(2)"), opened, and the assistant says "Your file is ready: <title>. n sections, m sources, saved in Documents\AgentDesk."

**What is fixed code and what is the AI.** Code: search (Wikipedia, Tavily), fetching public pages, reading your files, writing .docx / .md / .pdf (the PDF is printed by Edge in its own profile), naming, opening, checking. The AI only writes section prose from the text it is handed (fenced as untrusted data; instructions inside pages and files are ignored). The Sources list contains only pages really read; a citation `[n]` to a source that does not exist is removed. A plan has no sources and says so. Every document carries a line saying an AI wrote it from the listed sources and that important facts should be checked.

**Checked after saving** (reading the file back): it exists and opens; it has the title, all sections and real text; every `[n]` points at a listed source; every listed source URL is one that was fetched.

**Needs** "Answer questions with the cloud AI" (Settings): topic, page text and file text go to Groq. Without it nothing is searched or sent. Search needs `WIKIPEDIA_CONTACT_EMAIL` (your own address; Wikipedia asks for one) and/or a Tavily key (docs/SEARCH_SETUP.md). Long text uses this PC's own Groq key when there is one. The cloud brain on Render has a new `max_tokens` / `effort` option for the same purpose, but it must be REDEPLOYED to use it (its old chat endpoint is capped at 400 tokens and cannot write a section).

**Measured on this PC** (`backend/scripts/document_live.py`, `docs/eval/f6_live.json`, samples in `docs/eval/f6_samples/`): 7/7 cases with the real fetcher, the real Groq models and the real writers: Word (13.9 s, brief), Markdown (15.9 s), PDF through Edge (12.8 s), a study plan (5.7 s), Urdu (9.7 s, the large model), notes from two files (5.4 s), and the broad topic correctly asking its question. The first progress line appears in under 0.1 s. The pages read were fixed public pages (National Geographic, World History, Ducksters), because the search PROVIDERS need your contact e-mail or a key; `--real-search` runs them once you have set them. Wikipedia pages return HTTP 403 to the generic page fetcher (the Wikipedia provider supplies its own text instead).

**Limits.** Brief = 3 sections, standard = 5, detailed = 7: only brief was run live (token limits of the free Groq tier). The AI can still misstate a fact that is in a source; the label tells the reader to check. Word and PDF layout is simple (headings, paragraphs, bullets). Urdu is right-to-left in Word; the PDF path sets `dir="rtl"` but an Urdu PDF was not checked by eye. Opening uses the PC's default app for the file type.
