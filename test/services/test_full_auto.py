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

    def test_build_schedule_supports_more_than_two_daily_times(self):
        topics = ["One", "Two", "Three", "Four"]

        schedule = full_auto.build_schedule(
            topics,
            date(2026, 6, 15),
            [time(18, 0), time(9, 0), time(12, 30)],
        )

        self.assertEqual(
            [item["publish_label"] for item in schedule],
            [
                "2026-06-15 09:00",
                "2026-06-15 12:30",
                "2026-06-15 18:00",
                "2026-06-16 09:00",
            ],
        )

    def test_build_duration_script_requirement_sets_word_range(self):
        requirement = full_auto.build_duration_script_requirement(30)

        self.assertIn("about 30 seconds", requirement)
        self.assertIn("between 70 and 85 spoken words", requirement)
        self.assertIn("same length", requirement)

    def test_build_duration_script_requirement_defaults_to_30_seconds(self):
        requirement = full_auto.build_duration_script_requirement(999)

        self.assertIn("about 30 seconds", requirement)
        self.assertIn("between 70 and 85 spoken words", requirement)


if __name__ == "__main__":
    unittest.main()
