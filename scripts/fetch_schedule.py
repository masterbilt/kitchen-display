#!/usr/bin/env python3
import os
import sys
import json
import time
import datetime
import requests
from zoneinfo import ZoneInfo

LISTING = "7542-akron-food-works"
BASE_URL = "https://app.thefoodcorridor.com"
TZ = ZoneInfo("America/New_York")

# Resources to show as rows (in display order), keyed by calendar name from API
SPACE_ORDER = [
    "Create Kitchen - WHOLE ROOM",
    "Create Kitchen - LEFT SIDE",
    "Create Kitchen - RIGHT SIDE",
    "Elevate (Main) Kitchen",
    "NEW Prep/Specialty Kitchen",
    "Warewashing/Cleanup Area",
    "Market/Event Kit",
    "Refrigerator - Market/Event",
    "Portable 4-Compartment Sink",
    "Hand Wash Only Portable Sink",
    "Induction Cookware & Cooktops (Prep Kitchen)",
    "Deep Fryer (Create Kitchen)",
    "Deli Slicer",
    "Schedule time with Akron Food Works Staff",
]

DAY_START_HOUR = 6   # 6 AM
DAY_END_HOUR   = 22  # 10 PM


def login(session: requests.Session) -> bool:
    email = os.environ["TFC_EMAIL"]
    password = os.environ["TFC_PASSWORD"]

    # Fetch login page to get CSRF token
    r = session.get(f"{BASE_URL}/en/login")
    r.raise_for_status()

    from html.parser import HTMLParser

    class TokenParser(HTMLParser):
        token = None
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "input" and attrs.get("name") == "authenticity_token":
                self.token = attrs.get("value")

    parser = TokenParser()
    parser.feed(r.text)
    if not parser.token:
        print("ERROR: Could not find CSRF token on login page", file=sys.stderr)
        return False

    r = session.post(
        f"{BASE_URL}/en/sessions",
        data={
            "authenticity_token": parser.token,
            "person[login]": email,
            "person[password]": password,
        },
        allow_redirects=True,
    )
    r.raise_for_status()
    return "/en/login" not in r.url  # redirected away = success


def fetch_gantt(session: requests.Session, date_ts: int) -> list:
    url = f"{BASE_URL}/listings/{LISTING}/tfc_calendars/ganttdata"
    r = session.get(url, params={"date": date_ts})
    r.raise_for_status()
    return r.json()


def ts_to_local(ms: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ms / 1000, tz=TZ)


def pct(dt: datetime.datetime) -> float:
    total_mins = (DAY_END_HOUR - DAY_START_HOUR) * 60
    offset_mins = (dt.hour - DAY_START_HOUR) * 60 + dt.minute
    return max(0.0, min(100.0, offset_mins / total_mins * 100))


