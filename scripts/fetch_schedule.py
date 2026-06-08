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

    weekday_str = today.strftime("%A")
    date_str = today.strftime("%B %-d, %Y")
    updated_str = datetime.datetime.now(tz=TZ).strftime("%-I:%M %p")

    # Hour tick marks
    hours = list(range(DAY_START_HOUR, DAY_END_HOUR + 1))
    hour_ticks = ""
    for h in hours:
        p = (h - DAY_START_HOUR) / (DAY_END_HOUR - DAY_START_HOUR) * 100
        label = f"{h % 12 or 12}{'a' if h < 12 else 'p'}"
        hour_ticks += f'<div class="tick" style="left:{p:.2f}%">{label}</div>\n'

    # Display labels (shorter for TV)
    label_map = {
        "Create Kitchen - WHOLE ROOM": ("Create Kitchen", "Whole Room"),
        "Create Kitchen - LEFT SIDE":  ("Create Kitchen", "Left Side"),
        "Create Kitchen - RIGHT SIDE": ("Create Kitchen", "Right Side"),
        "Elevate (Main) Kitchen":      ("Elevate Kitchen", "Main"),
        "NEW Prep/Specialty Kitchen":  ("Prep / Specialty", "Kitchen"),
        "Warewashing/Cleanup Area":    ("Warewashing", "Cleanup Area"),
    }

    # Rows
    rows_html = ""
    for space in SPACE_ORDER:
        evs = by_cal.get(space, [])
        color = color_map.get(space, "#2C5440")
        line1, line2 = label_map.get(space, (space, ""))

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
                f'<div class="block" style="left:{left:.2f}%;width:{width:.2f}%;'
                f'background:{color};box-shadow:0 6px 16px -8px {color}90">'
                f'<span class="block-title">{title}</span>'
                f'<span class="block-time">{time_label}</span>'
                f'</div>\n'
            )

        hour_lines = "".join(
            f'<div class="hour-line" style="left:{((h-DAY_START_HOUR)/(DAY_END_HOUR-DAY_START_HOUR)*100):.2f}%"></div>'
            for h in hours
        )
        rows_html += f"""
        <div class="row">
          <div class="label">
            <span class="swatch" style="background:{color}"></span>
            <div class="label-text">
              <div class="label-1">{line1}</div>
              <div class="label-2">{line2}</div>
            </div>
          </div>
          <div class="timeline">
            {hour_lines}
            {blocks if blocks else '<div class="empty">Open · no bookings</div>'}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="900">
<title>Akron Food Works — Kitchen Schedule</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,900;1,9..144,500&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --cream: #FBF6EC;
    --paper: #FFFDF8;
    --ink: #23372B;
    --ink-soft: #4A5A4E;
    --green: #2C5440;
    --green-deep: #1E3A2D;
    --amber: #C8612E;
    --amber-soft: #E89B5A;
    --gold: #D9A441;
    --line: #E2D9C6;
    --shadow: 0 18px 40px -22px rgba(30,58,45,.45);
    --display: 'Fraunces', Georgia, serif;
    --body: 'Hanken Grotesk', system-ui, sans-serif;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    font-family: var(--body);
    color: var(--ink);
    background:
      radial-gradient(1200px 600px at 85% -8%, rgba(217,164,65,.16), transparent 60%),
      radial-gradient(900px 500px at -10% 110%, rgba(44,84,64,.12), transparent 55%),
      var(--cream);
    line-height: 1.5;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: clamp(20px, 2.2vw, 36px) clamp(24px, 3vw, 48px);
  }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    flex-shrink: 0;
    margin-bottom: clamp(16px, 1.8vw, 28px);
  }}
  .eyebrow {{
    font-size: clamp(.7rem, .9vw, .95rem);
    letter-spacing: .32em;
    text-transform: uppercase;
    font-weight: 600;
    color: var(--amber);
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }}
  .eyebrow::before {{
    content: "";
    width: 36px;
    height: 2px;
    background: var(--amber);
    display: inline-block;
  }}
  h1 {{
    font-family: var(--display);
    font-weight: 900;
    font-size: clamp(2.4rem, 4.4vw, 4.4rem);
    line-height: .98;
    letter-spacing: -.02em;
    color: var(--green-deep);
  }}
  h1 em {{
    font-style: italic;
    font-weight: 500;
    color: var(--amber);
  }}
  .meta {{
    text-align: right;
    font-family: var(--display);
    color: var(--ink-soft);
  }}
  .meta .day {{
    font-weight: 900;
    font-size: clamp(1.4rem, 2.2vw, 2.2rem);
    color: var(--green-deep);
    line-height: 1;
  }}
  .meta .date {{
    font-style: italic;
    font-weight: 500;
    font-size: clamp(1rem, 1.3vw, 1.3rem);
    color: var(--amber);
    margin-top: 6px;
  }}
  .meta .updated {{
    font-family: var(--body);
    font-size: clamp(.7rem, .8vw, .85rem);
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--ink-soft);
    margin-top: 10px;
    font-weight: 600;
  }}

  .schedule-card {{
    flex: 1;
    background: var(--paper);
    border: 1px solid var(--line);
    border-radius: 18px;
    box-shadow: var(--shadow);
    padding: clamp(18px, 2vw, 28px) clamp(18px, 2vw, 28px) clamp(14px, 1.6vw, 22px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}

  .hours-bar {{
    position: relative;
    margin-left: clamp(180px, 16vw, 280px);
    height: 26px;
    margin-bottom: 8px;
    flex-shrink: 0;
    border-bottom: 1px dashed var(--line);
  }}
  .tick {{
    position: absolute;
    transform: translateX(-50%);
    font-family: var(--display);
    font-weight: 600;
    font-size: clamp(.78rem, .95vw, 1rem);
    color: var(--ink-soft);
    bottom: 4px;
  }}

  .rows {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: clamp(8px, 1vw, 14px);
    padding-top: 6px;
    min-height: 0;
  }}
  .row {{
    display: flex;
    align-items: stretch;
    flex: 1;
    min-height: 0;
  }}
  .label {{
    width: clamp(180px, 16vw, 280px);
    min-width: clamp(180px, 16vw, 280px);
    display: flex;
    align-items: center;
    gap: 14px;
    padding-right: 16px;
  }}
  .swatch {{
    width: 8px;
    align-self: stretch;
    border-radius: 4px;
    flex-shrink: 0;
  }}
  .label-text {{
    line-height: 1.05;
  }}
  .label-1 {{
    font-family: var(--display);
    font-weight: 900;
    font-size: clamp(1.1rem, 1.5vw, 1.55rem);
    color: var(--green-deep);
    letter-spacing: -.01em;
  }}
  .label-2 {{
    font-family: var(--display);
    font-weight: 500;
    font-style: italic;
    font-size: clamp(.85rem, 1.1vw, 1.15rem);
    color: var(--amber);
    margin-top: 2px;
  }}

  .timeline {{
    flex: 1;
    position: relative;
    background: var(--cream);
    border: 1px solid var(--line);
    border-radius: 12px;
  }}
  .hour-line {{
    position: absolute;
    top: 0; bottom: 0;
    width: 1px;
    background: var(--line);
  }}
  .block {{
    position: absolute;
    top: 6px;
    bottom: 6px;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 6px 14px;
    overflow: hidden;
    min-width: 4px;
    color: #FFFDF8;
  }}
  .block-title {{
    font-family: var(--display);
    font-weight: 900;
    font-size: clamp(1rem, 1.35vw, 1.45rem);
    line-height: 1.05;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    letter-spacing: -.01em;
    text-shadow: 0 1px 2px rgba(0,0,0,.25);
  }}
  .block-time {{
    font-family: var(--body);
    font-weight: 600;
    font-size: clamp(.75rem, .95vw, 1rem);
    letter-spacing: .02em;
    color: rgba(255,253,248,.92);
    margin-top: 2px;
    white-space: nowrap;
  }}
  .empty {{
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    padding-left: 16px;
    font-family: var(--display);
    font-style: italic;
    font-weight: 500;
    font-size: clamp(.85rem, 1.05vw, 1.1rem);
    color: var(--ink-soft);
  }}

  footer {{
    flex-shrink: 0;
    text-align: center;
    margin-top: clamp(14px, 1.6vw, 22px);
    color: var(--ink-soft);
  }}
  footer .mark {{
    font-family: var(--display);
    font-weight: 900;
    letter-spacing: .12em;
    color: var(--green-deep);
    font-size: clamp(.95rem, 1.1vw, 1.15rem);
  }}
  footer .tag {{
    letter-spacing: .32em;
    text-transform: uppercase;
    font-size: clamp(.65rem, .75vw, .8rem);
    color: var(--amber);
    font-weight: 600;
    margin-top: 4px;
  }}
</style>
</head>
<body>
<header>
  <div>
    <div class="eyebrow">Akron Food Works · Today in the kitchen</div>
    <h1>What&rsquo;s cooking<br><em>today.</em></h1>
  </div>
  <div class="meta">
    <div class="day">{weekday_str}</div>
    <div class="date">{date_str}</div>
    <div class="updated">Updated {updated_str}</div>
  </div>
</header>

<div class="schedule-card">
  <div class="hours-bar">{hour_ticks}</div>
  <div class="rows">
    {rows_html}
  </div>
</div>

<footer>
  <div class="mark">AKRON FOOD WORKS</div>
  <div class="tag">Create · Incubate · Elevate</div>
</footer>

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
