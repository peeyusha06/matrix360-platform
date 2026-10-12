"""One lead, start to finish, across the real running services.

    bash start.sh        # SENDING_WINDOW_START_HOUR=0 SENDING_WINDOW_END_HOUR=24 to run outside 9am-8pm
    python e2e_test.py

Uses only synthetic people and the Radar's public company signals. Nothing is sent
to WhatsApp (mock sender) and nothing goes to LinkedIn.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DB, CHAT, ENGAGE = "http://127.0.0.1:8000", "http://127.0.0.1:8001", "http://127.0.0.1:4000"
ADMIN = {"X-Admin-Key": os.environ.get("ADMIN_API_KEY", "demo-admin-key")}
PHONE = "9000088888"  # synthetic buyer
env = dict(os.environ, SHARED_DB_URL=DB)


def call(method, url, body=None, headers=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise AssertionError(f"{method} {url} -> {e.code} {e.read()[:300]!r}") from None


def leads(**q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    return call("GET", f"{DB}/api/v1/leads?{query}", headers=ADMIN)


def by_phone(phone):
    return [l for l in leads(limit=500) if (l["phone"] or "").endswith(phone)]


def wait_for(fn, what, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        result = fn()
        if result:
            return result
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {what}")


def step(n, text):
    print(f"\n{n}. {text}")


def ok(text):
    print(f"   ok  {text}")


def main():
    for url in (f"{DB}/health", f"{CHAT}/health", f"{ENGAGE}/api/health"):
        call("GET", url)

    step(1, "Radar finds Sotefin Bharat and saves it to the shared DB")
    subprocess.run([sys.executable, str(ROOT / "services/radar/push_to_shared_db.py"), "--send"], env=env, check=True,
                   capture_output=True)
    sotefin = next(l for l in leads(source="radar") if l["company"].startswith("Sotefin"))
    assert sotefin["source"] == "radar" and sotefin["consent"] is False and "deccanchronicle" in sotefin["evidence"]
    ok(f"saved {sotefin['lead_id']} source=radar, evidence kept, consent=false")

    step(2, "Pratha's scoring: export to her sheet format, import her scored sheet")
    tmp = Path(tempfile.mkdtemp())
    subprocess.run([sys.executable, str(ROOT / "scripts/pratha_bridge.py"), "export", str(tmp / "out.csv")],
                   env=env, check=True, capture_output=True)
    rows = list(csv.DictReader(open(tmp / "out.csv")))
    row = next(r for r in rows if r["lead_id"] == sotefin["lead_id"])
    assert row["Name"].startswith("Sotefin") and row["Source URL"].startswith("https://")
    # Stand-in for the CSV her qualifier page downloads after AI scoring (needs her AI key to produce live).
    row.update({"Qualification": "Qualified", "Lead Score": "74", "Location pts": "20", "Activity pts": "24",
                "Credibility pts": "18", "Completeness pts": "12", "AI Reasoning": "Public IPO plan for a Kolkata factory."})
    with open(tmp / "scored.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    subprocess.run([sys.executable, str(ROOT / "scripts/pratha_bridge.py"), "import", str(tmp / "scored.csv")],
                   env=env, check=True, capture_output=True)
    scored = call("GET", f"{DB}/api/v1/leads/{sotefin['lead_id']}", headers=ADMIN)
    assert scored["fit_score"] == 74 and scored["stage"] == "qualified" and "Pratha rubric" in scored["fit_reasons"][0]
    ok("fit_score 74 with reasons, stage qualified, change audited")

    step(3, "Tanmayi's policy gate is asked about a WhatsApp message to the Radar lead")
    verdict = call("POST", f"{ENGAGE}/api/policy/check", {"lead_id": sotefin["lead_id"],
                   "message": {"text": "Hello", "is_template": True, "template_name": "x", "channel": "whatsapp"}})
    assert verdict["allowed"] is False and verdict["reason_code"] == "CONSENT_MISSING"
    ok("blocked: CONSENT_MISSING (Radar leads get a manual, approved LinkedIn message instead)")

    step(4, "A buyer fills in Shalini's site-visit form (exact LeadForm payload)")
    form = {"kind": "visit", "name": "Meera Das", "phone": PHONE, "email": "", "date": "2026-10-17", "slot": "Morning",
            "config": "3 BHK", "message": "", "from": "",
            "attribution": {"landing": "/", "utm_source": "instagram", "utm_campaign": "sh_oct"},
            "summary": "Site visit request: 3 BHK, Sat 17 Oct, Morning"}
    landing = call("POST", f"{DB}/integrations/landing/enquiry", form)["lead"]
    assert (landing["source"], landing["utm_source"], landing["utm_campaign"]) == ("landing_page", "instagram", "sh_oct")
    ok(f"lead {landing['lead_id']} source=landing_page utm=instagram/sh_oct consent=false")

    step(5, "The same buyer chats in Avinash's widget and agrees to WhatsApp follow-up")
    s = call("POST", f"{CHAT}/api/session", {"client_id": "shree-heights", "name": "Meera Das", "phone": PHONE,
                                              "consent": True, "utm_source": "instagram", "utm_campaign": "sh_oct"})
    for text in ["To live in", "3 BHK", "about 80 lakh", "within 2 months", "I'm the decision-maker", "Gated community",
                 "That's all", "Site visit", "Sat 17 Oct", "Morning", "WhatsApp", "Evening", "Yes"]:
        call("POST", f"{CHAT}/api/chat", {"session_id": s["session_id"], "message": text})
    lead = wait_for(lambda: next((l for l in by_phone(PHONE) if l["external_ref"] and l["consent"]
                                  and l["details"].get("chat", {}).get("followup_consent")), None), "chat sync", 45)
    assert len(by_phone(PHONE)) == 1 and lead["lead_id"] == landing["lead_id"], "chat must match the form lead, not duplicate it"
    assert lead["source"] == "landing_page" and lead["intent"] == "hot" and lead["stage"] == "engaged"
    assert lead["details"]["chat"]["visit_pref"]
    history = call("GET", f"{DB}/api/v1/leads/{lead['lead_id']}/contacts", headers=ADMIN)
    assert any(c["channel"] == "chat" for c in history) and all(c["status"] == "chat" for c in history)
    ok("matched by phone, one lead, source kept, intent=hot, consent=true, chat transcript stored")

    step(6, "Tanmayi sends a WhatsApp follow-up: queued for a person to approve, then approved")
    job = call("POST", f"{ENGAGE}/api/outbound/trigger", {"lead_id": lead["lead_id"], "message_type": "site_visit_invite"})
    assert job["result"]["status"] == "PENDING_APPROVAL", job
    job_id = job["result"]["job_id"]
    call("POST", f"{ENGAGE}/api/approvals/{job_id}/approve", {"operator": "e2e-test"})
    sent = wait_for(lambda: [c for c in call("GET", f"{DB}/api/v1/leads/{lead['lead_id']}/contacts", headers=ADMIN)
                             if c["channel"] == "whatsapp" and c["status"] == "sent"], "WhatsApp contact record")
    after = call("GET", f"{DB}/api/v1/leads/{lead['lead_id']}", headers=ADMIN)
    assert after["stage"] == "engaged"  # Tanmayi only moves new/qualified leads to contacted
    ok(f"approved and sent (mock WhatsApp), contact recorded ({sent[0]['message_id']}), stage stays engaged")

    step(7, "Site visit scheduled; reminder found and checked against the policy gate")
    visit = call("POST", f"{DB}/api/v1/leads/{lead['lead_id']}/site-visits", {"requested_by": "chat"}, ADMIN)
    at = datetime.now(timezone.utc) + timedelta(hours=20)
    call("PATCH", f"{DB}/api/v1/site-visits/{visit['id']}", {"status": "scheduled", "scheduled_at": at.isoformat()}, ADMIN)
    assert call("GET", f"{DB}/api/v1/leads/{lead['lead_id']}", headers=ADMIN)["stage"] == "visit_booked"
    out = subprocess.run([sys.executable, str(ROOT / "scripts/reminders.py")], env=env, check=True,
                         capture_output=True, text=True).stdout
    assert "24h reminder for Meera Das" in out
    again = subprocess.run([sys.executable, str(ROOT / "scripts/reminders.py")], env=env, check=True,
                           capture_output=True, text=True).stdout
    assert "Meera Das" not in again
    ok(f"stage visit_booked; reminder handled once: {out.split()[0]}")

    step(8, "The buyer replies STOP on WhatsApp")
    call("POST", f"{ENGAGE}/api/webhook/whatsapp", {"phone": f"91{PHONE}", "text": "STOP", "message_id": f"e2e-stop-{time.time()}"})
    stopped = wait_for(lambda: (l := call("GET", f"{DB}/api/v1/leads/{lead['lead_id']}", headers=ADMIN))["opted_out"] and l,
                       "opt-out")
    blocked = call("POST", f"{ENGAGE}/api/policy/check", {"lead_id": lead["lead_id"],
                   "message": {"text": "Hi", "is_template": True, "template_name": "x", "channel": "whatsapp"}})
    assert stopped["stage"] == "opted_out" and blocked["reason_code"] == "LEAD_OPTED_OUT"
    ok("opted_out=true in the shared DB; every later message is blocked")

    step(9, "Dashboard data: one lead, full history, funnel")
    detail = call("GET", f"{DB}/api/v1/leads/{lead['lead_id']}", headers=ADMIN)
    events = [e["event_type"] for e in detail["audit_history"]]
    for needed in ("lead.created", "lead.chat_synced", "contact.outbound", "site_visit.scheduled", "lead.updated"):
        assert needed in events, f"missing audit event {needed}: {events}"
    assert len(detail["site_visits"]) == 1
    funnel = call("GET", f"{DB}/api/v1/funnel", headers=ADMIN)
    assert funnel["opted_out"] >= 1 and funnel["by_source"].get("radar", 0) >= 4
    ok(f"funnel {funnel['stages']} | sources {funnel['by_source']}")
    ok(f"audit trail: {', '.join(events)}")
    print("\nALL STEPS PASSED")


if __name__ == "__main__":
    main()