def build_html(bookings: list, today: datetime.datetime) -> str:
    # Build color map from resource definitions (empty title entries)
    color_map = {}
    for item in bookings:
        if not item["title"] and item["calendar"] not in color_map:
            color_map[item["calendar"]] = item["color"]

    # Filter to actual bookings
    events = [b for b in bookings if b["title"]]

    # Group by calendar
    by_cal: dict[str, list] = {s: [] for s in SPACE_ORDER}
    for ev in events:
        cal = ev["calendar"]
        if cal in by_cal:
            by_cal[cal].append(ev)

    date_str = today.strftime("%A, %B %-d, %Y")
    updated_str = datetime.datetime.now(tz=TZ).strftime("%-I:%M %p")

    # Hour tick marks
    hours = list(range(DAY_START_HOUR, DAY_END_HOUR + 1))
    hour_ticks = ""
    for h in hours:
        p = (h - DAY_START_HOUR) / (DAY_END_HOUR - DAY_START_HOUR) * 100
        label = f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"
        hour_ticks += f'<div class="tick" style="left:{p:.2f}%">{label}</div>\n'

    # Rows
    rows_html = ""
    for space in SPACE_ORDER:
        evs = by_cal.get(space, [])
        color = color_map.get(space, "#555")

        blocks = ""
        for ev in evs:
            start_dt = ts_to_local(ev["startDate"])
            end_dt   = ts_to_local(ev["endDate"])
            left  = pct(start_dt)
            right = pct(end_dt)
            width = right - left
            if width <= 0:
                continue
            time_label = f"{start_dt.strftime('%-I:%M%p').lower()}–{end_dt.strftime('%-I:%M%p').lower()}"
            title = ev["title"]
            blocks += (
                f'<div class="block" style="left:{left:.2f}%;width:{width:.2f}%;background:{color}" '
                f'title="{title} {time_label}">'
                f'<span class="block-title">{title}</span>'
                f'<span class="block-time">{time_label}</span>'
                f'</div>\n'
            )

        dot_color = color if evs else "#333"
        rows_html += f"""
        <div class="row">
          <div class="label">
            <span class="dot" style="background:{dot_color}"></span>
            {space}
          </div>
          <div class="timeline">
            {"".join(f'<div class="hour-line" style="left:{((h-DAY_START_HOUR)/(DAY_END_HOUR-DAY_START_HOUR)*100):.2f}%"></div>' for h in hours)}
            {blocks if blocks else '<div class="empty">No bookings</div>'}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>Akron Food Works — Kitchen Schedule</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0d0d0d;
    color: #eee;
    font-family: 'Segoe UI', Arial, sans-serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 28px 8px;
    border-bottom: 1px solid #2a2a2a;
    flex-shrink: 0;
  }}
  h1 {{ font-size: 2rem; font-weight: 700; letter-spacing: .5px; }}
  .meta {{ text-align: right; font-size: 1rem; color: #888; }}
  .meta .updated {{ font-size: .85rem; margin-top: 2px; }}
  .schedule {{
    flex: 1;
    overflow-y: auto;
    padding: 8px 28px 16px;
  }}
  .hours-bar {{
    display: flex;
    margin-left: 260px;
    position: relative;
    height: 22px;
    margin-bottom: 4px;
    flex-shrink: 0;
  }}
  .tick {{
    position: absolute;
    transform: translateX(-50%);
    font-size: .75rem;
    color: #555;
  }}
  .row {{
    display: flex;
    align-items: center;
    margin-bottom: 6px;
    min-height: 48px;
  }}
  .label {{
    width: 260px;
    min-width: 260px;
    font-size: .9rem;
    line-height: 1.2;
    padding-right: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: #ccc;
  }}
  .dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .timeline {{
    flex: 1;
    position: relative;
    height: 44px;
    background: #1a1a1a;
    border-radius: 4px;
  }}
  .hour-line {{
    position: absolute;
    top: 0; bottom: 0;
    width: 1px;
    background: #2a2a2a;
  }}
  .block {{
    position: absolute;
    top: 4px;
    bottom: 4px;
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 8px;
    overflow: hidden;
    min-width: 2px;
    cursor: default;
  }}
  .block-title {{
    font-size: .82rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,.5);
  }}
  .block-time {{
    font-size: .7rem;
    color: rgba(255,255,255,.8);
    white-space: nowrap;
  }}
  .empty {{
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    padding-left: 10px;
    color: #333;
    font-size: .8rem;
  }}
  footer {{
    text-align: center;
    font-size: .75rem;
    color: #333;
    padding: 6px;
    flex-shrink: 0;
  }}
</style>
</head>
<body>
<header>
  <h1>Akron Food Works — Kitchen Schedule</h1>
  <div class="meta">
    <div>{date_str}</div>
    <div class="updated">Updated {updated_str} &bull; refreshes every 15 min</div>
  </div>
</header>
<div class="schedule">
  <div class="hours-bar">{hour_ticks}</div>
  {rows_html}
</div>
<footer>thefoodcorridor.com &bull; auto-generated</footer>
</body>
</html>"""


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (kitchen-display-bot/1.0)"

    if not login(session):
        print("Login failed", file=sys.stderr)
        sys.exit(1)

    now = datetime.datetime.now(tz=TZ)
    # Midnight local time as Unix seconds
    midnight = datetime.datetime(now.year, now.month, now.day, tzinfo=TZ)
    date_ts = int(midnight.timestamp())

    data = fetch_gantt(session, date_ts)

    html = build_html(data, now)

    out = os.environ.get("OUTPUT_FILE", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
