from __future__ import annotations

import os
import secrets
import logging
import threading
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_from_directory, session, url_for
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

from youtube_service import SCOPES, build_report, load_credentials
from analysis_engine import analyze_dataset
from dataset_store import import_dataset, list_datasets, load_dataset, report_to_dataset, save_dataset


BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
DATASETS_DIR = BASE_DIR / "datasets"

# OAuthlib requires HTTPS by default. Google explicitly permits HTTP loopback
# redirects for installed/local applications, and this server only binds to
# 127.0.0.1 (it is not exposed to the network).
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

load_dotenv(BASE_DIR / ".env")
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
file_handler = logging.FileHandler(BASE_DIR / "back_catalog_pulse.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
QUERY_LOCK = threading.Lock()


@app.template_filter("local_timestamp")
def local_timestamp(value):
    if not value:
        return "Unknown time"
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%b %-d, %Y · %-I:%M %p")


def _flow(state: str | None = None) -> Flow:
    return Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for("oauth_callback", _external=True),
    )


def _credentials():
    credentials = load_credentials(TOKEN_PATH)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_PATH.write_text(credentials.to_json())
    return credentials


def _report_view(data):
    report = dict(data["report"])
    report.setdefault("excluded_recent_count", None)
    for key in ("start_date", "end_date", "previous_start_date", "previous_end_date"):
        report[key] = date.fromisoformat(report[key])
    report["generated_at"] = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
    cutoff_value = report.get("published_cutoff_date")
    report["published_cutoff_date"] = date.fromisoformat(cutoff_value) if cutoff_value else report["generated_at"].date() - timedelta(days=data["query"]["exclusion_days"])
    report["rows"] = sorted(report["rows"], key=lambda row: row["views"], reverse=True)
    report["eligible_count"] = len(report.get("catalog", report["rows"]))
    report["total_channel_videos"] = report["eligible_count"] + report["excluded_recent_count"] if report["excluded_recent_count"] is not None else None
    report["inactive_eligible_count"] = max(report["eligible_count"] - len(report["rows"]), 0)
    return SimpleNamespace(**report)


def _render_saved(data, filename, analysis=None, status=None):
    query = data["query"]
    return render_template(
        "index.html",
        connected=True,
        report=_report_view(data),
        exclusion_days=query["exclusion_days"],
        window_days=query["window_days"],
        datasets=list_datasets(DATASETS_DIR),
        selected_dataset=filename,
        analysis=analysis,
        status=status,
    )


@app.route("/")
def index():
    exclusion_days = max(1, min(request.args.get("exclude", 90, type=int), 36500))
    window_days = max(1, min(request.args.get("window", 30, type=int), 365))
    credentials = _credentials()
    if not credentials:
        return render_template("index.html", connected=False, missing_secret=not CLIENT_SECRET_PATH.exists())
    datasets = list_datasets(DATASETS_DIR)
    selected = request.args.get("dataset") or (datasets[0]["filename"] if datasets else None)
    if selected:
        try:
            return _render_saved(load_dataset(DATASETS_DIR, selected), selected)
        except (ValueError, OSError) as error:
            return render_template("index.html", connected=True, datasets=datasets, exclusion_days=exclusion_days, window_days=window_days, error=str(error)), 400
    return render_template("index.html", connected=True, datasets=datasets, exclusion_days=exclusion_days, window_days=window_days)


@app.route("/query")
def new_query():
    exclusion_days = max(1, min(request.args.get("exclude", 90, type=int), 36500))
    window_days = max(1, min(request.args.get("window", 30, type=int), 365))
    credentials = _credentials()
    if not credentials:
        return redirect(url_for("index"))
    if not QUERY_LOCK.acquire(blocking=False):
        return render_template(
            "index.html",
            connected=True,
            exclusion_days=exclusion_days,
            window_days=window_days,
            datasets=list_datasets(DATASETS_DIR),
            error="A YouTube query is already running. Please keep its window open until it finishes.",
        ), 409
    try:
        report = build_report(credentials, exclusion_days, window_days)
        filename = save_dataset(DATASETS_DIR, report_to_dataset(report, exclusion_days, window_days))
        return redirect(url_for("index", dataset=filename))
    except Exception as error:
        app.logger.exception("Could not build report")
        return render_template(
            "index.html",
            connected=True,
            exclusion_days=exclusion_days,
            window_days=window_days,
            datasets=list_datasets(DATASETS_DIR),
            error=str(error),
        ), 502
    finally:
        QUERY_LOCK.release()


@app.route("/analyze")
def analyze():
    filename = request.args.get("dataset", "")
    try:
        data = load_dataset(DATASETS_DIR, filename)
        histories = []
        for item in list_datasets(DATASETS_DIR):
            if item["filename"] == filename:
                continue
            old = load_dataset(DATASETS_DIR, item["filename"])
            if old["query"] == data["query"]:
                histories.append(old)
            if len(histories) >= 24:
                break
        return _render_saved(data, filename, analysis=analyze_dataset(data, histories))
    except (ValueError, OSError) as error:
        return redirect(url_for("index", error=str(error)))


@app.route("/datasets/<path:filename>")
def download_dataset(filename):
    load_dataset(DATASETS_DIR, filename)
    return send_from_directory(DATASETS_DIR, filename, as_attachment=True, download_name=filename)


@app.post("/datasets/import")
def upload_dataset():
    upload = request.files.get("dataset_file")
    if not upload or not upload.filename:
        return redirect(url_for("index"))
    try:
        filename = import_dataset(DATASETS_DIR, upload.read(), upload.filename)
        return redirect(url_for("index", dataset=filename))
    except Exception as error:
        app.logger.exception("Dataset import failed")
        return render_template("index.html", connected=bool(_credentials()), datasets=list_datasets(DATASETS_DIR), exclusion_days=90, window_days=30, error=str(error)), 400


@app.route("/connect")
def connect():
    if not CLIENT_SECRET_PATH.exists():
        return redirect(url_for("index"))
    flow = _flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@app.route("/oauth2callback")
def oauth_callback():
    expected_state = session.pop("oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return "OAuth state did not match. Please return to the app and try again.", 400
    try:
        flow = _flow(state=expected_state)
        flow.fetch_token(authorization_response=request.url)
        TOKEN_PATH.write_text(flow.credentials.to_json())
        return redirect(url_for("new_query"))
    except Exception as error:
        app.logger.exception("OAuth callback failed")
        return render_template("oauth_error.html", error=str(error)), 500


@app.post("/disconnect")
def disconnect():
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8765"))
    app.run(host="127.0.0.1", port=port, debug=False)
