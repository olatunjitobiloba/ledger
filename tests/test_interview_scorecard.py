import tempfile
import unittest
from pathlib import Path

from scripts.interview_scorecard import add_interview, load, score


class InterviewScorecardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp()) / "i.jsonl"

    def fill(self, n: int, surprises: int = 0, pilots: int = 0) -> None:
        for i in range(n):
            add_interview(
                self.path,
                f"p{i}",
                "ML engineer",
                "bill was 3x estimate in March" if i < surprises else "",
                "committed" if i < pilots else "none",
                "send data sample by Nov 10" if i < pilots else "",
            )

    def test_continue_below_eight(self) -> None:
        self.fill(5, 5, 5)
        self.assertEqual(score(load(self.path))["verdict"], "CONTINUE")

    def test_go(self) -> None:
        self.fill(8, 4, 2)
        self.assertEqual(score(load(self.path))["verdict"], "GO")

    def test_no_go(self) -> None:
        self.fill(8, 3, 2)
        self.assertEqual(score(load(self.path))["verdict"], "NO_GO")

    def test_interested_is_not_committed(self) -> None:
        add_interview(self.path, "a", "CTO", pilot="interested")
        self.assertEqual(score(load(self.path))["committed_pilots"], 0)

    def test_committed_needs_next_step(self) -> None:
        with self.assertRaises(ValueError):
            add_interview(self.path, "a", "CTO", pilot="committed")

    def test_duplicate_alias_rejected(self) -> None:
        add_interview(self.path, "a", "CTO")
        with self.assertRaises(ValueError):
            add_interview(self.path, "A", "CTO")


if __name__ == "__main__":
    unittest.main()

