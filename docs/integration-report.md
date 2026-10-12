# Integration report

12 Oct 2026. Covers what each project is, how it now connects, what changed, and what is still open.

## 1. What was found

| Project | Stack | Before integration |
|---|---|---|
| Shared DB / ReferralOps (Mayur) | FastAPI, SQLAlchemy, SQLite or Postgres, Alembic | The central DB. Save and get lead APIs, dedupe, scoring with a shared hot/warm/cold rule, approvals, site visits, audit. No update endpoint, no message history. |
| Demand Radar (Peeyusha) | Python | Already posting to the shared DB. |
| Website chat (Avinash) | FastAPI, SQLite, plain JS widget | Own `chat.db`. Sends to `/leads/upsert` and `/messages` with its own field names. Not connected. |
| WhatsApp engage (Tanmayi) | Node, Express | Calls `/api/leads` paths the DB did not have, then silently fell back to a mock adapter. Not connected. |
| Lead qualifier (Pratha) | n8n, Google Sheets, AI API, HTML page | Works on a Google Sheet. Not connected. |
| Landing site (Shalini) | Vite, React | Form endpoint empty, so enquiries only opened WhatsApp. Not connected. |
| Enrichment (Rishabh), plot map (Aditya) | | Code not shared, so not integrated. |

## 2. How each tool connects now

The shared DB stays the only lead database. Each tool keeps its own code and is pointed at an adapter in Mayur's app that speaks the format it already uses.

| Tool | Change needed in the tool | Connection |
|---|---|---|
| Radar | None | `POST /api/v1/leads` |
| Chat (Avinash) | None. Set `DB_API_URL`, `DB_API_KEY` | `/integrations/chat/leads/upsert`, `/integrations/chat/messages` |
| WhatsApp (Tanmayi) | None. Set `SHARED_DB_URL`, `SHARED_DB_API_KEY`, `USE_DEV_DB_ADAPTER=false` | `/integrations/whatsapp/api/leads...` |
| Landing site (Shalini) | One line: `FORM_ENDPOINT` reads `VITE_FORM_ENDPOINT` (`patches/shalini-form-endpoint.patch`). Avinash's chat widget loads when `VITE_CHAT_WIDGET_URL` is set (`patches/shalini-chat-widget.patch`); without it the site runs as before. | `/integrations/landing/enquiry`; chat via Avinash's widget |
| Qualifier (Pratha) | None | `scripts/pratha_bridge.py` exports her sheet format and imports scores with `PATCH` |
| Reminders | New | `GET /api/v1/reminders/due` + Tanmayi's policy gate (`scripts/reminders.py`) |
| Dashboard | New | `/platform` page in Mayur's app |

## 3. Field mapping

**Avinash's chat record to the shared format**

| Chat field | Shared field | Rule |
|---|---|---|
| `lead_id` | `external_ref` | `chat:<id>`. Every chat turn updates the same lead. |
| `client_id` | `client` | `shree-heights` to Shree Heights, `lakhotia-industrial` to Lakhotia, `vrindavan-greens` to Vrindavan Greens |
| `property_type` | `property_type` | flat to flats, plot to plots, industrial unchanged |
| `name`, `phone`, `email` | same | Phone matching uses the last 10 digits |
| `followup_consent` | `consent` | true sets true, false sets false, empty leaves it unchanged. `intake_consent` (chat box tick) is not marketing consent. |
| `timeline` | `timeline` | asap to immediate, 1_3 to within_3_months, 3_6 to within_6_months, 6_plus to within_12_months |
| `budget_min/max_lakh` | `budget_inr` | lakh x 100,000 |
| `role` | `is_decision_maker` | decision_maker true; helping or researching false |
| `consult_type` = visit | `site_visit_interest` | |
| `score` (Hot/Warm/Cold) | kept in `details.chat.score` | `intent` comes from the one shared rule in Mayur's `scoring.py`, so chat, forms and WhatsApp rate leads the same way |
| `stage` | `stage` | In conversation, Qualified, Handoff to engaged; Visit booked to visit_booked. Stage never moves backwards. |
| `handoff_requested` | `next_action` | "Sales to call: reason" |
| `utm_source`, `utm_campaign` | same | |
| everything else (`summary`, `open_questions`, `features`, `visit_pref`, ...) | `details.chat` | Kept, shown on the dashboard |

**Shalini's forms**

