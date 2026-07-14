# Understand Claude Code: more deeply

*(Offline synthesis fallback: stitched key excerpts. Provide your own LLM for better results.)*

## Key excerpts
- **[1] my prior memo: memo_claude-code-sends-4-7x-more-tokens-than-opencode-before-read.md**

```
# Research memo: Claude Code Sends 4.7x More Tokens Than OpenCode Before Reading Your Prompt | Systima Blog

Claude Code Sends 4.7x More Tokens Than OpenCode Before Reading Your Prompt | Systima Blog We put Claude Code and OpenCode on the same model, the same machine, and the same tasks, then examined everything sent and received. Claude Code is far hungrier: When we asked both harnesses for a one-line reply, Claude Code used roughly 33,000 tokens of system prompt, tool schemas, and injected scaffolding before the prompt even arrived. OpenCode used about 7,000. Claude Code is far more cache inefficient: OpenCode s request prefix was byte-identical in every run we captured; it paid to cache its payload once per session and read it back for pennies. Claude Code on the other hand re-wrote tens of thousands of prompt-cache tokens mid-session, run after run, and on the same task wrote up to 54x more cache tokens than OpenCode . Cache writes of course are billed at a premium, which accounted for the usage dashboard climbing when using Claude Code. Config further bloats the prompt: A production repository s 72KB instruction (AGENTS.md or CLAUDE.md) file adds another (avg) 20,000 tokens to
```

- **[2] https://en.wikipedia.org/wiki/Claude_%28AI%29**

```
Claude (AI) - Wikipedia Jump to content From Wikipedia, the free encyclopedia Large language model and AI chatbot by Anthropic Claude Developer Anthropic Release March 2023 (3 years ago) ( 2023-03 ) Stable release Claude Sonnet 5 June 30, 2026 (12 days ago) ( 2026-06-30 ) Claude Fable 5 June 9, 2026 (33 days ago) ( 2026-06-09 ) Claude Opus 4.8 May 28, 2026 (45 days ago) ( 2026-05-28 ) Claude Haiku 4.5 October 15, 2025 (8 months ago) ( 2025-10-15 ) Platform Cloud computing platforms Type Large language model Chatbot Generative pre-trained transformer Foundation model License Proprietary Website claude .ai Claude is a series of large language models developed by American software company Anthropic . Named after Claude Shannon , Claude was released as an AI -based chatbot in March 2023. It is also used in AI-assisted software development . Claude is trained using "constitutional AI", a technique developed by Anthropic to improve ethical and legal compliance ( AI alignment ). Since Claude 3, each generation has typically been released in three sizes, from least to most capable: Haiku, Sonnet, and Opus. An additional model named Claude Mythos was released to a handful of companies in 20
```

- **[3] https://en.wikipedia.org/wiki/Anthropic**

```
Anthropic - Wikipedia Jump to content From Wikipedia, the free encyclopedia American artificial intelligence company For the philosophical and cosmological concept, see Anthropic principle . "},"founders":{"wt":"{{Unbulleted list|\n| [[Dario Amodei]]\n| [[Daniela Amodei]]\n| [[Jared Kaplan]] ref name=\"wsj1\">{{Cite news |last=Lin |first=Belle |title=Google and Anthropic Are Selling Generative AI to Businesses, Even as They Address Its Shortcomings |url=https://www.wsj.com/articles/google-and-anthropic-are-selling-generative-ai-to-businesses-even-as-they-address-its-shortcomings-ff90d83d |access-date=2024-04-11 |work=WSJ |language=en-US |archive-date=April 10, 2024 |archive-url=https://web.archive.org/web/20240410011503/https://www.wsj.com/articles/google-and-anthropic-are-selling-generative-ai-to-businesses-even-as-they-address-its-shortcomings-ff90d83d |url-status=live }} /ref>\n| Jack Clark ref>{{cite news |title=Alphabet-backed Anthropic outlines the moral values behind its AI bot |url=https://www.reuters.com/technology/alphabet-backed-anthropic-outlines-moral-values-behind-its-ai-bot-2023-05-09/|work=[[Reuters]]|date=9 May 2023|access-date=4 June 2023 |last1=Nellis |first1=Ste
```

- **[4] https://en.wikipedia.org/wiki/Claude_Mythos**

```
Claude Mythos - Wikipedia Jump to content From Wikipedia, the free encyclopedia Large language model {{start date and age|2026|06|09}}"},"replaces":{"wt":""},"replaced_by":{"wt":""},"genre":{"wt":"{{indented plainlist|\n*[[Large language model]]\n*[[Generative pre-trained transformer]]\n}}"},"platform":{"wt":""},"license":{"wt":"[[Proprietary software|Proprietary]]"},"website":{"wt":""}},"i":0}}]}'> Claude Mythos Developer Anthropic Release April 7, 2026 ; 3 months ago ( 2026-04-07 ) Stable release Claude Mythos 5 / June 9, 2026 ; 33 days ago ( 2026-06-09 ) Type Large language model Generative pre-trained transformer License Proprietary Claude Mythos is a series of large language models developed by Anthropic . The first model in the series was Claude Mythos Preview. Anthropic did not release the model to the public, due to its unusually strong ability to find software vulnerabilities . [ 1 ] The public had mixed reactions to the announcement of Claude Mythos Preview. [ 2 ] A publicly-available version of the model, Claude Fable 5, was later released, along with a private version called Claude Mythos 5. History [ edit source ] Leak (March 26 – April 7) [ edit source ] The existence
```

