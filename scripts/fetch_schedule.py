#!/usr/bin/env python3
import datetime
import requests
from zoneinfo import ZoneInfo

LISTING = "7542-akron-food-works"
BASE_URL = "https://app.thefoodcorridor.com"
TZ = ZoneInfo("America/New_York")

# Resources to show as rows, in display order
SPACE_ORDER = [
    "Create Kitchen - WHOLE ROOM",
    "Create Kitchen - LEFT SIDE",
    "Create Kitchen - RIGHT SIDE",
    "Elevate (Main) Kitchen",
    "NEW Prep/Specialty Kitchen",
    "Warewashing/Cleanup Area",
]

# Display labels (shorter for TV)
LABEL_MAP = {
    "Create Kitchen - WHOLE ROOM": ("Create Kitchen", "Whole Room"),
    "Create Kitchen - LEFT SIDE":  ("Create Kitchen", "Left Side"),
    "Create Kitchen - RIGHT SIDE": ("Create Kitchen", "Right Side"),
    "Elevate (Main) Kitchen":      ("Elevate Kitchen", "Main"),
    "NEW Prep/Specialty Kitchen":  ("Prep / Specialty", "Kitchen"),
    "Warewashing/Cleanup Area":    ("Warewashing", "Cleanup Area"),
}


def fetch_gantt(session: requests.Session, date_ts: int) -> list:
    url = f"{BASE_URL}/listings/{LISTING}/tfc_calendars/ganttdata"
    r = session.get(url, params={"date": date_ts})
    r.raise_for_status()
    return r.json()


def ts_to_local(ms: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ms / 1000, tz=TZ)


def hour_label(dt: datetime.datetime) -> str:
    h12 = dt.hour % 12 or 12
    suffix = "a" if dt.hour < 12 else "p"
    return f"{h12}{suffix}"