| Form | Becomes |
|---|---|
| Site visit / enquiry | `lead_type: buyer`, `source: landing_page`, UTM from attribution, `evidence` = landing page, `site_visit_interest` for visit forms, `consent: false` (the form has no consent box) |
| Referral with a prospect | `lead_type: buyer`, `source: referral`, `consent: false` and next action "Confirm the prospect's consent", because consent was asserted by the partner for one enquiry only |
| Partner sign-up | `lead_type: broker`, `source: broker` |
| Skipped answers ("Unknown") | treated as missing, never stored as a value |

**Tanmayi** already used the shared field names. Her `stage: "opted_out"` is accepted. Contact records keep her shape (`timestamp`, `direction`, `status`, `channel`, `message_id`).

**Pratha's sheet** columns are kept as-is with a `lead_id` column added. Her score becomes `fit_score`; her points, reasoning and missing info become `fit_reasons`; 65 or more sets stage `qualified`.

## 4. Changes made

Only Mayur's repo changed, on branch `integration/matrix360-platform`. All additive:
- `PATCH /api/v1/leads/{id}`, contact history, funnel, due reminders, `/platform` dashboard.
- Adapters for chat, WhatsApp and landing forms.
- Site-visit status now moves the lead stage.
- Migration `c7d1a2b3e4f5` adds `external_ref`, `details`, `contact_events`. Tested on a database created by the current main branch: old lead kept, new endpoints work on it.
- 13 new tests.

Bugs found and fixed while testing the real services together:
- The chat sends overlapping updates from two background threads; the last one could overwrite newer answers. Chat updates now apply one at a time, older records are ignored, and same-second records merge.
- Chat lines sent in the same second were treated as duplicates. Fixed.
- `stop.sh` could leave an old server running on port 8000. Now stops by port, and `start.sh` refuses to start on a busy port.

## 5. Test results (12 Oct 2026)

| Suite | Before | After |
|---|---|---|
| Mayur `pytest` | 29 passed | 42 passed (29 original + 13 new) |
| Avinash `pytest` | 76 passed | 76 passed (code unchanged) |
| Tanmayi `npm test` | 17 passed | 17 passed (code unchanged) |
| Peeyusha `test_push.py` | 2 passed | 2 passed |
| `e2e_test.py` across real services | n/a | 5 of 5 runs passed |
| Shalini's real form in a browser to the DB | n/a | Saved with `source: landing_page`, `utm facebook / browser_test` |

## 6. Issues for each owner

**Tanmayi**
- `campaignKnowledge.js` keys projects as "Lakhotia Industrial Complex", but the shared `client` is "Lakhotia". A Lakhotia lead falls back to Shree Heights templates. Add "Lakhotia" as the key or an alias.
- The Shree Heights first-outreach template says "starting from ₹70 lakhs". The developer's website says prices are not decided yet. Confirm with the client before using it.
- Lakhotia's location is listed as "Hooghly"; the project is on Ranihati–Amta Road, Howrah.
- No `site_visit_reminder` template exists, so reminders are blocked (correctly). It needs Meta approval first.
- The public repo contains a `.env` file. It has no real keys, but remove it and keep `.env.example` only.
- When the shared DB is unreachable, `sharedDbClient.js` quietly switches to mock data. In production that should fail loudly instead.

**Shalini**
- Apply `patches/shalini-form-endpoint.patch` (one line) and `patches/shalini-chat-widget.patch` (adds Avinash's widget, only when configured). Tested in a browser: a chat on the site reached the shared DB with `source: chat`, the page address and `utm google / widget_test`.
- The page title says "from ₹70 Lakhs". Same unconfirmed price; check with the client.
- Add a consent checkbox to the visit form if the team wants to follow up on WhatsApp after a form enquiry.

**Mayur**
- Review and merge the integration branch.
- `POST /api/v1/leads` has no key, and the admin key is `demo-admin-key`. Fine on one laptop; add a write key and change all keys before hosting.
- The chat lock works for one app process. With several processes on Postgres, use a row lock.

**Pratha**
- Her qualifier calls an AI API that needs a key. Ramjit said OpenAI or Grok, not Claude, for this; switch the model when the company key arrives.
- The bridge is a CSV step. Later, her n8n flow can call `GET /api/v1/leads` and `PATCH` directly.

**Avinash**
- Nothing required. The chat widget already worked through his `DB_API_URL` contract.

## 7. Not done or not verified

- Rishabh's enrichment and Aditya's plot map: code not shared.
- Real WhatsApp sending (mock only), real Grok or OpenAI calls (demo mode only).
- Pratha's n8n flows were not run in n8n; the bridge was tested with a scored CSV standing in for her page's output.
- LinkedIn: messages stay manual. Tanmayi's gate covers WhatsApp only.
- Hosting: everything runs on one laptop with SQLite.
