# RUNBOOK: Ledger Recovery Audit

**Who:** The ledger team (this is an internal safeguard, not a customer-facing feature).

**Cadence:** Weekly, every Monday at 07:00 UTC, using the cron entry below.

**Owner:** Fisayo (frontend) and the ops team (backup/packages/drill custody).

---

## 1. Where things live

| Item                         | Path / Location
|------------------------------|-----------------------------------------------------------------
| PostgreSQL backup dumps      | /PRIVATE/BACKUPS/*.dump (latest picked by ls -1t)
| Evidence packages (ZIP)      | /PRIVATE/PACKAGES (directory of Day 23-style .zips)
| Drill reports (JSON)         | esults/day25/ (or whatever --drill-dir points to)
| Audit environment            | /PRIVATE/ledger-audit.env (contains DATABASE_URL)
| History file                 | esults/day28/audit-history.jsonl (append-only)
| This runbook                 | RUNBOOK.md

---

## 2. Your cadence

1. **Backup** — after any batch of finished reservations, run pg_dump and write a new manifest with coverage (Day 25). Keep the dump file in /PRIVATE/BACKUPS/.
2. **Drill** — run the recovery drill monthly; reports go in esults/day25/.
3. **Audit** — runs automatically every Monday at 07:00 UTC (see cron below). The wrapper (day28.py) calls Day 27, records the result, and flags new or cleared gaps.
4. **Review** — open esults/day28/audit-history.jsonl and look for:
   - gap_ids that appear and then don't clear → investigate.
   - Repeated ERROR entries → the wrapper or its inputs are broken.
   - drill_fresh: false before the next drill is due → schedule a drill.

---

## 3. Fix by cause

| Symptom                                | Fix
|----------------------------------------|-----------------------------------------------------------------
| Wrapper exits ERROR                  | Check that /PRIVATE/ledger-audit.env exists and DATABASE_URL is valid; check that /PRIVATE/BACKUPS/ and /PRIVATE/PACKAGES/ are populated.
| gap_ids appear every run, never clear | The backup or packages are out of date. Regenerate the dump and ensure the package directory reflects the current evidence.
| drill_fresh: false                  | Run a new drill report and place it in --drill-dir.
| History file missing or empty          | The wrapper failed before appending. Rerun manually; check the exit code and stderr.

---

## 4. Never

- Re-run paid work to fix a recovery gap.
- Edit audit reports after the fact.
- Invent pricing or fabricate evidence.
- Store secrets in the crontab or the history file.

---

## 5. Cron entry (weekly, UTC)

`cron
17 7 * * 1 flock -n /tmp/ledger-audit.lock /Users/USER/ledger-audit/run-audit.sh
`

- Adjust the path to where you saved un-audit.sh.
- The lock guard prevents overlapping runs if a previous run is still going.
- A non-zero exit lets your scheduler's mail or alerting notice the failure.
- Do **not** put DATABASE_URL or any secret in the crontab itself; the script reads it from /PRIVATE/ledger-audit.env.

---

## 6. First run

1. Source the env file and test by hand:
`ash
set -a; . /PRIVATE/ledger-audit.env; set +a
python day28.py run \
  --backup /PRIVATE/BACKUPS/latest.dump \
  --packages /PRIVATE/PACKAGES \
  --drill-dir results/day25
`
2. Verify esults/day28/audit-history.jsonl has one line with status OK, ATTENTION, or ERROR.
3. Add the cron entry.

---

## 7. Definition of done

- [ ] Eight tests pass (day28.py test).
- [ ] un-audit.sh works by hand.
- [ ] A scheduled run appends to esults/day28/audit-history.jsonl.
- [ ] A forced ERROR reaches you through your scheduler (mail/alert).
- [ ] RUNBOOK.md exists and is reasonably up to date.
- [ ] You've answered: **who is the customer for this ledger?** (If there is no real customer, the best next step after this runbook is product work, not another safeguard.)

