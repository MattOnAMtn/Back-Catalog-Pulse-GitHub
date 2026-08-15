from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from youtube_service import build_report


class FakeRequest:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class FakeAnalytics:
    def __init__(self): self.calls = []
    def reports(self): return self
    def query(self, **kwargs):
        self.calls.append(kwargs)
        current = len(self.calls) == 1
        rows = [["old", 150, 10, 3, 4], ["new", 999, 20, 9, 8]] if current else [["old", 50, 5, 1, 2]]
        return FakeRequest({"rows": rows})


class ReportTest(TestCase):
    def test_filters_recent_upload_and_calculates_surge(self):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        new = datetime.now(timezone.utc)
        analytics = FakeAnalytics()
        with patch("youtube_service.build", side_effect=[object(), analytics]), patch(
            "youtube_service._playlist_memberships", return_value={}
        ), patch(
            "youtube_service._all_uploads",
            return_value={
                "old": {"title": "Old hit", "published_at": old, "thumbnail": ""},
                "new": {"title": "New upload", "published_at": new, "thumbnail": ""},
            },
        ):
            result = build_report(object(), exclusion_days=30, window_days=7)
        self.assertEqual([row["video_id"] for row in result.rows], ["old"])
        self.assertEqual(result.rows[0]["surge_percent"], 200.0)
        self.assertEqual(result.rows[0]["previous_views"], 50)
        self.assertEqual(result.excluded_recent_count, 1)
        self.assertIsNotNone(result.published_cutoff_date)
        self.assertEqual(len(analytics.calls), 4)
        self.assertEqual(analytics.calls[0]["filters"], "video==old")
        self.assertNotIn("startIndex", analytics.calls[0])
        self.assertEqual(analytics.calls[2]["dimensions"], "insightTrafficSourceType")
        self.assertEqual(analytics.calls[3]["dimensions"], "insightTrafficSourceDetail")
        self.assertEqual(
            result.start_date,
            result.end_date.replace() - __import__("datetime").timedelta(days=6),
        )
