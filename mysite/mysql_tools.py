import pymysql
import ap_tools
import html_tools
from envr import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
from datetime import datetime, timedelta

def get_connection():
    """Establishes a connection to the MySQL database."""
    conn = None
    try:
        conn = pymysql.connect(host=DB_HOST,
                             user=DB_USER,
                             password=DB_PASSWORD,
                             db=DB_NAME,
                             cursorclass=pymysql.cursors.DictCursor) # Use DictCursor for easier row access
    except pymysql.Error as e:
        print(f"Error connecting to MySQL database: {e}")
    return conn

def close_connection(conn, rollback = False):
    try:
        if rollback:
            conn.rollback()
        else:
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error closing MySQL database connection: {e}")

def execute(conn, sql, args = None, fetch_results = False):
    results = None
    with conn.cursor() as cursor:
        if args:
            print(f"SQL statement to execute: {sql} with args {args}")
            cursor.execute(sql, args)
        else:
            print(f"SQL statement to execute: {sql}")
            cursor.execute(sql)
        if fetch_results:
            results = cursor.fetchall()
            print(results)
        if results is None:
            results = []
        cursor.close()
        return results


def register_player(discord_id, discord_name):
    conn = get_connection()
    sql = "SELECT player_id FROM players WHERE discord_id = %s"
    args = (discord_id,)
    results = execute(conn, sql, args=args, fetch_results=True)
    if len(results) > 0:
        close_connection(conn)
    else:
        sql = "INSERT INTO players (discord_id, discord_name) VALUES (%s, %s)"
        args = (discord_id, discord_name.replace(";", ""))
        execute(conn, sql, args=args)
        close_connection(conn)
        
def get_todays_daily_seed_link():
    conn = get_connection()
    sql = """
        SELECT
            seed_id,
            seed_date,
            seed_link,
            seed_zip_path
        FROM daily_seeds
        WHERE SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d');"""
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        seed_link = results[0]["seed_link"]
        seed_zip_path = results[0]["seed_zip_path"]
    else:
        sql = "SELECT DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d') as est_date;"
        results = execute(conn, sql, fetch_results = True)
        date = results[0]["est_date"]
        seed_link, seed_zip_path = ap_tools.generate_daily_seed(date)
        sql = "INSERT INTO daily_seeds (seed_date, seed_link, seed_zip_path) values (%s, %s, %s);"
        args = (date, seed_link, seed_zip_path)
        execute(conn, sql, args = args)
    close_connection(conn)
    return seed_link, seed_zip_path

def get_players_daily_seed(discord_id):
    conn = get_connection()
    sql = f"""
        SELECT
            ps.PLAYER_ID,
            ps.SEED_ID,
            ps.room_link,
            ds.seed_zip_path
        FROM player_seeds ps
        JOIN players p
        ON p.player_id = ps.player_id
        AND p.discord_id = {discord_id}
        JOIN daily_seeds ds
        on ds.seed_id = ps.seed_id
        AND ds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d');"""
    results = execute(conn, sql, fetch_results = True)
    close_connection(conn)
    if len(results) > 0:
        room_link = results[0]["room_link"]
        seed_zip_path = results[0]["seed_zip_path"]
    else:
        seed_link, seed_zip_path = get_todays_daily_seed_link()
        conn = get_connection()
        room_link = ap_tools.get_redirected_url(seed_link.replace("/seed/", "/new_room/"))
        sql = f"""INSERT INTO player_seeds 
            (
                player_id, 
                seed_id, 
                room_link,
                start_time,
                complete_time
            ) 
            VALUES
            (
                (SELECT PLAYER_ID FROM players WHERE discord_id = {discord_id}),
                (SELECT SEED_ID FROM daily_seeds WHERE SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')),
                '{room_link}',
                null,
                null
            );"""
        execute(conn, sql)
        close_connection(conn)
    return room_link, seed_zip_path

def get_players_daily_seed_room_link(discord_id):
    conn = get_connection()
    sql = f"""
    SELECT
        ps.room_link,
        ds.seed_id
    FROM player_seeds ps
    JOIN players p
    ON ps.player_id = p.player_id
    AND p.discord_id = {discord_id}
    JOIN daily_seeds ds
    ON ps.seed_id = ds.seed_id
    AND ds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d');"""
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        room_link = results[0]["room_link"]
        seed_id = results[0]["seed_id"]
        close_connection(conn)
        return seed_id, room_link
    close_connection(conn)
    return None, None

def daily_seed_already_complete(discord_id):
    conn = get_connection()
    sql = f"""
    SELECT
        ps.complete_time
    FROM player_seeds ps
    JOIN players p
    ON ps.player_id = p.player_id
    AND p.discord_id = {discord_id}
    JOIN daily_seeds ds
    ON ps.seed_id = ds.seed_id
    AND ds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')
    WHERE ps.complete_time is not null;
    """
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        close_connection(conn)
        return True
    close_connection(conn)
    return False

