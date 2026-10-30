# Day 29 interview script and outreach copy

## Outreach message

Subject: LLM eval cost tracking

Body:

Hi [Name],

I'm researching how teams handle LLM evaluation costs. I built a tool that plans and records spend per eval run, and I'm checking whether the problem is real before building more.

Do you run evals today? If yes, could I ask you five questions over 20 minutes? I'm not selling anything yet.

[Your name]

## Interview questions

Ask about past behavior, not hypotheticals.

1. Tell me about the last eval run you did. What did it cost?
2. Did you know the cost beforehand?
3. Has a run ever cost more than expected? What happened next?
4. How do you track this today?
5. Who would care if the cost was wrong?
6. What have you spent time or money on to fix this?

## Rules for the interviewer

- Don't pitch.
- Don't ask "would you use this". People say yes to be polite.
- Ask for something small instead: a pilot, an intro, or a payment commitment.

## Notes

- Ten interviews give direction, not proof. One interviewee can skew the result.
- Count only pilot agreements and price commitments for the scorecard.

## Recording and Scoring Interviews

Log each completed interview into the append-only evidence store:

```bash
python scripts/interview_scorecard.py add \
  --alias "P1" \
  --role "ML Lead" \
  --surprise-evidence "Eval run cost 3x estimate, Sept" \
  --pilot committed \
  --next-step "Share sample config by Nov 10"
```

Check validation progress and verdict:

```bash
python scripts/interview_scorecard.py score
```
Exit codes: `0` = GO, `2` = CONTINUE (< 8 interviews), `3` = NO_GO.

---

## Outreach Funnel Tracking

Track the funnel from initial message through booking:

```bash
# 1. When contacting someone
python scripts/outreach_tracker.py add --alias "P1" --status contacted --channel linkedin

# 2. When they reply, book, or decline
python scripts/outreach_tracker.py add --alias "P1" --status booked
python scripts/outreach_tracker.py add --alias "P1" --status interviewed

# 3. Check funnel health and follow-up deadlines
python scripts/outreach_tracker.py summary
```

Exit codes:
- `0` = All caught up.
- `2` = Attention needed (follow-up due after 5 days, or contact marked `interviewed` without a matching record in the interview scorecard).

### Outreach Template (Direct, No Fluff)

```text
Hi [first name],

I'm researching how teams budget for LLM evaluation runs. I'm not selling anything yet.

Could I ask you about [one specific, true reason you picked them] in a 20 minute call? I'm mainly interested in what happened the last time an eval bill surprised you.

If this isn't your area, no worries. A pointer to someone who handles it would also help.

[Your name]
```

**Follow-up (once, after 5 days):**

```text
Hi [first name], following up once on my note below. If the timing is bad, tell me and I'll stop.
```