- **[5] https://en.wikipedia.org/wiki/Codex_%28AI_agent%29**

```
Codex (AI agent) - Wikipedia Jump to content From Wikipedia, the free encyclopedia Software engineering agent developed by OpenAI This article is about the AI agent. For the language model, see OpenAI Codex (language model) . {{cite web |title=openai/codex |url=https://github.com/openai/codex |website=Github |publisher=OpenAI |access-date=8 June 2026 |date=8 June 2026}} /ref>"},"website":{"wt":"{{URL|https://chatgpt.com/codex/}}"}},"i":0}}]}'> Codex The Codex desktop app start screen, showing options for creating a new project and using Codex tools Developer OpenAI Release 2025 ; 1 year ago ( 2025 ) Operating system Windows macOS Web platform License Apache 2.0 [ 1 ] Website chatgpt .com /codex / Repository github .com /openai /codex Codex is an AI coding agent developed by OpenAI for software engineering tasks such as writing code and fixing bugs, released in April 2025 as Codex CLI. [ 2 ] Codex is available through ChatGPT's web app, the Codex CLI, a desktop app for Windows and macOS , [ 3 ] and several IDE integrations. [ citation needed ] In March 2026, OpenAI introduced Codex Security, an application-security agent designed to identify and fix software vulnerabilities . [ 4 ] 
```

- **[6] https://en.wikipedia.org/wiki/Bun_%28software%29**

```
Bun (software) - Wikipedia Jump to content From Wikipedia, the free encyclopedia JavaScript runtime {{cite web | url=https://github.com/oven-sh/bun/releases/tag/bun-build-8 | access-date=14 September 2021|title=Releases, oven-sh/bun, Github| website=[[GitHub]]}} /ref>"},"genre":{"wt":"[[Runtime system|Runtime environment]]"},"latest release version":{"wt":"{{wikidata|property|preferred|references|edit|Q113048518|P348|P548=Q2804309}}"},"latest release date":{"wt":"{{Start date and age|{{wikidata|qualifier|preferred|single|Q113048518|P348|P548=Q2804309|P577}}}}"},"repo":{"wt":"{{URL|https://github.com/oven-sh/bun}}"},"programming language":{"wt":"[[Rust (programming language)|Rust]], [[Zig (programming language)|Zig]], [[C++]] ([[JavaScriptCore|JSC]] bindings), [[C (programming language)|C]] ([[WebSocket]] bindings), [[TypeScript]], [[JavaScript]]"},"operating system":{"wt":"[[Linux]], [[macOS]], [[Microsoft Windows|Windows]]"},"license":{"wt":"[[MIT license]] ref>{{Cite web |last=Sumner |first=Jarred |date=2023-07-02 |title=License |url=https://bun.sh/docs/project/licensing |access-date=2023-07-07 |website=Bun Docs |archive-date=2023-07-06 |archive-url=https://web.archive.org/web/20
```

- **[7] https://en.wikipedia.org/wiki/Vibe_coding**

```
Vibe coding - Wikipedia Jump to content From Wikipedia, the free encyclopedia AI-dependent computer programming Vibe coding is a software development practice assisted by artificial intelligence (AI) where the software developer describes a project or task in a prompt to a large language model (LLM) which generates source code automatically . Vibe coding may involve accepting AI-generated code without thorough review of the output, instead relying on results and follow-up prompts to guide changes. [ 1 ] [ 2 ] The term was coined in February 2025 by computer scientist Andrej Karpathy , a co-founder of OpenAI and former AI leader at Tesla . Merriam-Webster listed the term in March 2025 as a "slang trending" expression. [ 3 ] It was named the Collins English Dictionary Word of the Year for 2025. [ 4 ] [ 5 ] Advocates of vibe coding say that it allows even amateur programmers to produce software without the extensive training and skills required for software engineering . [ 6 ] [ 7 ] Critics point out a lack of accountability, maintainability , and an increased risk of introducing security vulnerabilities in the resulting software. [ 1 ] [ 7 ] Definition [ edit ] The term "vibe coding"
```

- **[8] https://en.wikipedia.org/wiki/Code_of_Hammurabi**

