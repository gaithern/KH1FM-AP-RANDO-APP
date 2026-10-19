import re
from datetime import datetime, timedelta

import ap_tools

ROOM_LOG_TIMESTAMP_PATTERN = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\]")
ROOM_LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"
ROOM_LOG_UTC_TO_EASTERN = timedelta(hours=4)
ROOM_LOG_START_MARKER = "(Team #1)"
ROOM_LOG_END_MARKER = "Notice (all): Team #1 has completed all of their games! Congratulations!"


def get_html(url):
    print(f"Getting HTML from URL {url}...")
    session = ap_tools.get_session()
    return session.get(url).text


def read_log_line_time(line):
    timestamp = ROOM_LOG_TIMESTAMP_PATTERN.search(line)
    if not timestamp:
        return None
    utc_time = datetime.strptime(timestamp.group(1), ROOM_LOG_TIMESTAMP_FORMAT)
    return utc_time - ROOM_LOG_UTC_TO_EASTERN


def get_event_times(room_url):
    log_url = room_url.replace("/room/", "/log/")
    log_text = get_html(log_url)
    print(log_text)

    start_time = None
    end_time = None
    for line in log_text.splitlines():
        if ROOM_LOG_START_MARKER in line and start_time is None:
            start_time = read_log_line_time(line)
        if ROOM_LOG_END_MARKER in line and end_time is None:
            end_time = read_log_line_time(line)
        if start_time and end_time:
            break

    if start_time is None or end_time is None:
        duration = None
    else:
        duration = end_time - start_time
    return start_time, end_time, duration
