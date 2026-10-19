import pymysql

import ap_tools
import html_tools
from envr import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

TODAY_IN_NEW_YORK_SQL = "DATE_FORMAT(CONVERT_TZ(UTC_TIMESTAMP(), 'UTC', 'America/New_York'), '%%Y-%%m-%%d')"

RANK_EMOJIS = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}
LEADERBOARD_SIZE = 9


def get_connection():
    connection = None
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except pymysql.Error as error:
        print(f"Error connecting to MySQL database: {error}")
    return connection


def close_connection(connection, rollback=False):
    try:
        if rollback:
            connection.rollback()
        else:
            connection.commit()
        connection.close()
    except Exception as error:
        print(f"Error closing MySQL database connection: {error}")


def execute(connection, sql, args=None, fetch_results=False):
    if args is None:
        args = ()
    with connection.cursor() as cursor:
        print(f"SQL statement to execute: {sql} with args {args}")
        cursor.execute(sql, args)

        if not fetch_results:
            return []
        results = cursor.fetchall()
        print(results)
        return results


def fetch_rows(sql, args=None):
    connection = get_connection()
    rows = execute(connection, sql, args=args, fetch_results=True)
    close_connection(connection)
    return rows


def run_statement(sql, args=None):
    connection = get_connection()
    execute(connection, sql, args=args)
    close_connection(connection)


def get_todays_date_in_new_york():
    rows = fetch_rows(f"SELECT {TODAY_IN_NEW_YORK_SQL} as est_date;")
    return rows[0]["est_date"]


def register_player(discord_id, discord_name):
    rows = fetch_rows("SELECT player_id FROM players WHERE discord_id = %s", args=(discord_id,))
    player_already_registered = len(rows) > 0
    if player_already_registered:
        return
    name_without_semicolons = discord_name.replace(";", "")
    run_statement(
        "INSERT INTO players (discord_id, discord_name) VALUES (%s, %s)",
        args=(discord_id, name_without_semicolons),
    )


def get_todays_daily_seed_link():
    rows = fetch_rows(f"""
        SELECT
            seed_id,
            seed_date,
            seed_link,
            seed_zip_path
        FROM daily_seeds
        WHERE SEED_DATE = {TODAY_IN_NEW_YORK_SQL};""")
    if len(rows) > 0:
        return rows[0]["seed_link"], rows[0]["seed_zip_path"]

    date = get_todays_date_in_new_york()
    seed_link, seed_zip_path = ap_tools.generate_daily_seed()
    run_statement(
        "INSERT INTO daily_seeds (seed_date, seed_link, seed_zip_path) values (%s, %s, %s);",
        args=(date, seed_link, seed_zip_path),
    )
    return seed_link, seed_zip_path


def get_players_daily_seed(discord_id):
    rows = fetch_rows(f"""
        SELECT
            ps.PLAYER_ID,
            ps.SEED_ID,
            ps.room_link,
            ds.seed_zip_path
        FROM player_seeds ps
        JOIN players p
        ON p.player_id = ps.player_id
        AND p.discord_id = %s
        JOIN daily_seeds ds
        on ds.seed_id = ps.seed_id
        AND ds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL};""", args=(discord_id,))
    if len(rows) > 0:
        return rows[0]["room_link"], rows[0]["seed_zip_path"]

    seed_link, seed_zip_path = get_todays_daily_seed_link()
    room_link = ap_tools.new_room_link(seed_link)
    run_statement(f"""INSERT INTO player_seeds
        (
            player_id,
            seed_id,
            room_link,
            start_time,
            complete_time
        )
        VALUES
        (
            (SELECT PLAYER_ID FROM players WHERE discord_id = %s),
            (SELECT SEED_ID FROM daily_seeds WHERE SEED_DATE = {TODAY_IN_NEW_YORK_SQL}),
            %s,
            null,
            null
        );""", args=(discord_id, room_link))
    return room_link, seed_zip_path


def get_players_daily_seed_room_link(discord_id):
    rows = fetch_rows(f"""
    SELECT
        ps.room_link,
        ds.seed_id
    FROM player_seeds ps
    JOIN players p
    ON ps.player_id = p.player_id
    AND p.discord_id = %s
    JOIN daily_seeds ds
    ON ps.seed_id = ds.seed_id
    AND ds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL};""", args=(discord_id,))
    if len(rows) == 0:
        return None, None
    return rows[0]["seed_id"], rows[0]["room_link"]


