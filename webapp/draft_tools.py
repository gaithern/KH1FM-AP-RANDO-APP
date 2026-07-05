"""DB access for the KH1 item draft feature (see schema/draft_tables.sql).

Mirrors mysql_tools.py's approach (pymysql, one connection per call) and
reuses its get_connection/execute/close_connection helpers directly rather
than duplicating them.
"""

import mysql_tools
from draft_formats import get_draft_format
from draft_item_pool import build_pool

STATUS_LOBBY = "lobby"
STATUS_DRAFTING = "drafting"
STATUS_AWAITING_YAML = "awaiting_yaml"
STATUS_GENERATING = "generating"
STATUS_SENDING_ITEMS = "sending_items"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"


def get_player_id(discord_id) -> int | None:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn, "SELECT player_id FROM players WHERE discord_id = %s", args=(discord_id,), fetch_results=True
    )
    mysql_tools.close_connection(conn)
    return rows[0]["player_id"] if rows else None


def create_game(created_by_player_id: int, draft_type: str, max_players: int, picks_per_player: int,
                item_categories: list[str]) -> int:
    get_draft_format(draft_type)  # raises ValueError if unknown
    conn = mysql_tools.get_connection()
    mysql_tools.execute(
        conn,
        """INSERT INTO draft_games
           (created_by_player_id, draft_type, status, max_players, picks_per_player, item_categories)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        args=(created_by_player_id, draft_type, STATUS_LOBBY, max_players, picks_per_player,
              ",".join(item_categories)),
    )
    rows = mysql_tools.execute(conn, "SELECT LAST_INSERT_ID() as game_id", fetch_results=True)
    game_id = rows[0]["game_id"]
    mysql_tools.execute(
        conn, "INSERT INTO draft_seats (game_id, seat_number, player_id) VALUES (%s, 1, %s)",
        args=(game_id, created_by_player_id),
    )
    mysql_tools.close_connection(conn)
    return game_id


def get_game(game_id: int) -> dict | None:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(conn, "SELECT * FROM draft_games WHERE game_id = %s", args=(game_id,),
                                fetch_results=True)
    mysql_tools.close_connection(conn)
    return rows[0] if rows else None


def get_seats(game_id: int) -> list[dict]:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn,
        """SELECT ds.seat_number, ds.player_id, p.discord_name, ds.room_link, ds.items_sent_flag
           FROM draft_seats ds JOIN players p ON p.player_id = ds.player_id
           WHERE ds.game_id = %s ORDER BY ds.seat_number""",
        args=(game_id,), fetch_results=True,
    )
    mysql_tools.close_connection(conn)
    return rows


def get_seat_for_player(game_id: int, player_id: int) -> dict | None:
    for seat in get_seats(game_id):
        if seat["player_id"] == player_id:
            return seat
    return None


def join_game(game_id: int, player_id: int) -> int:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["status"] != STATUS_LOBBY:
        raise ValueError("This draft game has already started")
    seats = get_seats(game_id)
    if any(seat["player_id"] == player_id for seat in seats):
        raise ValueError("Already joined this draft game")
    if len(seats) >= game["max_players"]:
        raise ValueError("This draft game is full")
    seat_number = len(seats) + 1
    conn = mysql_tools.get_connection()
    mysql_tools.execute(
        conn, "INSERT INTO draft_seats (game_id, seat_number, player_id) VALUES (%s, %s, %s)",
        args=(game_id, seat_number, player_id),
    )
    mysql_tools.close_connection(conn)
    return seat_number


def start_game(game_id: int, caller_player_id: int) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["created_by_player_id"] != caller_player_id:
        raise ValueError("Only the host can start the draft")
    if game["status"] != STATUS_LOBBY:
        raise ValueError("This draft game has already started")
    seats = get_seats(game_id)
    if len(seats) < 2:
        raise ValueError("Need at least 2 players to start")
    pool_items = build_pool(game["item_categories"].split(","), len(seats) * game["picks_per_player"])
    conn = mysql_tools.get_connection()
    for item_name, category in pool_items:
        mysql_tools.execute(conn, "INSERT INTO draft_pool (game_id, item_name, category) VALUES (%s, %s, %s)",
                             args=(game_id, item_name, category))
    mysql_tools.execute(conn, "UPDATE draft_games SET status = %s WHERE game_id = %s",
                         args=(STATUS_DRAFTING, game_id))
    mysql_tools.close_connection(conn)


def get_pool(game_id: int) -> list[dict]:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn,
        "SELECT item_name, category FROM draft_pool WHERE game_id = %s AND taken_flag = 'N' ORDER BY item_name",
        args=(game_id,), fetch_results=True,
    )
    mysql_tools.close_connection(conn)
    return rows


def get_picks(game_id: int) -> list[dict]:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn, "SELECT pick_number, seat_number, item_name FROM draft_picks WHERE game_id = %s ORDER BY pick_number",
        args=(game_id,), fetch_results=True,
    )
    mysql_tools.close_connection(conn)
    return rows


def record_pick(game_id: int, caller_player_id: int, item_name: str) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["status"] != STATUS_DRAFTING:
        raise ValueError("This draft game is not currently drafting")
    seat = get_seat_for_player(game_id, caller_player_id)
    if seat is None:
        raise ValueError("You are not seated in this draft game")

    seats = get_seats(game_id)
    picks = get_picks(game_id)
    draft_format = get_draft_format(game["draft_type"])
    on_the_clock = draft_format.seat_on_the_clock(len(seats), game["picks_per_player"], len(picks))
    if on_the_clock is None or seats[on_the_clock]["seat_number"] != seat["seat_number"]:
        raise ValueError("It is not your turn")

    conn = mysql_tools.get_connection()
    # Claim one specific untaken row by pool_id, not by item_name - the pool
    # can contain duplicate item names (build_pool fills out small
    # categories with repeats), so updating by item_name alone would mark
    # every copy of that item taken instead of just this one.
    available_rows = mysql_tools.execute(
        conn, "SELECT pool_id FROM draft_pool WHERE game_id = %s AND item_name = %s AND taken_flag = 'N' LIMIT 1",
        args=(game_id, item_name), fetch_results=True,
    )
    if not available_rows:
        mysql_tools.close_connection(conn)
        raise ValueError("That item is not available")
    pool_id = available_rows[0]["pool_id"]

    mysql_tools.execute(
        conn, "INSERT INTO draft_picks (game_id, pick_number, seat_number, item_name) VALUES (%s, %s, %s, %s)",
        args=(game_id, len(picks) + 1, seat["seat_number"], item_name),
    )
    mysql_tools.execute(
        conn, "UPDATE draft_pool SET taken_flag = 'Y' WHERE pool_id = %s",
        args=(pool_id,),
    )
    if draft_format.is_draft_complete(len(seats), game["picks_per_player"], len(picks) + 1):
        mysql_tools.execute(conn, "UPDATE draft_games SET status = %s WHERE game_id = %s",
                             args=(STATUS_AWAITING_YAML, game_id))
    mysql_tools.close_connection(conn)


def set_error(game_id: int, message: str) -> None:
    conn = mysql_tools.get_connection()
    mysql_tools.execute(conn, "UPDATE draft_games SET status = %s, error_message = %s WHERE game_id = %s",
                         args=(STATUS_ERROR, message, game_id))
    mysql_tools.close_connection(conn)


def start_generation(game_id: int, caller_player_id: int, seed_zip_path: str) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["created_by_player_id"] != caller_player_id:
        raise ValueError("Only the host can upload settings for this draft game")
    if game["status"] != STATUS_AWAITING_YAML:
        raise ValueError("This draft game is not awaiting settings")
    conn = mysql_tools.get_connection()
    mysql_tools.execute(
        conn,
        "UPDATE draft_games SET status = %s, seed_zip_path = %s WHERE game_id = %s",
        args=(STATUS_GENERATING, seed_zip_path, game_id),
    )
    mysql_tools.close_connection(conn)


def set_generation_result(game_id: int, server_password: str, seed_link: str, slot_name: str) -> None:
    # slot_name is the resolved name from the generated multiworld, not a
    # text-parse of the uploaded YAML - see _run_draft_finalize in
    # flask_app.py for why (template placeholders like "Player{number}").
    conn = mysql_tools.get_connection()
    mysql_tools.execute(
        conn,
        "UPDATE draft_games SET status = %s, server_password = %s, seed_link = %s, slot_name = %s WHERE game_id = %s",
        args=(STATUS_SENDING_ITEMS, server_password, seed_link, slot_name, game_id),
    )
    mysql_tools.close_connection(conn)


def set_seat_room_link(game_id: int, seat_number: int, room_link: str) -> None:
    conn = mysql_tools.get_connection()
    mysql_tools.execute(
        conn, "UPDATE draft_seats SET room_link = %s WHERE game_id = %s AND seat_number = %s",
        args=(room_link, game_id, seat_number),
    )
    mysql_tools.close_connection(conn)


def set_seat_items_sent(game_id: int, seat_number: int) -> None:
    conn = mysql_tools.get_connection()
    mysql_tools.execute(
        conn, "UPDATE draft_seats SET items_sent_flag = 'Y' WHERE game_id = %s AND seat_number = %s",
        args=(game_id, seat_number),
    )
    mysql_tools.close_connection(conn)
    seats = get_seats(game_id)
    if all(seat["items_sent_flag"] == "Y" for seat in seats):
        conn = mysql_tools.get_connection()
        mysql_tools.execute(conn, "UPDATE draft_games SET status = %s WHERE game_id = %s",
                             args=(STATUS_COMPLETE, game_id))
        mysql_tools.close_connection(conn)