def daily_seed_started(discord_id):
    conn = get_connection()
    sql = f"""
    SELECT
        1
    FROM player_seeds ps
    JOIN players p
    ON ps.player_id = p.player_id
    AND p.discord_id = {discord_id}
    JOIN daily_seeds ds
    ON ps.seed_id = ds.seed_id
    AND ds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d');
    """
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        close_connection(conn)
        return True
    close_connection(conn)
    return False

def check_daily_seed_complete(discord_id):
    print("Checking if seed has already been started by player...")
    if not daily_seed_started(discord_id):
        return "Daily seed not started."
    print("Checking if seed has already been completed by player...")
    if daily_seed_already_complete(discord_id):
        return "Daily seed is already completed!"
    print("Getting players seed_id and room_link...")
    seed_id, room_link = get_players_daily_seed_room_link(discord_id)
    print("Checking if that room has all slots complete...")
    start_time, end_time, duration = html_tools.get_event_times(room_link)
    if not end_time:
        return "All slots in your daily seed room have not goaled."
    conn = get_connection()
    sql = f"""UPDATE player_seeds
            SET start_time = STR_TO_DATE('{str(start_time)}','%Y-%m-%d %H:%i:%s.%f')
            , complete_time = STR_TO_DATE('{str(end_time)}','%Y-%m-%d %H:%i:%s.%f')
            WHERE seed_id = {seed_id}
            and room_link = '{room_link}';"""
    execute(conn, sql)
    close_connection(conn)
    return f"Seed completed in {str(duration)}!"

def get_daily_leaderboard():
    conn = get_connection()
    sql = f"""select * from vw_daily_leaderboard"""
    results = execute(conn, sql, fetch_results = True)
    return_str = ""
    player = 1
    digit_map = {
        "0": "0️⃣",
        "1": "🥇",
        "2": "🥈",
        "3": "🥉",
        "4": "4️⃣",
        "5": "5️⃣",
        "6": "6️⃣",
        "7": "7️⃣",
        "8": "8️⃣",
        "9": "9️⃣"
    }
    for row in results:
        if str(player) in digit_map.keys():
            return_str = f"\n{digit_map[str(player)]}: <@{row["discord_id"]}> - {row["run_time"]}"
    return return_str

def daily_duo_get_current_team(discord_id):
    conn = get_connection()
    sql = f"""select
                    coalesce(ddt1.team_id, ddt2.team_id) as team_id,
                    p.discord_name
                from (select * from players where discord_id = {discord_id}) p
                left join (select * from daily_duo_teams where team_up_date = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')) ddt1
                on p.player_id = ddt1.player_id_1
                left join (select * from daily_duo_teams where team_up_date = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')) ddt2
                on p.player_id = ddt2.player_id_2
                where coalesce(ddt1.team_id, ddt2.team_id) is not null"""
    results = execute(conn, sql, fetch_results = True)
    close_connection(conn)
    if len(results) > 0:
        return results[0]["team_id"]
    else:
        return None

def daily_duo_register_team(discord_id_1, discord_id_2):
    conn = get_connection()
    sql = f"""insert into daily_duo_teams
                (player_id_1, player_id_2, team_up_date)
                values
                (
                    (select player_id from players where discord_id = {discord_id_1}),
                    (select player_id from players where discord_id = {discord_id_2}),
                    DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')
                )"""
    execute(conn, sql)
    close_connection(conn)

def daily_duo_team_up(discord_id_1, discord_name_1, discord_id_2, discord_name_2):
    return_str = ""
    register_player(discord_id_1, discord_name_1)
    register_player(discord_id_2, discord_name_2)
    player_1_current_team = daily_duo_get_current_team(discord_id_1)
    player_2_current_team = daily_duo_get_current_team(discord_id_2)
    if player_1_current_team:
        return_str = return_str + f"<@{discord_id_1}> is already assigned to team {player_1_current_team}\n"
    if player_2_current_team:
        return_str = return_str + f"<@{discord_id_2}> is already assigned to team {player_2_current_team}\n"
    if not player_1_current_team and not player_2_current_team:
        daily_duo_register_team(discord_id_1, discord_id_2)
        return_str = return_str + f"Success!  <@{discord_id_1}> and <@{discord_id_2}> are now teamed up for today!"
    return return_str

def get_teams_daily_seed(discord_id):
    player_1_current_team = daily_duo_get_current_team(discord_id)
    if not player_1_current_team:
        return f"<@{discord_id}> is not teamed up!  Team up using `!daily_duo_team_up` and mentioning your desired teammate"
    else:
        conn = get_connection()
        sql = f"""
            SELECT
                ds.TEAM_ID,
                ds.SEED_ID,
                ds.room_link
            FROM duo_seeds ds
            JOIN daily_duo_teams ddt
            ON ddt.team_id = ds.team_id
            AND ddt.team_id = {player_1_current_team}
            JOIN daily_duo_seeds dds
            on ds.seed_id = dds.seed_id
            AND dds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d');"""
        results = execute(conn, sql, fetch_results = True)
        close_connection(conn)
        if len(results) > 0:
            room_link = results[0]["room_link"]
        else:
            seed_link = get_todays_daily_duo_seed_link()
            conn = get_connection()
            room_link = ap_tools.get_redirected_url(seed_link.replace("/seed/", "/new_room/"))
            sql = f"""INSERT INTO duo_seeds 
                (
                    team_id, 
                    seed_id, 
                    room_link,
                    start_time,
                    complete_time
                ) 
                VALUES
                (
                    {player_1_current_team},
                    (SELECT SEED_ID FROM daily_duo_seeds WHERE SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')),
                    '{room_link}',
                    null,
                    null
                );"""
            execute(conn, sql)
            close_connection(conn)
        return_str = f"Seed link for Team {player_1_current_team} (<@{discord_id}>'s team):\n{room_link}"
        return return_str

