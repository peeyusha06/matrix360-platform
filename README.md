# Matrix360 Platform

Runs the intern team's tools as one lead platform on one laptop, all writing to Mayur's shared lead database.

```
Find                    Save + score              Reach out / talk                  Visit
Radar (Peeyusha)  ─┐                              Chat widget (Avinash) ──┐
Landing forms     ─┼──▶  Shared DB (Mayur)  ◀───▶ WhatsApp engage +      ├──▶  Site visit, reminders,
 (Shalini)         │     dedupe, scoring,         policy gate (Tanmayi) ─┘     dashboard
Referrals         ─┘     audit, dashboard   ◀───  Qualifier (Pratha) via bridge
```

## Run the demo

Needs Python 3.10+, Node 20+, git.

```
bash setup.sh      # fetches every service into ./services and installs dependencies
bash start.sh      # starts everything (see ports below)
python e2e_test.py # one lead, start to finish
bash stop.sh
```

Outside 9am to 8pm IST, Tanmayi's policy gate blocks WhatsApp sends, as it should. To run the test anyway:
`SENDING_WINDOW_START_HOUR=0 SENDING_WINDOW_END_HOUR=24 bash start.sh`

| Service | Owner | Address |
|---|---|---|
| Shared lead DB + API | Mayur | http://127.0.0.1:8000 (API docs `/docs`) |
| **Dashboard** | | http://127.0.0.1:8000/platform (admin key: `demo-admin-key`) |
| Website chat | Avinash | http://127.0.0.1:8001/demo |
| WhatsApp engage + policy gate | Tanmayi | http://127.0.0.1:4000 |
| Landing site | Shalini | http://127.0.0.1:5173 (only if `../shree-heights-main` exists) |

Scripts:
- `scripts/pratha_bridge.py`: exports leads in Pratha's sheet columns, imports her scored sheet back as `fit_score` and `fit_reasons`.
- `scripts/reminders.py`: finds site-visit reminders that are due and checks each with Tanmayi's policy gate. Run every 15 minutes.
- `services/radar/push_to_shared_db.py --send`: adds Radar leads.

## What the end-to-end test proves

All against the real running services, with synthetic people only:

1. Radar adds Sotefin Bharat. Saved with `source: radar`, evidence links, consent false.
2. Pratha's scoring (through the bridge) sets fit 74 with reasons, stage `qualified`.
3. Tanmayi's policy gate blocks WhatsApp to the Radar lead: `CONSENT_MISSING`.
4. A buyer submits Shalini's site-visit form. Saved with `source: landing_page` and UTM.
5. The same buyer chats in Avinash's widget. Matched to the same lead by phone (no duplicate), source kept, intent hot, follow-up consent recorded, chat transcript stored.
6. Tanmayi's WhatsApp follow-up waits for a person's approval, then sends (mock) and is recorded.
7. Site visit scheduled: stage `visit_booked`. The reminder is checked once and blocked with the real reason: no approved reminder template yet.
8. The buyer replies STOP: `opted_out: true` in the shared DB, every later message blocked.
9. The dashboard data shows one lead, its full history, audit trail and funnel.

Last result: 5 runs in a row, all steps passed (12 Oct 2026).

Details, field mappings and open issues: [docs/integration-report.md](docs/integration-report.md).
