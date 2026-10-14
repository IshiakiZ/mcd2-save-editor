"""The Soul Storm timetable: which area has a storm when, from the game's own table, on fixed clocks."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dungeons2_editor import soul_storms

UTC = timezone.utc
MOUNTAIN = timezone(timedelta(hours=-6), "MDT")  # the developer's clock in October
TURN = ["Howling Woods", "Singer's Meadow", "Rainy Plains", "Humbler Huskland", "Lullaby Hills", "Frozen Highlands", "Honeycomb Fields"]


def at(*parts):
    return datetime(*parts, tzinfo=UTC)


class TimetableTests(unittest.TestCase):
    def setUp(self):
        self.table = soul_storms.load()

    def test_the_timetable_is_the_games(self):
        self.assertEqual(self.table.starts, at(2026, 1, 1))
        self.assertEqual((self.table.every, self.table.lasts), (timedelta(minutes=40), timedelta(minutes=20)))
        self.assertEqual(self.table.areas, (
            "SW.Area.Forest.A1", "SW.Area.Meadow.A1", "SW.Area.Plains.A2", "SW.Area.Carapace.A1",
            "SW.Area.Meadow.A2", "SW.Area.Desert.A1", "SW.Area.Plains.A1",
        ))

    def test_every_area_goes_by_the_games_name(self):
        self.assertEqual([soul_storms.storm(self.table, number).name for number in range(7)], TURN)

    def test_the_first_storms(self):
        storms = soul_storms.coming(self.table, at(2026, 1, 1, 0, 5), 3)
        self.assertEqual([(storm.number, storm.name, storm.starts, storm.ends) for storm in storms], [
            (0, "Howling Woods", at(2026, 1, 1, 0, 0), at(2026, 1, 1, 0, 20)),
            (1, "Singer's Meadow", at(2026, 1, 1, 0, 40), at(2026, 1, 1, 1, 0)),
            (2, "Rainy Plains", at(2026, 1, 1, 1, 20), at(2026, 1, 1, 1, 40)),
        ])
        self.assertTrue(storms[0].is_on(at(2026, 1, 1, 0, 5)))

    def test_a_storm_is_on_for_twenty_minutes_and_the_next_comes_twenty_later(self):
        self.assertEqual(soul_storms.coming(self.table, at(2026, 1, 1, 0, 19, 59), 1)[0].number, 0)
        between = soul_storms.coming(self.table, at(2026, 1, 1, 0, 20), 1)[0]  # the storm is over on the twentieth minute
        self.assertEqual((between.number, between.is_on(at(2026, 1, 1, 0, 20))), (1, False))
        self.assertEqual(soul_storms.coming(self.table, at(2026, 1, 1, 0, 40), 1)[0].number, 1)

    def test_the_turn_goes_round(self):
        storms = soul_storms.coming(self.table, at(2026, 1, 1, 4, 30))  # one round: each area once
        self.assertEqual([storm.name for storm in storms], TURN)
        self.assertEqual(storms[0].starts, at(2026, 1, 1, 4, 40))

    def test_a_day_long_after_the_start(self):
        # 2026-10-14 21:21 UTC is 286 days and 21 hours 21 minutes on: storm 10,328, the fourth area of its turn.
        storm = soul_storms.coming(self.table, at(2026, 10, 14, 21, 21), 1)[0]
        self.assertEqual((storm.number, storm.name, storm.starts, storm.ends), (10328, "Humbler Huskland", at(2026, 10, 14, 21, 20), at(2026, 10, 14, 21, 40)))

    def test_before_the_timetable_starts_it_counts_back(self):
        storms = soul_storms.coming(self.table, at(2025, 12, 31, 23, 25), 2)
        self.assertEqual([(storm.number, storm.name, storm.starts) for storm in storms], [
            (-1, "Honeycomb Fields", at(2025, 12, 31, 23, 20)), (0, "Howling Woods", at(2026, 1, 1)),
        ])

    def test_an_areas_next_storm(self):
        self.assertEqual(soul_storms.next_in(self.table, "SW.Area.Desert.A1", at(2026, 1, 1, 0, 5)).starts, at(2026, 1, 1, 3, 20))
        self.assertEqual(soul_storms.next_in(self.table, "SW.Area.Forest.A1", at(2026, 1, 1, 0, 5)).starts, at(2026, 1, 1))  # on now
        with self.assertRaises(ValueError):
            soul_storms.next_in(self.table, "SW.Area.Town", at(2026, 1, 1))

    def test_a_moment_without_a_time_zone_is_the_pcs(self):
        local = at(2026, 1, 1, 0, 5).astimezone().replace(tzinfo=None)
        self.assertEqual(soul_storms.coming(self.table, local, 1)[0].number, 0)


class WordsTests(unittest.TestCase):
    def setUp(self):
        self.table = soul_storms.load()

    def test_how_long(self):
        self.assertEqual(
            [soul_storms.wait_text(seconds) for seconds in (0, 59, 60, 61, 25 * 60, 60 * 60, 61 * 60, 125 * 60, 4 * 3600 + 40 * 60)],
            ["under a minute", "under a minute", "1 minute", "1 minute", "25 minutes", "1 hour", "1 hour 1 minute", "2 hours 5 minutes", "4 hours 40 minutes"],
        )

    def test_a_time_on_the_clock(self):
        now = at(2026, 10, 14, 21, 21)  # 15:21 in the Rockies
        self.assertEqual(soul_storms.clock_text(at(2026, 10, 14, 21, 40), now, MOUNTAIN), "15:40")
        self.assertEqual(soul_storms.clock_text(at(2026, 10, 15, 6, 20), now, MOUNTAIN), "Thu 00:20")  # the next day there
        self.assertEqual(soul_storms.clock_text(at(2026, 10, 15, 0, 20), now, MOUNTAIN), "18:20")  # still the same day there,
        self.assertEqual(soul_storms.clock_text(at(2026, 10, 15, 0, 20), now, UTC), "Thu 00:20")  # and the next in UTC

    def test_the_storm_now(self):
        self.assertEqual(
            soul_storms.now_text(self.table, at(2026, 10, 14, 21, 21), MOUNTAIN),
            "A Soul Storm is on in Humbler Huskland until 15:40 (19 minutes left).",
        )

    def test_no_storm_now(self):
        self.assertEqual(
            soul_storms.now_text(self.table, at(2026, 10, 14, 21, 45), MOUNTAIN),
            "No Soul Storm is on now. The next is in Lullaby Hills at 16:00, in 15 minutes.",
        )

    def test_the_pcs_time_zone_has_a_name(self):
        self.assertTrue(soul_storms.zone_name(at(2026, 10, 14, 21, 21)))


class TimetableFileTests(unittest.TestCase):
    def write(self, **changes):
        data = {"starts": "2026-01-01T00:00:00Z", "every_seconds": 2400, "lasts_seconds": 1200, "areas": ["SW.Area.Forest.A1"]}
        data.update(changes)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "soul_storms.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_a_timetable_of_another_shape_is_read_as_it_says(self):
        table = soul_storms.load(self.write(every_seconds=3600, lasts_seconds=600, areas=["SW.Area.Forest.A1", "SW.Area.Town"]))
        storms = soul_storms.coming(table, at(2026, 1, 1, 0, 15), 2)
        self.assertEqual([(storm.area, storm.starts) for storm in storms], [("SW.Area.Town", at(2026, 1, 1, 1)), ("SW.Area.Forest.A1", at(2026, 1, 1, 2))])

    def test_a_timetable_that_cant_be(self):
        for changes in ({"lasts_seconds": 3000}, {"lasts_seconds": 0}, {"every_seconds": 0}, {"areas": []}, {"starts": "2026-01-01T00:00:00"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                soul_storms.load(self.write(**changes))


if __name__ == "__main__":
    unittest.main()