def daily_seed_already_complete(discord_id):
    rows = fetch_rows(f"""
    SELECT
        ps.complete_time
    FROM player_seeds ps
    JOIN players p
    ON ps.player_id = p.player_id
    AND p.discord_id = %s
    JOIN daily_seeds ds
    ON ps.seed_id = ds.seed_id
    AND ds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL}
    WHERE ps.complete_time is not null;
    """, args=(discord_id,))
    return len(rows) > 0


def daily_seed_started(discord_id):
    rows = fetch_rows(f"""
    SELECT
        1
    FROM player_seeds ps
    JOIN players p
    ON ps.player_id = p.player_id
    AND p.discord_id = %s
    JOIN daily_seeds ds
    ON ps.seed_id = ds.seed_id
    AND ds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL};
    """, args=(discord_id,))
    return len(rows) > 0


def save_run_times(table_name, seed_id, room_link, start_time, end_time):
    run_statement(
        f"UPDATE {table_name} SET start_time = %s, complete_time = %s WHERE seed_id = %s and room_link = %s;",
        args=(start_time, end_time, seed_id, room_link),
    )


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
    save_run_times("player_seeds", seed_id, room_link, start_time, end_time)
    return f"Seed completed in {str(duration)}!"


def get_daily_leaderboard():
    rows = fetch_rows("select * from vw_daily_leaderboard")
    lines = []
    leaderboard = []
    rank = 0
    for row in rows:
        rank = rank + 1
        if rank > LEADERBOARD_SIZE:
            break
        lines.append(f"{RANK_EMOJIS[rank]}: <@{row['discord_id']}> - {row['run_time']}")

        run_time = None
        if row['run_time'] is not None:
            run_time = str(row['run_time'])
        leaderboard.append({
            'rank': rank,
            'discord_name': row['discord_name'],
            'run_time': run_time,
        })
    return "\n".join(lines), leaderboard


def daily_duo_get_current_team(discord_id):
    rows = fetch_rows(f"""select
                    coalesce(ddt1.team_id, ddt2.team_id) as team_id,
                    p.discord_name
                from (select * from players where discord_id = %s) p
                left join (select * from daily_duo_teams where team_up_date = {TODAY_IN_NEW_YORK_SQL}) ddt1
                on p.player_id = ddt1.player_id_1
                left join (select * from daily_duo_teams where team_up_date = {TODAY_IN_NEW_YORK_SQL}) ddt2
                on p.player_id = ddt2.player_id_2
                where coalesce(ddt1.team_id, ddt2.team_id) is not null""", args=(discord_id,))
    if len(rows) == 0:
        return None
    return rows[0]["team_id"]


def daily_duo_register_team(discord_id_1, discord_id_2):
    run_statement(f"""insert into daily_duo_teams
                (player_id_1, player_id_2, team_up_date)
                values
                (
                    (select player_id from players where discord_id = %s),
                    (select player_id from players where discord_id = %s),
                    {TODAY_IN_NEW_YORK_SQL}
                )""", args=(discord_id_1, discord_id_2))


def daily_duo_team_up(discord_id_1, discord_name_1, discord_id_2, discord_name_2):
    register_player(discord_id_1, discord_name_1)
    register_player(discord_id_2, discord_name_2)
    player_1_current_team = daily_duo_get_current_team(discord_id_1)
    player_2_current_team = daily_duo_get_current_team(discord_id_2)

    message = ""
    if player_1_current_team:
        message = message + f"<@{discord_id_1}> is already assigned to team {player_1_current_team}\n"
    if player_2_current_team:
        message = message + f"<@{discord_id_2}> is already assigned to team {player_2_current_team}\n"
    if not player_1_current_team and not player_2_current_team:
        daily_duo_register_team(discord_id_1, discord_id_2)
        message = message + f"Success!  <@{discord_id_1}> and <@{discord_id_2}> are now teamed up for today!"
    return message


