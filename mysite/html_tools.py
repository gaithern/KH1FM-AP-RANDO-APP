import requests
from pprint import pprint
from bs4 import BeautifulSoup
from envr import AP_LOGIN
from datetime import datetime, timedelta
import re

def get_session():
    session = requests.Session()
    session.get(AP_LOGIN)
    return session

def get_tracker_url(room_url):
    room_html = get_html(room_url)
    html_section = room_html.split("/tracker/")[1]
    html_section = html_section.split("\"")[0]
    tracker_url = f"https://archipelago.gg/tracker/{html_section}"
    return tracker_url

def get_checks_table(tracker_html):
    soup = BeautifulSoup(tracker_html, 'html.parser')
    checks_table = soup.find('table', {'id': 'checks-table'})
    table_data = []
    for row in checks_table.find_all('tr'):
        row_data = []
        for cell in row.find_all(['td', 'th']):  # Handle both td and th
            row_data.append(cell.text.strip())
        table_data.append(row_data)
    checks_table = table_data[1:-1]
    checks_library = []
    for entry in checks_table:
        slot_info = {
            "Number": entry[0],
            "Name": entry[1],
            "Game": entry[2],
            "Status": entry[3],
            "Checks": entry[4],
            "Percent": entry[5],
            "Last Activity": entry[6]}
        checks_library.append(slot_info)
    return checks_library

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

def get_html(url):
    print(f"Getting HTML from URL {url}...")
    session = get_session()
    return session.get(url).text

def get_event_times(url):
    """
    Parse a log text and return the start time, end time, and duration.
    """
    # Timestamp format: [YYYY-MM-DD HH:MM:SS,mmm]
    
    log_text = get_html(url.replace("/room/", "/log/"))
    
    print(log_text)
    
    timestamp_pattern = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\]")

    start_marker = "(Team #1)"
    end_marker = "Notice (all): Team #1 has completed all of their games! Congratulations!"

    start_time = None
    end_time = None

    for line in log_text.splitlines():
        if start_marker in line and start_time is None:
            match = timestamp_pattern.search(line)
            if match:
                start_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f") - timedelta(hours=4)
        if end_marker in line and end_time is None:
            match = timestamp_pattern.search(line)
            if match:
                end_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f") - timedelta(hours=4)
        if start_time and end_time:
            break

    return start_time, end_time, None if start_time is None or end_time is None else end_time - start_time
