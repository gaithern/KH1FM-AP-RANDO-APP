import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

import ap_tools

ROOM_LOG_TIMESTAMP_PATTERN = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\]")
ROOM_LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"
ROOM_LOG_UTC_TO_EASTERN = timedelta(hours=4)
ROOM_LOG_START_MARKER = "(Team #1)"
ROOM_LOG_END_MARKER = "Notice (all): Team #1 has completed all of their games! Congratulations!"

CHECKS_TABLE_COLUMNS = ["Number", "Name", "Game", "Status", "Checks", "Percent", "Last Activity"]


def get_html(url):
    print(f"Getting HTML from URL {url}...")
    session = ap_tools.get_session()
    return session.get(url).text


def get_tracker_url(room_url):
    room_html = get_html(room_url)
    text_after_tracker = room_html.split("/tracker/")[1]
    tracker_id = text_after_tracker.split("\"")[0]
    return f"https://archipelago.gg/tracker/{tracker_id}"


def get_checks_table(tracker_html):
    page = BeautifulSoup(tracker_html, 'html.parser')
    table = page.find('table', {'id': 'checks-table'})

    all_rows = []
    for table_row in table.find_all('tr'):
        cell_texts = []
        for cell in table_row.find_all(['td', 'th']):
            cell_texts.append(cell.text.strip())
        all_rows.append(cell_texts)

    rows_without_header_and_footer = all_rows[1:-1]

    slots = []
    for row in rows_without_header_and_footer:
        slot = {}
        for column_index in range(len(CHECKS_TABLE_COLUMNS)):
            column_name = CHECKS_TABLE_COLUMNS[column_index]
            slot[column_name] = row[column_index]
        slots.append(slot)
    return slots


def all_slots_goaled(room_url):
    print("Getting tracker URL from Room URL")
    tracker_url = get_tracker_url(room_url)
    print(f"Tracker URL: {tracker_url}")
    print("Getting tracker HTML")
    tracker_html = get_html(tracker_url)
    print(f"Tracker HTML: {tracker_html}")
    print("Getting checks table")
    checks_table = get_checks_table(tracker_html)
    print(f"Checks table: {checks_table}")
    print("Checking if every slot in the checks table has goaled")
    all_goaled = True
    for slot in checks_table:
        if slot["Status"] != "Goal Completed":
            print(f"Player not goaled:\n{slot}")
            all_goaled = False
    print(f"All goaled: {all_goaled}")
    return all_goaled


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
