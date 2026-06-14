from datetime import date, time
import unittest

from app.services import full_auto


class TestFullAuto(unittest.TestCase):
    def test_parse_topics_removes_blanks_and_duplicates(self):
        topics = full_auto.parse_topics("First\n\nSecond\nFirst\n  Third  ")

        self.assertEqual(topics, ["First", "Second", "Third"])

    def test_build_schedule_uses_each_daily_time_before_next_day(self):
        topics = ["One", "Two", "Three", "Four", "Five"]

        schedule = full_auto.build_schedule(
            topics,
            date(2026, 6, 15),
            [time(20, 0), time(8, 0)],
        )

        self.assertEqual(
            [item["publish_label"] for item in schedule],
            [
                "2026-06-15 08:00",
                "2026-06-15 20:00",
                "2026-06-16 08:00",
                "2026-06-16 20:00",
                "2026-06-17 08:00",
            ],
        )


if __name__ == "__main__":
    unittest.main()
