from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


GENERIC = {
    "the adventure", "trip update", "travel vlog", "channel update", "gear review",
    "planning", "highlights", "introduction", "overview",
}
GENERIC_PLAYLISTS = {
    "uploads", "popular uploads", "all videos", "videos", "shorts", "youtube shorts",
    "hiking", "diving", "paddling", "travel", "adventures", "favorites",
}
STOPWORDS = {
    "the", "and", "for", "from", "with", "this", "that", "into", "our", "your", "day",
    "episode", "video", "trip", "part", "paddle", "dive", "ep", "of", "to", "in", "on", "a",
}


def _clean_segment(segment: str) -> str:
    value = segment.lower().replace("&", " and ")
    value = re.sub(r"\b(?:episode|ep\.?|part|day)\s*#?\s*\d+[a-z]?\b", " ", value)
    value = re.sub(r"\b(?:episode|ep\.?|part)\b\s*$", " ", value)
    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    return " ".join(value.split()).strip()


def _display_name(cleaned: str) -> str:
    small = {"and", "to", "of", "the", "from"}
    words = cleaned.split()
    return " ".join(word if index and word in small else word.capitalize() for index, word in enumerate(words))


def _episode_number(title: str) -> int | None:
    match = re.search(r"\b(?:episode|ep\.?|part)\s*#?\s*(\d+)\b", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _candidates(title: str) -> set[str]:
    segments = [_clean_segment(part) for part in re.split(r"\s*[|–—:]\s*", title)]
    output = set()
    for segment in segments:
        words = segment.split()
        if len(words) >= 2 and segment not in GENERIC:
            output.add(segment)
        # Series names are often the stable trailing phrase before an episode number.
        if len(words) >= 5:
            output.add(" ".join(words[-5:]))
            output.add(" ".join(words[-4:]))
    return output


def analyze_dataset(dataset: dict[str, Any], histories: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    report = dataset["report"]
    histories = histories or []
    catalog = report.get("catalog", report["rows"])
    current_by_id = {row["video_id"]: row for row in report["rows"]}
    candidate_videos: dict[str, set[str]] = defaultdict(set)
    playlist_videos: dict[str, set[str]] = defaultdict(set)
    playlist_display: dict[str, dict[str, str]] = {}
    for video in catalog:
        for candidate in _candidates(video["title"]):
            candidate_videos[candidate].add(video["video_id"])
        for playlist in video.get("playlists", []):
            cleaned = _clean_segment(playlist["title"])
            if cleaned and cleaned not in GENERIC_PLAYLISTS and len(cleaned.split()) >= 2:
                playlist_videos[cleaned].add(video["video_id"])
                playlist_display[cleaned] = playlist

    recurring = {name: ids for name, ids in candidate_videos.items() if len(ids) >= 2}
    recurring_playlists = {name: ids for name, ids in playlist_videos.items() if len(ids) >= 2}
    assignments: dict[str, str] = {}
    assignment_basis: dict[str, str] = {}
    # A specific owned playlist is stronger evidence than title phrasing. Prefer
    # descriptive playlist names and smaller, more focused playlist membership.
    playlist_ranked = sorted(
        recurring_playlists,
        key=lambda name: (len(name.split()), -len(recurring_playlists[name]), len(name)),
        reverse=True,
    )
    for name in playlist_ranked:
        for video_id in recurring_playlists[name]:
            if video_id not in assignments:
                assignments[video_id] = name
                assignment_basis[video_id] = "playlist"

    # Fall back to repeated title phrases for videos without a useful playlist.
    ranked = sorted(recurring, key=lambda name: (len(recurring[name]), len(name.split()), len(name)), reverse=True)
    for name in ranked:
        for video_id in recurring[name]:
            current = assignments.get(video_id)
            if current is None:
                assignments[video_id] = name
                assignment_basis[video_id] = "title"

    groups: dict[str, dict[str, Any]] = {}
    for name in set(assignments.values()):
        catalog_ids = {video_id for video_id, assigned in assignments.items() if assigned == name}
        active_rows = [current_by_id[video_id] for video_id in catalog_ids if video_id in current_by_id]
        group_catalog = [video for video in catalog if video["video_id"] in catalog_ids]
        playlist_details = {
            playlist["id"]: playlist
            for video in group_catalog
            for playlist in video.get("playlists", [])
        }
        episodes = sorted(
            [(_episode_number(row["title"]), row["views"], row["title"]) for row in active_rows if _episode_number(row["title"]) is not None],
            key=lambda episode: episode[0],
        )
        episode_retention = None
        if len(episodes) >= 2 and episodes[0][1] > 0:
            later_average = sum(episode[1] for episode in episodes[1:]) / (len(episodes) - 1)
            episode_retention = round(later_average / episodes[0][1] * 100, 1)
        views = sum(row["views"] for row in active_rows)
        previous_views = sum(row["previous_views"] for row in active_rows)
        subscribers_gained = sum(row.get("subscribers_gained", 0) for row in active_rows)
        subscribers_lost = sum(row.get("subscribers_lost", 0) for row in active_rows)
        groups[name] = {
            "name": _display_name(name),
            "video_count": len(catalog_ids),
            "active_count": len(active_rows),
            "views": views,
            "likes": sum(row["likes"] for row in active_rows),
            "comments": sum(row["comments"] for row in active_rows),
            "shares": sum(row["shares"] for row in active_rows),
            "watch_hours": round(sum(row.get("watch_minutes", 0) for row in active_rows) / 60, 1),
            "subscribers_gained": subscribers_gained,
            "subscribers_lost": subscribers_lost,
            "subscriber_change": subscribers_gained - subscribers_lost,
            "previous_views": previous_views,
            "view_change": views - previous_views,
            "change_percent": None if previous_views == 0 else round((views - previous_views) / previous_views * 100, 1),
            "engagement_rate": round(
                sum(row["likes"] + row["comments"] + row["shares"] for row in active_rows) / views * 100,
                2,
            ) if views else 0,
            "episode_retention": episode_retention,
            "numbered_episodes_active": len(episodes),
            "playlist_details": sorted(playlist_details.values(), key=lambda playlist: playlist["title"].lower()),
            "included_video_titles": sorted(video["title"] for video in group_catalog),
            "grouping_basis": "playlist" if any(assignment_basis.get(video_id) == "playlist" for video_id in catalog_ids) else "title pattern",
        }

    trips = sorted(groups.values(), key=lambda group: (group["views"], group["active_count"], group["video_count"]), reverse=True)
    active_trips = [trip for trip in trips if trip["views"] > 0]
    top_videos = sorted(report["rows"], key=lambda row: row["views"], reverse=True)[:5]
    total_views = sum(row["views"] for row in report["rows"])
    total_previous = sum(row["previous_views"] for row in report["rows"])
    overall_change = None if total_previous == 0 else round((total_views - total_previous) / total_previous * 100, 1)
    for trip in trips:
        trip["view_share"] = round(trip["views"] / total_views * 100, 1) if total_views else 0

    historical_activity: Counter[str] = Counter()
    history_points = []
    for old in histories:
        old_rows = old.get("report", {}).get("rows", [])
        for row in old_rows:
            if row.get("views", 0) > 0:
                historical_activity[row["video_id"]] += 1
        history_points.append({
            "generated_at": old["report"]["generated_at"],
            "views": sum(row.get("views", 0) for row in old_rows),
            "active_videos": len(old_rows),
        })

    classifications = {"surging": [], "evergreen": [], "declining": [], "newly_active": [], "steady": []}
    for row in report["rows"]:
        change = row.get("surge_percent")
        if row.get("previous_views", 0) == 0:
            bucket = "newly_active"
        elif change is not None and change >= 25:
            bucket = "surging"
        elif change is not None and change <= -25:
            bucket = "declining"
        elif historical_activity[row["video_id"]] >= 3:
            bucket = "evergreen"
        else:
            bucket = "steady"
        classifications[bucket].append(row)
    for rows in classifications.values():
        rows.sort(key=lambda row: row["views"], reverse=True)

    topic_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report["rows"]:
        words = set(re.findall(r"[a-z0-9']+", row["title"].lower())) - STOPWORDS
        for word in words:
            if len(word) >= 4 and not word.isdigit():
                topic_rows[word].append(row)
    topic_patterns = []
    for word, matching in topic_rows.items():
        if len(matching) >= 2:
            topic_patterns.append({
                "topic": word.title(),
                "videos": len(matching),
                "views": sum(row["views"] for row in matching),
                "average_views": round(sum(row["views"] for row in matching) / len(matching), 1),
            })
    topic_patterns.sort(key=lambda topic: (topic["views"], topic["videos"]), reverse=True)

    insights = report.get("insights", {})
    traffic_sources = insights.get("traffic_sources", [])
    search_terms = insights.get("search_terms", [])
    recommendations = []
    if active_trips and active_trips[0]["view_share"] >= 25:
        recommendations.append(f"Feature {active_trips[0]['name']} prominently: it supplies {active_trips[0]['view_share']}% of current back-catalog views. Check its playlist order, end screens, and pinned comments.")
    if classifications["surging"]:
        video = classifications["surging"][0]
        recommendations.append(f"Use “{video['title']}” as a gateway: it is up {video['surge_percent']}% and can direct viewers to the related trip or next episode.")
    engaged = sorted(report["rows"], key=lambda row: ((row["likes"] + row["comments"] + row["shares"]) / row["views"]) if row["views"] else 0, reverse=True)
    if engaged and engaged[0]["views"] >= 10:
        rate = (engaged[0]["likes"] + engaged[0]["comments"] + engaged[0]["shares"]) / engaged[0]["views"] * 100
        recommendations.append(f"“{engaged[0]['title']}” has the strongest engagement among meaningful active videos ({rate:.1f} interactions per 100 views); consider a follow-up or community post.")
    dormant = [trip for trip in trips if trip["views"] == 0]
    if dormant:
        recommendations.append(f"Consider refreshing a dormant series such as {dormant[0]['name']} with a retrospective, playlist update, Short, or new pinned comment.")
    if search_terms:
        recommendations.append(f"Current YouTube search demand is led by “{search_terms[0]['term']}”; reuse that language naturally where it accurately describes related videos.")

    if active_trips:
        leaders = active_trips[:3]
        leader_text = ", ".join(f"{trip['name']} ({trip['views']:,} views)" for trip in leaders)
        trend = "up" if overall_change is not None and overall_change > 0 else "down" if overall_change is not None and overall_change < 0 else "about even"
        summary = (
            f"Back-catalog viewing is {trend} versus the preceding comparison window"
            + (f" ({overall_change:+.1f}%). " if overall_change is not None else ". ")
            + f"The most active detected trip series are {leader_text}."
        )
    else:
        summary = "No recurring trip series with activity were detected in this dataset."

    return {
        "summary": summary,
        "total_views": total_views,
        "overall_change": overall_change,
        "trips": trips,
        "top_videos": top_videos,
        "classifications": classifications,
        "classification_counts": {name: len(rows) for name, rows in classifications.items()},
        "topic_patterns": topic_patterns[:12],
        "recommendations": recommendations,
        "traffic_sources": traffic_sources,
        "search_terms": search_terms,
        "history_points": sorted(history_points, key=lambda point: point["generated_at"]),
        "method_note": "Trips are detected from title phrases repeated across two or more catalog videos; review names as pattern-based suggestions.",
    }