def get_todays_daily_duo_seed_link():
    conn = get_connection()
    sql = """
        SELECT
            seed_id,
            seed_date,
            seed_link
        FROM daily_duo_seeds
        WHERE SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d');"""
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        seed_link = results[0]["seed_link"]
    else:
        sql = "SELECT DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d') as est_date;"
        results = execute(conn, sql, fetch_results = True)
        date = results[0]["est_date"]
        seed_link = ap_tools.generate_daily_duo_seed(date)
        sql = "INSERT INTO daily_duo_seeds (seed_date, seed_link) values (%s, %s);"
        args = (date, seed_link)
        execute(conn, sql, args = args)
    close_connection(conn)
    return seed_link

def check_daily_duo_seed_complete(discord_id):
    current_team = daily_duo_get_current_team(discord_id)
    if not current_team:
        return f"<@{discord_id}> not currently assignd to a team!"
    print("Checking if seed has already been started by team...")
    if not daily_duo_seed_started(current_team):
        return "Daily duo seed not started."
    print("Checking if seed has already been completed by team...")
    if daily_duo_seed_already_complete(current_team):
        return "Daily duo seed is already completed!"
    print("Getting teams seed_id and room_link...")
    seed_id, room_link = get_teams_daily_seed_room_link(current_team)
    print("Checking if that room has all slots complete...")
    start_time, end_time, duration = html_tools.get_event_times(room_link)
    if not end_time:
        return "All slots in your team's seed room have not goaled."
    conn = get_connection()
    sql = f"""UPDATE duo_seeds
            SET start_time = STR_TO_DATE('{str(start_time)}','%Y-%m-%d %H:%i:%s.%f')
            , complete_time = STR_TO_DATE('{str(end_time)}','%Y-%m-%d %H:%i:%s.%f')
            WHERE seed_id = {seed_id}
            and room_link = '{room_link}';"""
    execute(conn, sql)
    close_connection(conn)
    return f"Seed completed in {str(duration)}!"

def daily_duo_seed_started(current_team):
    conn = get_connection()
    sql = f"""
    SELECT
        1
    FROM duo_seeds ds
    JOIN daily_duo_seeds dds
    ON ds.seed_id = dds.seed_id
    AND dds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')
    WHERE ds.team_id = {current_team}
    """
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        close_connection(conn)
        return True
    close_connection(conn)
    return False

def daily_duo_seed_already_complete(current_team):
    conn = get_connection()
    sql = f"""
    SELECT
        ds.complete_time
    FROM duo_seeds ds
    JOIN daily_duo_seeds dds
    ON ds.seed_id = dds.seed_id
    AND dds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')
    WHERE ds.complete_time is not null
    AND ds.team_id = {current_team}
    """
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        close_connection(conn)
        return True
    close_connection(conn)
    return False

def get_teams_daily_seed_room_link(current_team):
    conn = get_connection()
    sql = f"""
    SELECT
        ds.room_link,
        dds.seed_id
    FROM duo_seeds ds
    JOIN daily_duo_seeds dds
    ON ds.seed_id = dds.seed_id
    AND dds.SEED_DATE = DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%Y-%m-%d')
    AND ds.team_id = {current_team};"""
    results = execute(conn, sql, fetch_results = True)
    if len(results) > 0:
        room_link = results[0]["room_link"]
        seed_id = results[0]["seed_id"]
        close_connection(conn)
        return seed_id, room_link
    close_connection(conn)
    return None, None

def get_daily_duo_leaderboard():
    conn = get_connection()
    sql = f"""select * from vw_daily_duo_leaderboard"""
    results = execute(conn, sql, fetch_results = True)
    return_str = ""
    player = 1
    digit_map = {
        "0": "0️⃣",
        "1": "🥇",
        "2": "🥈",
        "3": "🥉",
        "4": "4️⃣",
        "5": "5️⃣",
        "6": "6️⃣",
        "7": "7️⃣",
        "8": "8️⃣",
        "9": "9️⃣"
    }
    for row in results:
        if str(player) in digit_map.keys():
            return_str = f"\n{digit_map[str(player)]}: <@{row["p1_discord_id"]}> + <@{row["p2_discord_id"]}> - {row["run_time"]}"
    return return_str