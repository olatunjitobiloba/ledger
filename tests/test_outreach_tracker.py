from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.outreach_tracker import add_event, load, summarize

D1, D7 = date(2026, 11, 1), date(2026, 11, 7)


class OutreachTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "o.jsonl"

    def test_first_event_must_be_contacted(self) -> None:
        with self.assertRaises(ValueError):
            add_event(self.path, "a", "replied")

    def test_cannot_contact_twice(self) -> None:
        add_event(self.path, "a", "contacted", today=D1)
        with self.assertRaises(ValueError):
            add_event(self.path, "A", "contacted", today=D1)

    def test_latest_status_wins(self) -> None:
        add_event(self.path, "a", "contacted", today=D1)
        add_event(self.path, "a", "booked", today=D1)
        s = summarize(load(self.path), today=D1)
        self.assertEqual(s["counts"]["booked"], 1)
        self.assertEqual(s["counts"]["contacted"], 0)

    def test_follow_up_due_after_five_days(self) -> None:
        add_event(self.path, "a", "contacted", today=D1)
        s = summarize(load(self.path), today=D7)
        self.assertEqual(s["follow_up_due"], ["a"])
        self.assertEqual(s["exit_code"], 2)

    def test_interviewed_must_exist_in_day30(self) -> None:
        add_event(self.path, "a", "contacted", today=D1)
        add_event(self.path, "a", "interviewed", today=D1)
        s = summarize(load(self.path), interview_aliases=[], today=D1)
        self.assertEqual(s["interviewed_missing_from_day30"], ["a"])
        ok = summarize(load(self.path), interview_aliases=["A"], today=D1)
        self.assertEqual(ok["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()

