# Back Catalog Pulse

A small, read-only local web app for finding older YouTube videos that are receiving activity now. It deliberately keeps two controls independent:

- **Exclusion age** (default 90 days): hides videos published more recently than this.
- **Activity window** (default 30 days): totals activity over this many complete days and compares it with the immediately preceding window of the same length.

The report includes sortable views, likes, shares, comments, publication date/age, **Surging** (percentage change in views), and the number of newer uploads excluded by the age cutoff. Clicking a title opens the video on YouTube.

The publication cutoff is selected with a date picker (default: 90 days ago), while the recent activity window remains an adjustable number of days (default: 30). The channel-coverage summary separates total uploads, videos newer than the chosen cutoff, eligible older videos, eligible videos with activity, and eligible videos without activity. It also states the exact included publication date and both analytics comparison periods.

Each new query is automatically saved as a portable JSON snapshot in `datasets/`. Opening the app loads the newest saved snapshot without contacting YouTube. Use **New YouTube query** when you want fresh data, the saved-dataset menu to revisit a prior query, **Download JSON** to export one, or **Import JSON** to load an exported snapshot. The **Analyze** button performs local title-pattern analysis to identify recurring trip series and summarize their current activity; it does not send data to an AI service.

While a new YouTube query is running, the interface displays a blocking progress screen and disables its controls. The server also permits only one query at a time to prevent duplicate API work.

New snapshots also request watch time, subscribers gained and lost, channel-level traffic sources, and disclosed YouTube search terms. Supplemental traffic/search queries are best-effort: if YouTube does not expose one for the channel or period, the core dataset still saves successfully. Analysis includes trip view share and engagement, net subscriber change, activity classifications, title-topic patterns, dormant-series prompts, recommendations, and history from prior snapshots created with matching parameters.

New queries also save owned-channel playlist membership. Analyze uses specific playlist membership as stronger trip-grouping evidence than repeated title text. The information icon beside each trip lists the represented playlists and included video titles. Older snapshots without playlist data continue to use title-pattern grouping.

## One-time Google setup

You need a Google Cloud project because YouTube does not permit channel analytics without the channel owner's OAuth consent.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Under **APIs & Services → Library**, enable both **YouTube Data API v3** and **YouTube Analytics API**.
3. Open **Google Auth Platform** (or **APIs & Services → OAuth consent screen**). Configure the app as **External**. While the app is in testing, add your channel's Google account as a test user.
4. Under **Clients / Credentials**, create an **OAuth client ID** of type **Web application**.
5. Add this exact authorized redirect URI: `http://127.0.0.1:8765/oauth2callback`
6. Download the OAuth client JSON, rename it to `client_secret.json`, and put it in this folder beside `app.py`.

The OAuth app only asks for read-only YouTube and YouTube Analytics scopes. `client_secret.json` and the generated `token.json` are ignored by Git and should remain private.

## Run on macOS

Double-click **start.command** in Finder. On first run it creates a private Python environment and installs dependencies, then opens the report in your browser. If macOS blocks it, Control-click the file, choose **Open**, and approve it once.

Or run manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:8765>. Click **Connect YouTube** and approve access.

The app enables OAuthlib's HTTP transport exception because Google permits plain HTTP for loopback redirects and the server binds only to `127.0.0.1`. Do not change the server host to a network-accessible address without adding HTTPS.

To use another port, copy `.env.example` to `.env`, change `PORT`, and add the matching redirect URI in Google Cloud. Use a stable `FLASK_SECRET_KEY` in `.env` if you want OAuth login to survive an app restart in the middle of the consent flow.

## Metric behavior and API limitations

- The app queries the **YouTube Data API** for every upload's publication timestamp and applies the age exclusion locally. It queries the **YouTube Analytics API** twice: once for the selected window and once for the immediately preceding equal-length window.
- Only videos with activity returned in the selected current window appear. New uploads cannot dominate because they are removed before display.
- **Surging** is `(current views - previous views) / previous views`. If the prior window had zero views, it displays **New** rather than an infinite percentage.
- Analytics reports are not realtime. The app uses complete UTC days ending yesterday; recent results can still be delayed or revised by YouTube. The Analytics API is the closest supported source for channel-level likes, comments, and shares over arbitrary date windows.
- The Analytics API documents `shares`, but availability can vary by channel/report permissions and YouTube can change metric support. If a shares query is rejected, the app automatically retries without it, keeps the report usable, shows zeros in that column, and displays an explanatory banner.
- Data API quota usage grows with the size of the uploads playlist, though the read operations used here are relatively inexpensive. Analytics requests filter eligible video IDs in documented batches of up to 500.

## Troubleshooting

- **Access blocked / app not verified:** keep the OAuth app in Testing and add your own Google account under Test users.
- **Redirect URI mismatch:** confirm the URI is exactly `http://127.0.0.1:8765/oauth2callback` (including scheme, IP, port, and path).
- **Wrong channel:** click Disconnect and reconnect using the Google account that owns or manages the intended YouTube channel.
- **Reset authorization:** stop the app, delete `token.json`, and reconnect.

## Tests

With the environment active, run:

```bash
python -m unittest discover -s tests
```