def build_html(bookings: list, start_dt: datetime.datetime, end_dt: datetime.datetime, mode: str) -> str:
    # Build color map from resource definitions (empty title entries)
    color_map = {}
    for item in bookings:
        if not item["title"] and item["calendar"] not in color_map:
            color_map[item["calendar"]] = item["color"]

    total_seconds = (end_dt - start_dt).total_seconds()

    def pct(dt: datetime.datetime) -> float:
        offset = (dt - start_dt).total_seconds()
        return max(0.0, min(100.0, offset / total_seconds * 100))

    # Filter to bookings that overlap the window
    events = []
    for b in bookings:
        if not b["title"]:
            continue
        ev_start = ts_to_local(b["startDate"])
        ev_end = ts_to_local(b["endDate"])
        if ev_end <= start_dt or ev_start >= end_dt:
            continue
        events.append((b, ev_start, ev_end))

    # Group by calendar
    by_cal: dict[str, list] = {s: [] for s in SPACE_ORDER}
    for b, ev_start, ev_end in events:
        cal = b["calendar"]
        if cal in by_cal:
            by_cal[cal].append((b, ev_start, ev_end))

    # Hour tick marks — iterate from start to end
    hours = []
    h = start_dt
    while h <= end_dt:
        hours.append(h)
        h = h + datetime.timedelta(hours=1)

    hour_ticks = ""
    for ht in hours:
        p = (ht - start_dt).total_seconds() / total_seconds * 100
        hour_ticks += f'<div class="tick" style="left:{p:.2f}%">{hour_label(ht)}</div>\n'

    # Rows
    rows_html = ""
    for space in SPACE_ORDER:
        evs = by_cal.get(space, [])
        color = color_map.get(space, "#2C5440")
        line1, line2 = LABEL_MAP.get(space, (space, ""))

        blocks = ""
        for b, ev_start, ev_end in evs:
            left = pct(ev_start)
            right = pct(ev_end)
            width = right - left
            if width <= 0:
                continue
            time_label = f"{ev_start.strftime('%-I:%M%p').lower()}–{ev_end.strftime('%-I:%M%p').lower()}"
            title = b["title"]
            blocks += (
                f'<div class="block" style="left:{left:.2f}%;width:{width:.2f}%;'
                f'background:{color};box-shadow:0 6px 16px -8px {color}90">'
                f'<span class="block-title">{title}</span>'
                f'<span class="block-time">{time_label}</span>'
                f'</div>\n'
            )

        hour_lines = "".join(
            f'<div class="hour-line" style="left:{((ht-start_dt).total_seconds()/total_seconds*100):.2f}%"></div>'
            for ht in hours
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

    updated_str = datetime.datetime.now(tz=TZ).strftime("%-I:%M %p")

    if mode == "overnight":
        eyebrow = "Akron Food Works · Tonight in the kitchen"
        title_html = "Cooking<br><em>through the night.</em>"
        meta_day = "Tonight"
        # Date range: "Mon Jun 8 → Tue Jun 9"
        same_year = start_dt.year == end_dt.year
        meta_date = f"{start_dt.strftime('%a %b %-d')} → {end_dt.strftime('%a %b %-d')}"
        if not same_year:
            meta_date = f"{start_dt.strftime('%a %b %-d, %Y')} → {end_dt.strftime('%a %b %-d, %Y')}"
        body_class = "overnight"
    else:
        eyebrow = "Akron Food Works · Today in the kitchen"
        title_html = "What&rsquo;s cooking<br><em>today.</em>"
        meta_day = start_dt.strftime("%A")
        meta_date = start_dt.strftime("%B %-d, %Y")
        body_class = "day"

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
  body.overnight {{
    color: #F4EEDF;
    background:
      radial-gradient(1100px 500px at 88% -8%, rgba(217,164,65,.20), transparent 60%),
      radial-gradient(900px 500px at -10% 110%, rgba(232,155,90,.10), transparent 55%),
      var(--green-deep);
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
  body.overnight .eyebrow {{ color: var(--gold); }}
  .eyebrow::before {{
    content: "";
    width: 36px;
    height: 2px;
    background: currentColor;
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
  body.overnight h1 {{ color: #FFFDF8; }}
  h1 em {{
    font-style: italic;
    font-weight: 500;
    color: var(--amber);
  }}
  body.overnight h1 em {{ color: var(--gold); }}
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
  body.overnight .meta .day {{ color: #FFFDF8; }}
  .meta .date {{
    font-style: italic;
    font-weight: 500;
    font-size: clamp(1rem, 1.3vw, 1.3rem);
    color: var(--amber);
    margin-top: 6px;
  }}
  body.overnight .meta .date {{ color: var(--gold); }}
  .meta .updated {{
    font-family: var(--body);
    font-size: clamp(.7rem, .8vw, .85rem);
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--ink-soft);
    margin-top: 10px;
    font-weight: 600;
  }}
  body.overnight .meta .updated {{ color: #CFC9BA; }}

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
  body.overnight .schedule-card {{
    background: rgba(255,253,248,.04);
    border-color: rgba(255,253,248,.12);
    box-shadow: 0 30px 60px -30px rgba(0,0,0,.5);
  }}

  .hours-bar {{
    position: relative;
    margin-left: clamp(180px, 16vw, 280px);
    height: 26px;
    margin-bottom: 8px;
    flex-shrink: 0;
    border-bottom: 1px dashed var(--line);
  }}
  body.overnight .hours-bar {{ border-bottom-color: rgba(255,253,248,.15); }}
  .tick {{
    position: absolute;
    transform: translateX(-50%);
    font-family: var(--display);
    font-weight: 600;
    font-size: clamp(.78rem, .95vw, 1rem);
    color: var(--ink-soft);
    bottom: 4px;
  }}
  body.overnight .tick {{ color: #CFC9BA; }}

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
  .label-text {{ line-height: 1.05; }}
  .label-1 {{
    font-family: var(--display);
    font-weight: 900;
    font-size: clamp(1.1rem, 1.5vw, 1.55rem);
    color: var(--green-deep);
    letter-spacing: -.01em;
  }}
  body.overnight .label-1 {{ color: #FFFDF8; }}
  .label-2 {{
    font-family: var(--display);
    font-weight: 500;
    font-style: italic;
    font-size: clamp(.85rem, 1.1vw, 1.15rem);
    color: var(--amber);
    margin-top: 2px;
  }}
  body.overnight .label-2 {{ color: var(--gold); }}

  .timeline {{
    flex: 1;
    position: relative;
    background: var(--cream);
    border: 1px solid var(--line);
    border-radius: 12px;
  }}
  body.overnight .timeline {{
    background: rgba(255,253,248,.04);
    border-color: rgba(255,253,248,.12);
  }}
  .hour-line {{
    position: absolute;
    top: 0; bottom: 0;
    width: 1px;
    background: var(--line);
  }}
  body.overnight .hour-line {{ background: rgba(255,253,248,.08); }}
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
  body.overnight .empty {{ color: #CFC9BA; }}

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
  body.overnight footer .mark {{ color: #FFFDF8; }}
  footer .tag {{
    letter-spacing: .32em;
    text-transform: uppercase;
    font-size: clamp(.65rem, .75vw, .8rem);
    color: var(--amber);
    font-weight: 600;
    margin-top: 4px;
  }}
  body.overnight footer .tag {{ color: var(--gold); }}
</style>
</head>
<body class="{body_class}">
<header>
  <div>
    <div class="eyebrow">{eyebrow}</div>
    <h1>{title_html}</h1>
  </div>
  <div class="meta">
    <div class="day">{meta_day}</div>
    <div class="date">{meta_date}</div>
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


def merge_bookings(*lists):
    """Combine bookings from multiple days, de-duped by (calendar, title, startDate, endDate)."""
    seen = set()
    merged = []
    for bookings in lists:
        for b in bookings:
            key = (b["calendar"], b["title"], b["startDate"], b["endDate"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(b)
    return merged


def main():
    import os
    os.makedirs("dist", exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (kitchen-display-bot/1.0)"

    now = datetime.datetime.now(tz=TZ)
    today_midnight = datetime.datetime(now.year, now.month, now.day, tzinfo=TZ)
    yesterday_midnight = today_midnight - datetime.timedelta(days=1)

    # --- Day view: 6am–10pm today ---
    today_data = fetch_gantt(session, int(today_midnight.timestamp()))
    day_start = today_midnight + datetime.timedelta(hours=6)
    day_end = today_midnight + datetime.timedelta(hours=22)
    day_html = build_html(today_data, day_start, day_end, mode="day")
    with open("dist/index.html", "w", encoding="utf-8") as f:
        f.write(day_html)
    print("Wrote dist/index.html")

    # --- Overnight view: 8pm–8am ---
    # If we're already past midnight but before 8am, show the overnight that's in progress
    if now.hour < 8:
        overnight_start = yesterday_midnight + datetime.timedelta(hours=20)
    else:
        overnight_start = today_midnight + datetime.timedelta(hours=20)
    overnight_end = overnight_start + datetime.timedelta(hours=12)

    start_day_midnight = overnight_start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_day_midnight = overnight_end.replace(hour=0, minute=0, second=0, microsecond=0)

    overnight_lists = []
    if start_day_midnight == today_midnight:
        overnight_lists.append(today_data)
    else:
        overnight_lists.append(fetch_gantt(session, int(start_day_midnight.timestamp())))
    if end_day_midnight != start_day_midnight:
        if end_day_midnight == today_midnight:
            overnight_lists.append(today_data)
        else:
            overnight_lists.append(fetch_gantt(session, int(end_day_midnight.timestamp())))

    overnight_data = merge_bookings(*overnight_lists)
    overnight_html = build_html(overnight_data, overnight_start, overnight_end, mode="overnight")
    with open("dist/overnight.html", "w", encoding="utf-8") as f:
        f.write(overnight_html)
    print("Wrote dist/overnight.html")


if __name__ == "__main__":
    main()
