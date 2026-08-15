from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


@dataclass(frozen=True)
class ReportResult:
    rows: list[dict[str, Any]]
    catalog: list[dict[str, Any]]
    start_date: date
    end_date: date
    previous_start_date: date
    previous_end_date: date
    shares_available: bool
    generated_at: datetime
    excluded_recent_count: int = 0
    insights: dict[str, Any] = field(default_factory=dict)
    published_cutoff_date: str | None = None


def load_credentials(token_path: Path) -> Credentials | None:
    if not token_path.exists():
        return None
    credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    return credentials if credentials and credentials.valid else credentials


def _all_uploads(youtube) -> dict[str, dict[str, Any]]:
    channel = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = channel.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel was found for the signed-in account.")

    playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    video_ids: list[str] = []
    page_token = None
    while True:
        response = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        video_ids.extend(item["contentDetails"]["videoId"] for item in response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    videos: dict[str, dict[str, Any]] = {}
    for offset in range(0, len(video_ids), 50):
        response = youtube.videos().list(
            part="snippet",
            id=",".join(video_ids[offset : offset + 50]),
            maxResults=50,
        ).execute()
        for item in response.get("items", []):
            snippet = item["snippet"]
            published_at = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
            videos[item["id"]] = {
                "title": snippet["title"],
                "published_at": published_at,
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
            }
    return videos


def _analytics_rows(
    analytics,
    start_date: date,
    end_date: date,
    video_ids: list[str],
) -> tuple[dict[str, dict[str, int]], bool]:
    if not video_ids:
        return {}, True
    requested_metrics = "views,likes,shares,comments,estimatedMinutesWatched,subscribersGained,subscribersLost"
    shares_available = True
    try:
        rows = _filtered_reports(analytics, start_date, end_date, requested_metrics, video_ids)
    except HttpError as error:
        # Some channel/report combinations do not expose shares. Keep the rest useful.
        if error.resp.status not in (400, 403):
            raise
        shares_available = False
        requested_metrics = "views,likes,comments,estimatedMinutesWatched,subscribersGained,subscribersLost"
        rows = _filtered_reports(analytics, start_date, end_date, requested_metrics, video_ids)

    metrics = requested_metrics.split(",")
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        result[row[0]] = {name: int(value or 0) for name, value in zip(metrics, row[1:])}
        if not shares_available:
            result[row[0]]["shares"] = 0
    return result, shares_available


def _filtered_reports(
    analytics,
    start_date: date,
    end_date: date,
    metrics: str,
    video_ids: list[str],
) -> list[list[Any]]:
    output: list[list[Any]] = []
    # YouTube supports up to 500 IDs in a video filter. Filtering explicit IDs
    # avoids unreliable startIndex pagination on the per-video channel report.
    for offset in range(0, len(video_ids), 500):
        batch = video_ids[offset : offset + 500]
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics=metrics,
            dimensions="video",
            filters=f"video=={','.join(batch)}",
            sort="-views",
            maxResults=500,
        ).execute()
        output.extend(response.get("rows", []))
    return output


def _supplemental_insights(analytics, start_date: date, end_date: date) -> dict[str, Any]:
    insights: dict[str, Any] = {"traffic_sources": [], "search_terms": [], "available": True}
    try:
        traffic = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="insightTrafficSourceType",
            sort="-views",
            maxResults=25,
        ).execute()
        insights["traffic_sources"] = [
            {"source": row[0], "views": int(row[1] or 0), "watch_minutes": float(row[2] or 0)}
            for row in traffic.get("rows", [])
        ]
    except HttpError as error:
        insights["available"] = False
        insights["traffic_source_error"] = str(error)

    try:
        search = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="insightTrafficSourceDetail",
            filters="insightTrafficSourceType==YT_SEARCH",
            sort="-views",
            maxResults=25,
        ).execute()
        insights["search_terms"] = [
            {"term": row[0], "views": int(row[1] or 0), "watch_minutes": float(row[2] or 0)}
            for row in search.get("rows", [])
        ]
    except HttpError as error:
        insights["search_terms_available"] = False
        insights["search_term_error"] = str(error)
    return insights


def build_report(credentials: Credentials, exclusion_days: int, window_days: int) -> ReportResult:
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)

    today = datetime.now(timezone.utc).date()
    # Analytics data for the current UTC day is usually incomplete, so use yesterday.
    end_date = today - timedelta(days=1)
    start_date = end_date - timedelta(days=window_days - 1)
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)
    published_cutoff = datetime.now(timezone.utc) - timedelta(days=exclusion_days)

    uploads = _all_uploads(youtube)
    eligible_ids = [
        video_id
        for video_id, video in uploads.items()
        if video["published_at"] <= published_cutoff
    ]
    current, shares_current = _analytics_rows(analytics, start_date, end_date, eligible_ids)
    previous, shares_previous = _analytics_rows(analytics, previous_start, previous_end, eligible_ids)
    rows: list[dict[str, Any]] = []

    for video_id, metrics in current.items():
        video = uploads.get(video_id)
        if not video or video["published_at"] > published_cutoff:
            continue
        prior = previous.get(video_id, {})
        views = metrics.get("views", 0)
        prior_views = prior.get("views", 0)
        surge_percent = None if prior_views == 0 else round((views - prior_views) / prior_views * 100, 1)
        age_days = (today - video["published_at"].date()).days
        rows.append({
            "video_id": video_id,
            "title": video["title"],
            "published_at": video["published_at"].date().isoformat(),
            "published_timestamp": int(video["published_at"].timestamp()),
            "age_days": age_days,
            "thumbnail": video["thumbnail"],
            "views": views,
            "likes": metrics.get("likes", 0),
            "shares": metrics.get("shares", 0),
            "comments": metrics.get("comments", 0),
            "watch_minutes": metrics.get("estimatedMinutesWatched", 0),
            "subscribers_gained": metrics.get("subscribersGained", 0),
            "subscribers_lost": metrics.get("subscribersLost", 0),
            "previous_views": prior_views,
            "surge_percent": surge_percent,
        })

    rows.sort(key=lambda row: row["views"], reverse=True)
    catalog = [
        {
            "video_id": video_id,
            "title": video["title"],
            "published_at": video["published_at"].date().isoformat(),
        }
        for video_id, video in uploads.items()
        if video["published_at"] <= published_cutoff
    ]
    return ReportResult(
        rows=rows,
        catalog=catalog,
        start_date=start_date,
        end_date=end_date,
        previous_start_date=previous_start,
        previous_end_date=previous_end,
        shares_available=shares_current and shares_previous,
        generated_at=datetime.now(timezone.utc),
        excluded_recent_count=sum(1 for video in uploads.values() if video["published_at"] > published_cutoff),
        insights=_supplemental_insights(analytics, start_date, end_date),
        published_cutoff_date=published_cutoff.date().isoformat(),
    )