```
Code of Hammurabi - Wikipedia Jump to content From Wikipedia, the free encyclopedia Babylonian legal text {{cite book |last1=Sasson |first1=Jack |title=Civilizations of the Ancient Near East |publisher=Hendrickson |isbn=0684192799 |pages=901, 908}} /ref> ref>{{cite book |last1=Ross |first1=Leslie |title=Art and Architecture of the World s Religions |publisher=Greenwood Press |pages=35}} /ref>"},"subject":{"wt":"Law, justice"},"purpose":{"wt":"Debated: [[legislation]], [[law report]], or [[jurisprudence]]"},"wikisource":{"wt":"Code of Hammurabi"}},"i":0}}]}'> Hammurabi's code The Louvre stele Created c. 1753 BC Location Louvre Museum , Ile-de-France , France (originally Sippar , Mesopotamia (now Iraq ), found at Susa , Iran) Replicas: various Author Hammurabi Media type Basalt stele [ 1 ] [ 2 ] Subject Law, justice Purpose Debated: legislation , law report , or jurisprudence Full text Code of Hammurabi at Wikisource The Code of Hammurabi is a Babylonian legal text composed c. 1753 BC. It is the longest, best-organized, and best-preserved legal text from the ancient Near East . It is written in the Old Babylonian dialect of Akkadian , purportedly by Hammurabi , sixth king of the Firs
```

- **[9] https://en.wikipedia.org/wiki/Binary_code**

```
Binary code - Wikipedia Jump to content From Wikipedia, the free encyclopedia Encoded data represented in binary notation For the binary form of computer software, see Machine code . The ASCII-encoded letters of "Wikipedia" represented as binary codes. A binary code is the value of a data-encoding convention represented in a binary notation that usually is a sequence of 0s and 1s, sometimes called a bit string . For example, ASCII is an 8-bit text encoding that in addition to the human readable form (letters) can be represented as binary. Binary code can also refer to the mass noun code that is not human readable in nature such as machine code and bytecode . Even though all modern computer data is binary in nature, and therefore can be represented as binary, other numerical bases may be used. Power of 2 bases (including hex and octal ) are sometimes considered binary code since their power-of-2 nature makes them inherently linked to binary. Decimal is, of course, a commonly used representation. For example, ASCII characters are often represented as either decimal or hex. Some types of data such as image data is sometimes represented as hex, but rarely as decimal. History [ edit ] F
```

- **[10] https://en.wikipedia.org/wiki/Code-switching**

```
Code-switching - Wikipedia Jump to content From Wikipedia, the free encyclopedia Changing between languages during a conversation This article is about alternating between two or more languages in speech. For other uses, see Code-switching (disambiguation) . Not to be confused with Plurilingualism or Situational code-switching . Sarah Geronimo and an interviewer code-switch between English and Filipino . Such code-switching is widespread in the Philippines. Maya Diab code-switches between English and Lebanese Arabic mid-sentence. Sociolinguistics Key concepts Code-switching Language change Language ideology Language planning Multilingualism Prestige Variation Areas of study Accent Bilingual pun Dialect Diglossia Homophonic translation Macaronic language Phono-semantic matching Register Discourse analysis Language varieties Linguistic description Loanword Pragmatics Pidgin Soramimi People Sociolinguists Related fields Applied linguistics Historical linguistics Linguistic anthropology Sociocultural linguistics Sociology of language Category Linguistics portal v t e In linguistics , code-switching or language alternation is the process of shifting from one linguistic code (a language 
```

- **[11] https://en.wikipedia.org/wiki/Error_correction_code**

```
Error correction code - Wikipedia Jump to content From Wikipedia, the free encyclopedia Scheme for controlling errors in data over noisy communication channels "Interleaver" redirects here. For the fiber-optic device, see optical interleaver . In computing , telecommunication , information theory , and coding theory , forward error correction ( FEC ) or channel coding [ 1 ] is a technique used for controlling errors in data transmission over unreliable or noisy communication channels . The central idea is that the sender encodes the message in a redundant way, most often by using an error correction code , or error correcting code ( ECC ). [ 2 ] [ 3 ] The redundancy allows the receiver not only to detect errors that may occur anywhere in the message, but often to correct a limited number of errors. Therefore a reverse channel to request re-transmission may not be needed. The cost is a fixed, higher forward channel bandwidth. The American mathematician Richard Hamming pioneered this field in the 1940s and invented the first error-correcting code in 1950: the Hamming (7,4) code . [ 3 ] FEC can be applied in situations where re-transmissions are costly or impossible, such as one-way c
```

## Sources
[1] my prior memo: memo_claude-code-sends-4-7x-more-tokens-than-opencode-before-read.md
[2] https://en.wikipedia.org/wiki/Claude_%28AI%29
[3] https://en.wikipedia.org/wiki/Anthropic
[4] https://en.wikipedia.org/wiki/Claude_Mythos
[5] https://en.wikipedia.org/wiki/Codex_%28AI_agent%29
[6] https://en.wikipedia.org/wiki/Bun_%28software%29
[7] https://en.wikipedia.org/wiki/Vibe_coding
[8] https://en.wikipedia.org/wiki/Code_of_Hammurabi
[9] https://en.wikipedia.org/wiki/Binary_code
[10] https://en.wikipedia.org/wiki/Code-switching
[11] https://en.wikipedia.org/wiki/Error_correction_code

---
Builds on: /Users/ricmassey/orrin_v3/data/goals/artifacts/g_959bc92919e5/memo_claude-code-sends-4-7x-more-tokens-than-opencode-before-read.md
