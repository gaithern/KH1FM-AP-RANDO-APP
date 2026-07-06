"""DB access for the KH1 item draft feature (see schema/draft_tables.sql).

Mirrors mysql_tools.py's approach (pymysql, one connection per call) and
reuses its get_connection/execute/close_connection helpers directly rather
than duplicating them.
"""

import secrets

import mysql_tools
from draft_formats import get_draft_format
from draft_item_pool import build_pool

# No 0/O/1/I/L - avoids characters that look alike when a player types a
# code someone else read out loud or shared as a screenshot.
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 8

STATUS_LOBBY = "lobby"
STATUS_DRAFTING = "drafting"
STATUS_AWAITING_YAML = "awaiting_yaml"
STATUS_GENERATING = "generating"
STATUS_SENDING_ITEMS = "sending_items"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"

GRID_SIZE = 3

# (line_type, line_index) -> [(row, col), ...] cells that make up that line
# of a 3x3 grid. Diagonal 0 is top-left to bottom-right, diagonal 1 is
# top-right to bottom-left.
GRID_LINES: dict[tuple[str, int], list[tuple[int, int]]] = {
    ("row", 0): [(0, 0), (0, 1), (0, 2)],
    ("row", 1): [(1, 0), (1, 1), (1, 2)],
    ("row", 2): [(2, 0), (2, 1), (2, 2)],
    ("column", 0): [(0, 0), (1, 0), (2, 0)],
    ("column", 1): [(0, 1), (1, 1), (2, 1)],
    ("column", 2): [(0, 2), (1, 2), (2, 2)],
    ("diagonal", 0): [(0, 0), (1, 1), (2, 2)],
    ("diagonal", 1): [(0, 2), (1, 1), (2, 0)],
}


def get_player_id(discord_id) -> int | None:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn, "SELECT player_id FROM players WHERE discord_id = %s", args=(discord_id,), fetch_results=True
    )
    mysql_tools.close_connection(conn)
    return rows[0]["player_id"] if rows else None


def _generate_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def resolve_join_code(join_code: str) -> int | None:
    """Public draft games are referenced everywhere outside this module
    (URLs, API paths) by this random code rather than the sequential
    game_id, so a low integer can't just be guessed/enumerated."""
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn, "SELECT game_id FROM draft_games WHERE join_code = %s", args=(join_code,), fetch_results=True
    )
    mysql_tools.close_connection(conn)
    return rows[0]["game_id"] if rows else None


def create_game(created_by_player_id: int, draft_type: str, max_players: int, item_categories: list[str],
                picks_per_player: int | None = None, num_grids: int | None = None) -> str:
    get_draft_format(draft_type)  # raises ValueError if unknown
    if draft_type == "grid":
        if max_players != 2:
            raise ValueError("Grid draft only supports 2 players")
        if not num_grids or num_grids < 1:
            raise ValueError("num_grids must be a positive integer")
        picks_per_player = None
    else:
        if not picks_per_player or picks_per_player < 1:
            raise ValueError("picks_per_player must be a positive integer")
        num_grids = None

    conn = mysql_tools.get_connection()

    join_code = _generate_join_code()
    while mysql_tools.execute(conn, "SELECT 1 FROM draft_games WHERE join_code = %s",
                               args=(join_code,), fetch_results=True):
        join_code = _generate_join_code()

    mysql_tools.execute(
        conn,
        """INSERT INTO draft_games
           (created_by_player_id, draft_type, status, max_players, picks_per_player, num_grids,
            item_categories, join_code)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        args=(created_by_player_id, draft_type, STATUS_LOBBY, max_players, picks_per_player, num_grids,
              ",".join(item_categories), join_code),
    )
    rows = mysql_tools.execute(conn, "SELECT LAST_INSERT_ID() as game_id", fetch_results=True)
    game_id = rows[0]["game_id"]
    mysql_tools.execute(
        conn, "INSERT INTO draft_seats (game_id, seat_number, player_id) VALUES (%s, 1, %s)",
        args=(game_id, created_by_player_id),
    )
    mysql_tools.close_connection(conn)
    return join_code


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

    conn = mysql_tools.get_connection()
    if game["draft_type"] == "grid":
        pool_items = build_pool(game["item_categories"].split(","), game["num_grids"] * GRID_SIZE * GRID_SIZE)
        item_iter = iter(pool_items)
        for grid_number in range(game["num_grids"]):
            for row in range(GRID_SIZE):
                for col in range(GRID_SIZE):
                    item_name, category = next(item_iter)
                    mysql_tools.execute(
                        conn,
                        """INSERT INTO draft_pool (game_id, item_name, category, grid_number, grid_row, grid_col)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        args=(game_id, item_name, category, grid_number, row, col),
                    )
    else:
        pool_items = build_pool(game["item_categories"].split(","), len(seats) * game["picks_per_player"])
        for item_name, category in pool_items:
            mysql_tools.execute(conn, "INSERT INTO draft_pool (game_id, item_name, category) VALUES (%s, %s, %s)",
                                 args=(game_id, item_name, category))
    mysql_tools.execute(conn, "UPDATE draft_games SET status = %s WHERE game_id = %s",
                         args=(STATUS_DRAFTING, game_id))
    mysql_tools.close_connection(conn)


def total_items(game: dict, num_seats: int) -> int:
    """Size of the full item pool for this game - snake draft splits it
    evenly per seat, grid draft is always num_grids grids of 9."""
    if game["draft_type"] == "grid":
        return game["num_grids"] * GRID_SIZE * GRID_SIZE
    return num_seats * game["picks_per_player"]


