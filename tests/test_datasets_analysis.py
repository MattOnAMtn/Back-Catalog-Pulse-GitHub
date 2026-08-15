from datetime import date, datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase

from analysis_engine import analyze_dataset
from dataset_store import list_datasets, load_dataset, report_to_dataset, save_dataset
from youtube_service import ReportResult


class DatasetAnalysisTest(TestCase):
    def sample_report(self):
        rows = [
            {"video_id": "m1", "title": "Headwaters | Mississippi Source to Sea Paddle Ep 1", "views": 100, "previous_views": 50, "likes": 3, "shares": 1, "comments": 1},
            {"video_id": "m2", "title": "Rapids | Mississippi Source to Sea Paddle Ep 2", "views": 80, "previous_views": 80, "likes": 2, "shares": 0, "comments": 0},
            {"video_id": "b1", "title": "Bonaire '24 Day 1 | Reef Dive", "views": 40, "previous_views": 20, "likes": 1, "shares": 0, "comments": 0},
        ]
        catalog = [
            {"video_id": "m1", "title": rows[0]["title"], "published_at": "2023-01-01"},
            {"video_id": "m2", "title": rows[1]["title"], "published_at": "2023-01-02"},
            {"video_id": "b1", "title": rows[2]["title"], "published_at": "2024-01-01"},
            {"video_id": "b2", "title": "Bonaire '24 Day 2 | Salt Pier Dive", "published_at": "2024-01-02"},
        ]
        return ReportResult(rows, catalog, date(2026, 8, 8), date(2026, 8, 14), date(2026, 8, 1), date(2026, 8, 7), True, datetime.now(timezone.utc))

    def test_round_trip_and_trip_detection(self):
        data = report_to_dataset(self.sample_report(), 90, 7)
        with TemporaryDirectory() as directory:
            filename = save_dataset(Path(directory), data)
            loaded = load_dataset(Path(directory), filename)
            listing = list_datasets(Path(directory))[0]
        self.assertEqual(loaded["query"], {"exclusion_days": 90, "window_days": 7})
        self.assertEqual(listing["eligible_count"], 4)
        self.assertEqual(listing["row_count"], 3)
        analysis = analyze_dataset(loaded)
        names = [trip["name"] for trip in analysis["trips"]]
        self.assertTrue(any("Mississippi Source to Sea" in name for name in names))
        self.assertTrue(any("Bonaire '24" in name for name in names))
        mississippi = next(trip for trip in analysis["trips"] if "Mississippi Source to Sea" in trip["name"])
        self.assertEqual(mississippi["episode_retention"], 80.0)
        self.assertEqual(mississippi["view_change"], 50)
        self.assertEqual(mississippi["subscriber_change"], 0)

    def test_playlist_membership_combines_different_title_patterns(self):
        report = self.sample_report()
        playlist = {"id": "PL_bonaire_2024", "title": "Bonaire 2024 Diving"}
        for video in report.catalog:
            if video["video_id"] in {"b1", "b2"}:
                video["playlists"] = [playlist]

        analysis = analyze_dataset(report_to_dataset(report, 90, 7))
        bonaire = next(trip for trip in analysis["trips"] if trip["name"] == "Bonaire 2024 Diving")
        self.assertEqual(bonaire["video_count"], 2)
        self.assertEqual(bonaire["grouping_basis"], "playlist")
        self.assertEqual(bonaire["playlist_details"], [playlist])
        self.assertEqual(len(bonaire["included_video_titles"]), 2)