def get_teams_daily_seed(discord_id):
    team_id = daily_duo_get_current_team(discord_id)
    if not team_id:
        return f"<@{discord_id}> is not teamed up!  Team up using `!daily_duo_team_up` and mentioning your desired teammate"

    rows = fetch_rows(f"""
        SELECT
            ds.TEAM_ID,
            ds.SEED_ID,
            ds.room_link
        FROM duo_seeds ds
        JOIN daily_duo_teams ddt
        ON ddt.team_id = ds.team_id
        AND ddt.team_id = %s
        JOIN daily_duo_seeds dds
        on ds.seed_id = dds.seed_id
        AND dds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL};""", args=(team_id,))
    if len(rows) > 0:
        room_link = rows[0]["room_link"]
    else:
        seed_link = get_todays_daily_duo_seed_link()
        room_link = ap_tools.new_room_link(seed_link)
        run_statement(f"""INSERT INTO duo_seeds
            (
                team_id,
                seed_id,
                room_link,
                start_time,
                complete_time
            )
            VALUES
            (
                %s,
                (SELECT SEED_ID FROM daily_duo_seeds WHERE SEED_DATE = {TODAY_IN_NEW_YORK_SQL}),
                %s,
                null,
                null
            );""", args=(team_id, room_link))
    return f"Seed link for Team {team_id} (<@{discord_id}>'s team):\n{room_link}"


def get_todays_daily_duo_seed_link():
    rows = fetch_rows(f"""
        SELECT
            seed_id,
            seed_date,
            seed_link
        FROM daily_duo_seeds
        WHERE SEED_DATE = {TODAY_IN_NEW_YORK_SQL};""")
    if len(rows) > 0:
        return rows[0]["seed_link"]

    date = get_todays_date_in_new_york()
    seed_link = ap_tools.generate_daily_duo_seed()
    run_statement(
        "INSERT INTO daily_duo_seeds (seed_date, seed_link) values (%s, %s);",
        args=(date, seed_link),
    )
    return seed_link


def check_daily_duo_seed_complete(discord_id):
    team_id = daily_duo_get_current_team(discord_id)
    if not team_id:
        return f"<@{discord_id}> not currently assignd to a team!"
    print("Checking if seed has already been started by team...")
    if not daily_duo_seed_started(team_id):
        return "Daily duo seed not started."
    print("Checking if seed has already been completed by team...")
    if daily_duo_seed_already_complete(team_id):
        return "Daily duo seed is already completed!"
    print("Getting teams seed_id and room_link...")
    seed_id, room_link = get_teams_daily_seed_room_link(team_id)
    print("Checking if that room has all slots complete...")
    start_time, end_time, duration = html_tools.get_event_times(room_link)
    if not end_time:
        return "All slots in your team's seed room have not goaled."
    save_run_times("duo_seeds", seed_id, room_link, start_time, end_time)
    return f"Seed completed in {str(duration)}!"


def daily_duo_seed_started(team_id):
    rows = fetch_rows(f"""
    SELECT
        1
    FROM duo_seeds ds
    JOIN daily_duo_seeds dds
    ON ds.seed_id = dds.seed_id
    AND dds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL}
    WHERE ds.team_id = %s
    """, args=(team_id,))
    return len(rows) > 0


def daily_duo_seed_already_complete(team_id):
    rows = fetch_rows(f"""
    SELECT
        ds.complete_time
    FROM duo_seeds ds
    JOIN daily_duo_seeds dds
    ON ds.seed_id = dds.seed_id
    AND dds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL}
    WHERE ds.complete_time is not null
    AND ds.team_id = %s
    """, args=(team_id,))
    return len(rows) > 0


def get_teams_daily_seed_room_link(team_id):
    rows = fetch_rows(f"""
    SELECT
        ds.room_link,
        dds.seed_id
    FROM duo_seeds ds
    JOIN daily_duo_seeds dds
    ON ds.seed_id = dds.seed_id
    AND dds.SEED_DATE = {TODAY_IN_NEW_YORK_SQL}
    AND ds.team_id = %s;""", args=(team_id,))
    if len(rows) == 0:
        return None, None
    return rows[0]["seed_id"], rows[0]["room_link"]


def get_daily_duo_leaderboard():
    rows = fetch_rows("select * from vw_daily_duo_leaderboard")
    lines = []
    rank = 0
    for row in rows:
        rank = rank + 1
        if rank > LEADERBOARD_SIZE:
            break
        lines.append(f"{RANK_EMOJIS[rank]}: <@{row['p1_discord_id']}> + <@{row['p2_discord_id']}> - {row['run_time']}")
    return "\n".join(lines)
