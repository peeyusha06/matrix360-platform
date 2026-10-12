"""Site-visit reminders (24 hours and 2 hours before). Run every 15 minutes (cron or n8n).

    python scripts/reminders.py

For each reminder that is due, asks Tanmayi's policy gate whether a WhatsApp
message is allowed (consent, opt-out, frequency, sending hours). Allowed ones are
recorded in the shared DB as "queued_for_approval" so they are never queued twice;
blocked ones are recorded with the reason.

It does not send. WhatsApp needs a Meta-approved reminder template first, and
Tanmayi's engage service has none yet. Once it exists, a person approves the
queued reminders in Tanmayi's approval queue.
"""
import json
import os
import urllib.request
from datetime import datetime

DB = os.environ.get("SHARED_DB_URL", "http://127.0.0.1:8000").rstrip("/")
ENGAGE = os.environ.get("ENGAGE_URL", "http://127.0.0.1:4000").rstrip("/")
KEY = os.environ.get("ADMIN_API_KEY", "demo-admin-key")
TEMPLATE = "site_visit_reminder"  # to be approved in Meta and added to Tanmayi's templates


def call(method, url, body=None, headers=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def reminder_text(item):
    at = datetime.fromisoformat(item["scheduled_at"])
    when = "tomorrow" if item["kind"] == "24h" else "in about 2 hours"
    lead = item["lead"]
    return (f"Hello {lead['name']}, a reminder that your site visit to {lead['client']} is {when}, "
            f"{at:%a %d %b at %H:%M}. Reply STOP if you no longer want messages.")


def main():
    admin = {"X-Admin-Key": KEY}
    due = call("GET", f"{DB}/api/v1/reminders/due", headers=admin)
    for item in due:
        lead = item["lead"]
        text = reminder_text(item)
        verdict = call("POST", f"{ENGAGE}/api/policy/check", {
            "lead_id": lead["lead_id"],
            "message": {"text": text, "is_template": True, "template_name": TEMPLATE, "channel": "whatsapp"}})
        status = "queued_for_approval" if verdict.get("allowed") else "blocked"
        note = text if verdict.get("allowed") else f"{verdict.get('reason_code')}: {verdict.get('reason_detail')}"
        call("POST", f"{DB}/api/v1/leads/{lead['lead_id']}/contacts", {
            "channel": "whatsapp", "direction": "outbound", "status": status,
            "message_id": item["message_id"], "text": note}, headers=admin)
        print(f"{status:20} {item['kind']} reminder for {lead['name']} ({lead['lead_id']})")
    if not due:
        print("no reminders due")


if __name__ == "__main__":
    main()