def get_pool(game_id: int) -> list[dict]:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn,
        "SELECT item_name, category FROM draft_pool WHERE game_id = %s AND taken_flag = 'N' ORDER BY item_name",
        args=(game_id,), fetch_results=True,
    )
    mysql_tools.close_connection(conn)
    return rows


def get_grid(game_id: int) -> list[dict]:
    """Every cell of every grid for this game, taken or not - the grid draft
    UI needs to show gaps left by already-claimed cells, unlike the plain
    item-pool UI which only ever lists what's still available."""
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn,
        """SELECT grid_number, grid_row, grid_col, item_name, category, taken_flag
           FROM draft_pool WHERE game_id = %s ORDER BY grid_number, grid_row, grid_col""",
        args=(game_id,), fetch_results=True,
    )
    mysql_tools.close_connection(conn)
    return rows


def get_picks(game_id: int) -> list[dict]:
    conn = mysql_tools.get_connection()
    rows = mysql_tools.execute(
        conn,
        """SELECT pick_number, seat_number, item_name, turn_number FROM draft_picks
           WHERE game_id = %s ORDER BY pick_number""",
        args=(game_id,), fetch_results=True,
    )
    mysql_tools.close_connection(conn)
    return rows


def _seat_on_the_clock_or_raise(game: dict, seats: list[dict], picks: list[dict], seat: dict) -> None:
    draft_format = get_draft_format(game["draft_type"])
    on_the_clock = draft_format.seat_on_the_clock(len(seats), picks, total_items(game, len(seats)))
    if on_the_clock is None or seats[on_the_clock]["seat_number"] != seat["seat_number"]:
        raise ValueError("It is not your turn")


def _finish_draft_if_complete(conn, game_id: int, picks_now: int, pool_size: int) -> None:
    if picks_now >= pool_size:
        mysql_tools.execute(conn, "UPDATE draft_games SET status = %s WHERE game_id = %s",
                             args=(STATUS_AWAITING_YAML, game_id))


def record_pick(game_id: int, caller_player_id: int, item_name: str) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["draft_type"] == "grid":
        raise ValueError("Use the grid pick endpoint for grid draft games")
    if game["status"] != STATUS_DRAFTING:
        raise ValueError("This draft game is not currently drafting")
    seat = get_seat_for_player(game_id, caller_player_id)
    if seat is None:
        raise ValueError("You are not seated in this draft game")

    seats = get_seats(game_id)
    picks = get_picks(game_id)
    _seat_on_the_clock_or_raise(game, seats, picks, seat)

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

    next_pick_number = len(picks) + 1
    mysql_tools.execute(
        conn,
        "INSERT INTO draft_picks (game_id, pick_number, seat_number, item_name, turn_number) VALUES (%s, %s, %s, %s, %s)",
        args=(game_id, next_pick_number, seat["seat_number"], item_name, next_pick_number),
    )
    mysql_tools.execute(
        conn, "UPDATE draft_pool SET taken_flag = 'Y' WHERE pool_id = %s",
        args=(pool_id,),
    )
    _finish_draft_if_complete(conn, game_id, next_pick_number, total_items(game, len(seats)))
    mysql_tools.close_connection(conn)


def record_grid_pick(game_id: int, caller_player_id: int, grid_number: int, line_type: str, line_index: int) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["draft_type"] != "grid":
        raise ValueError("This is not a grid draft game")
    if game["status"] != STATUS_DRAFTING:
        raise ValueError("This draft game is not currently drafting")
    if (line_type, line_index) not in GRID_LINES:
        raise ValueError("Invalid line_type/line_index")
    seat = get_seat_for_player(game_id, caller_player_id)
    if seat is None:
        raise ValueError("You are not seated in this draft game")

    seats = get_seats(game_id)
    picks = get_picks(game_id)
    _seat_on_the_clock_or_raise(game, seats, picks, seat)

    grid_cells = get_grid(game_id)
    untaken_by_grid: dict[int, list[dict]] = {}
    for cell in grid_cells:
        if cell["taken_flag"] == "N":
            untaken_by_grid.setdefault(cell["grid_number"], []).append(cell)
    current_grid_number = min(untaken_by_grid) if untaken_by_grid else None
    if current_grid_number is None:
        raise ValueError("This draft game is not currently drafting")
    if grid_number != current_grid_number:
        raise ValueError("That grid is not currently being drafted")

    line_positions = set(GRID_LINES[(line_type, line_index)])
    cells_to_take = [cell for cell in untaken_by_grid[grid_number]
                      if (cell["grid_row"], cell["grid_col"]) in line_positions]
    if not cells_to_take:
        raise ValueError("That line has no cards left to take")

    conn = mysql_tools.get_connection()
    turn_number = len(picks) + 1
    next_pick_number = len(picks) + 1
    for cell in cells_to_take:
        mysql_tools.execute(
            conn,
            """UPDATE draft_pool SET taken_flag = 'Y'
               WHERE game_id = %s AND grid_number = %s AND grid_row = %s AND grid_col = %s""",
            args=(game_id, grid_number, cell["grid_row"], cell["grid_col"]),
        )
        mysql_tools.execute(
            conn,
            "INSERT INTO draft_picks (game_id, pick_number, seat_number, item_name, turn_number) VALUES (%s, %s, %s, %s, %s)",
            args=(game_id, next_pick_number, seat["seat_number"], cell["item_name"], turn_number),
        )
        next_pick_number += 1
    _finish_draft_if_complete(conn, game_id, next_pick_number - 1, total_items(game, len(seats)))
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
