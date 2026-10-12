"""Connects Pratha's AI Lead Qualifier to the shared database without changing it.

Her qualifier works on a sheet (her n8n flow or her demo page: upload sheet,
AI scores each row, download CSV). This script moves leads between the shared
DB and that sheet format.

    python scripts/pratha_bridge.py export leads_to_score.csv --source radar
    (score the file in Pratha's qualifier page or n8n flow, download the result)
    python scripts/pratha_bridge.py import scored.csv

Import writes fit_score and fit_reasons back with PATCH, so every change is in
the audit trail. Rows without a lead_id or a score are skipped and listed.
"""
import csv
import json
import os
import sys
import urllib.parse
import urllib.request

DB = os.environ.get("SHARED_DB_URL", "http://127.0.0.1:8000").rstrip("/")
KEY = os.environ.get("ADMIN_API_KEY", "demo-admin-key")
# Column order from Pratha's sheet_template/leads_sheet_template.csv, plus lead_id to map rows back.
COLUMNS = ["Name", "Location", "Source URL", "Evidence", "Contact", "Qualification", "Lead Score",
           "Location pts", "Activity pts", "Credibility pts", "Completeness pts", "AI Reasoning", "Missing info", "lead_id"]
QUALIFIED_AT = 65  # Pratha's threshold


def call(method, path, body=None):
    req = urllib.request.Request(f"{DB}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Admin-Key": KEY, "X-Actor": "pratha_qualifier", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def to_row(lead):
    urls = [p.strip() for p in (lead.get("evidence") or "").split("|") if p.strip().startswith("http")]
    return {"Name": lead["company"] if lead["company"] != "Individual buyer" else lead["name"],
            "Location": lead["client"], "Source URL": urls[0] if urls else "",
            "Evidence": lead.get("business_requirements") or lead.get("evidence") or "",
            "Contact": " / ".join(x for x in (lead.get("phone"), lead.get("email") if "@lead.local" not in (lead.get("email") or "") else None, lead.get("linkedin_url")) if x),
            "lead_id": lead["lead_id"]}


def to_update(row):
    score = int(float(row["Lead Score"]))
    parts = [f"{k} {row[k]}" for k in ("Location pts", "Activity pts", "Credibility pts", "Completeness pts") if row.get(k)]
    reasons = [f"Pratha rubric: {row.get('Qualification') or ('Qualified' if score >= QUALIFIED_AT else 'Not qualified')} ({score}/100)"]
    if parts:
        reasons.append(", ".join(parts))
    for k in ("AI Reasoning", "Missing info"):
        if row.get(k):
            reasons.append(f"{k}: {row[k]}")
    update = {"fit_score": score, "fit_reasons": reasons}
    if score >= QUALIFIED_AT:
        update["stage"] = "qualified"
    return update


def export(path, source):
    params = urllib.parse.urlencode({"source": source, "limit": 500})
    leads = [l for l in call("GET", f"/api/v1/leads?{params}") if l["stage"] == "new" and not l["opted_out"]]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for lead in leads:
            w.writerow(to_row(lead))
    print(f"exported {len(leads)} lead(s) to {path}")


def import_(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if not row.get("lead_id") or not (row.get("Lead Score") or "").strip():
            print(f"skip  {row.get('Name')!r}: no lead_id or no score")
            continue
        lead = call("PATCH", f"/api/v1/leads/{row['lead_id']}", to_update(row))
        print(f"saved {lead['company']}: {lead['fit_score']}/100, stage {lead['stage']}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "export":
        export(sys.argv[2], sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else "radar")
    elif len(sys.argv) == 3 and sys.argv[1] == "import":
        import_(sys.argv[2])
    else:
        sys.exit(__doc__)
