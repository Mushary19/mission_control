# Demo script (5 minutes)

Setup: `make start` (or `make dev`), browser at full width, "Reviewing as: Hana Pemberton". Start on a clean `backend/feedback.db` so the counts begin at zero.

---

### 0:00 – 0:40 · Overview

**Show:** the funnel tiles, the three process cards, the coverage notice in the top bar.

**Say:**
"Mission Control rebuilds how the People team runs leave, offboarding and onboarding from what is already in their tools: mail, calendar, Teams and screen activity. Over four weeks there were 11,346 raw records. After deduplication and grouping screen frames into sessions, that is 9,489 events, of which 397 are real process steps. Those form 70 cases. Nothing has been checked by a person yet, which is the last tile: steps waiting for review.
Note the bar at the top: the data comes from 6 of 12 staff. Account Managers, IT and Finance were not exported, so the tool never pretends to see their side."

**Point at** the confidence badges on the cards: "Leave rests on 29 complete cases, so high confidence. Onboarding has only 3, so it is labelled low."

### 0:40 – 1:20 · A finding

**Click:** "Laptops come after the start date" in Top findings.

**Say:**
"This is a pattern, not a one-off. All 9 new starters got their laptop request in after the date it was needed, which is always their start date, and most were confirmed 'onboarded' days before the laptop arrived. The tool explains why it calls this a pattern: it hits 9 of 9 eligible cases. Each starter's line is the evidence. Let's open one."

### 1:20 – 2:40 · Chiara's case

**Click:** Chiara Ekwueme.

**Say:**
"This is Chiara's onboarding as a timeline. Every step has a time in Sri Lanka time, who did it, where it came from (mail, Teams, calendar, screen) and how sure we are. High means an explicit message. Medium means a calendar entry or a name matched by context. 'Likely' means it was only seen on screen.
Under each step is the reason it belongs to Chiara. Here, 'Chaira Ekwueme' was a typo, one edit from Chiara, and there is no closer name.
The 'started before 2 Mar' badge means the contract was sent before our export, so it's not a missing step. The data just starts later."

**Point at** the small "by Lerato Faraday" tag on *Laptop requested*: "Hana owns this case. Lerato posted one step, so it's tagged, not called a handoff." (Vida Faraday's case shows a real handoff, "Hana → Lerato", because Lerato did everything after that point.)

### 2:40 – 3:30 · Proof and confirm

**Click:** "Proof" on **Laptop delivered**.

**Say:**
"Every step links back to the original record, unchanged, with the file and line number. This is Ravi's message in the Procurement channel: 'Chaira has the laptop now'. Nobody has to trust the model blindly."

**Click:** Confirm. A toast says "Saved".

**Say:** "Hana confirms the step. That goes to a local database and an audit file."

### 3:30 – 4:10 · Feedback and questions

**Click:** Feedback in the sidebar. The confirmation is there.

**Click:** Questions.

**Say:**
"Where the data is thin or shows two ways of working, the tool asks instead of guessing. Is sick leave a notice or a request? In 7 cases the client was asked, in 5 only told. Do you update the leave tracker after each request or in batches? Staff answer here, and the answers become the rules."

### 4:10 – 4:40 · Process map

**Click:** Leave.

**Say:**
"This is the discovered process: request, client asked, client approved, worker told. 25 of the 29 complete cases follow it exactly. The order comes from the data, not from a template. The times on the arrows are medians: about a day waiting for the client. Below are the variants: declined, sick-leave notice, cancelled. Click any step for real examples and to confirm or reject it."

### 4:40 – 5:00 · How it works and close

**Click:** How it works.

**Say:**
"Seven steps from raw export to these screens, each with a file you can open. No AI model: the messages are templated, so explicit rules are more honest and repeatable. An LLM would come in later for free-text mail and hard name matches, with staff confirming here. Next step: put these questions in front of Hana and Lerato, and feed their answers back in."
