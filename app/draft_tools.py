import secrets
from collections import Counter

import mysql_tools
from draft_formats import get_draft_format
from draft_item_pool import build_pool, validate_categories

JOIN_CODE_LETTERS_THAT_CANNOT_BE_CONFUSED = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 8

STATUS_LOBBY = "lobby"
STATUS_GENERATING = "generating"
STATUS_POOL_SELECTION = "pool_selection"
STATUS_DRAFTING = "drafting"
STATUS_SENDING_ITEMS = "sending_items"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"

STATUSES_BEFORE_DRAFT_STARTS = (STATUS_LOBBY, STATUS_GENERATING, STATUS_POOL_SELECTION)

MINIMUM_PLAYERS = 2
GRID_DRAFT_PLAYERS = 2
GRID_SIZE = 3

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
    rows = mysql_tools.fetch_rows("SELECT player_id FROM players WHERE discord_id = %s", args=(discord_id,))
    if not rows:
        return None
    return rows[0]["player_id"]


def generate_join_code() -> str:
    join_code = ""
    for position in range(JOIN_CODE_LENGTH):
        join_code = join_code + secrets.choice(JOIN_CODE_LETTERS_THAT_CANNOT_BE_CONFUSED)
    return join_code


def resolve_join_code(join_code: str) -> int | None:
    rows = mysql_tools.fetch_rows("SELECT game_id FROM draft_games WHERE join_code = %s", args=(join_code,))
    if not rows:
        return None
    return rows[0]["game_id"]


def join_code_is_taken(connection, join_code: str) -> bool:
    rows = mysql_tools.execute(
        connection, "SELECT 1 FROM draft_games WHERE join_code = %s", args=(join_code,), fetch_results=True
    )
    return len(rows) > 0


def create_game(created_by_player_id: int, draft_type: str, max_players: int, item_categories: list[str],
                picks_per_player: int | None = None, num_grids: int | None = None) -> str:
    get_draft_format(draft_type)
    validate_categories(item_categories)
    if draft_type == "grid":
        if max_players != GRID_DRAFT_PLAYERS:
            raise ValueError("Grid draft only supports 2 players")
        if not num_grids or num_grids < 1:
            raise ValueError("num_grids must be a positive integer")
        picks_per_player = None
    else:
        if not picks_per_player or picks_per_player < 1:
            raise ValueError("picks_per_player must be a positive integer")
        num_grids = None

    connection = mysql_tools.get_connection()

    join_code = generate_join_code()
    while join_code_is_taken(connection, join_code):
        join_code = generate_join_code()

    mysql_tools.execute(
        connection,
        """INSERT INTO draft_games
           (created_by_player_id, draft_type, status, max_players, picks_per_player, num_grids,
            item_categories, join_code)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        args=(created_by_player_id, draft_type, STATUS_LOBBY, max_players, picks_per_player, num_grids,
              ",".join(item_categories), join_code),
    )
    rows = mysql_tools.execute(connection, "SELECT LAST_INSERT_ID() as game_id", fetch_results=True)
    game_id = rows[0]["game_id"]
    mysql_tools.execute(
        connection, "INSERT INTO draft_seats (game_id, seat_number, player_id) VALUES (%s, 1, %s)",
        args=(game_id, created_by_player_id),
    )
    mysql_tools.close_connection(connection)
    return join_code


def get_game(game_id: int) -> dict | None:
    rows = mysql_tools.fetch_rows("SELECT * FROM draft_games WHERE game_id = %s", args=(game_id,))
    if not rows:
        return None
    return rows[0]


def get_seats(game_id: int) -> list[dict]:
    return mysql_tools.fetch_rows(
        """SELECT ds.seat_number, ds.player_id, p.discord_name, ds.room_link, ds.items_sent_flag
           FROM draft_seats ds JOIN players p ON p.player_id = ds.player_id
           WHERE ds.game_id = %s ORDER BY ds.seat_number""",
        args=(game_id,),
    )


def find_seat_for_player(seats: list[dict], player_id) -> dict | None:
    for seat in seats:
        if seat["player_id"] == player_id:
            return seat
    return None


def get_seat_for_player(game_id: int, player_id: int) -> dict | None:
    return find_seat_for_player(get_seats(game_id), player_id)


def join_game(game_id: int, player_id: int) -> int:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["status"] not in STATUSES_BEFORE_DRAFT_STARTS:
        raise ValueError("This draft game has already started")
    seats = get_seats(game_id)
    if find_seat_for_player(seats, player_id) is not None:
        raise ValueError("Already joined this draft game")
    if len(seats) >= game["max_players"]:
        raise ValueError("This draft game is full")

    seat_number = len(seats) + 1
    mysql_tools.run_statement(
        "INSERT INTO draft_seats (game_id, seat_number, player_id) VALUES (%s, %s, %s)",
        args=(game_id, seat_number, player_id),
    )
    return seat_number


def get_candidates(game_id: int) -> list[dict]:
    return mysql_tools.fetch_rows(
        "SELECT item_name, category, quantity FROM draft_candidates WHERE game_id = %s ORDER BY category, item_name",
        args=(game_id,),
    )


def build_selected_items(candidates: list[dict], selected_item_names: list[str] | None) -> list[tuple[str, str]]:
    candidate_by_name = {}
    for candidate in candidates:
        candidate_by_name[candidate["item_name"]] = candidate

    if selected_item_names is None:
        selected_item_names = list(candidate_by_name)
    copies_by_name = Counter(selected_item_names)

    unknown_names = set(copies_by_name) - set(candidate_by_name)
    if unknown_names:
        raise ValueError(f"Not in this seed's draftable items: {sorted(unknown_names)}")

    names_with_too_many_copies = []
    for name, copies in copies_by_name.items():
        if copies > candidate_by_name[name]["quantity"]:
            names_with_too_many_copies.append(name)
    if names_with_too_many_copies:
        raise ValueError(f"More copies selected than the seed has: {sorted(names_with_too_many_copies)}")

    selected_items = []
    for name, copies in copies_by_name.items():
        category = candidate_by_name[name]["category"]
        for copy_number in range(copies):
            selected_items.append((name, category))
    return selected_items


def save_grid_pool(connection, game_id: int, num_grids: int, pool_items: list[tuple[str, str]]) -> None:
    item_index = 0
    for grid_number in range(num_grids):
        for row in range(GRID_SIZE):
            for column in range(GRID_SIZE):
                item_name, category = pool_items[item_index]
                item_index = item_index + 1
                mysql_tools.execute(
                    connection,
                    """INSERT INTO draft_pool (game_id, item_name, category, grid_number, grid_row, grid_col)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    args=(game_id, item_name, category, grid_number, row, column),
                )


def save_plain_pool(connection, game_id: int, pool_items: list[tuple[str, str]]) -> None:
    for item_name, category in pool_items:
        mysql_tools.execute(
            connection,
            "INSERT INTO draft_pool (game_id, item_name, category) VALUES (%s, %s, %s)",
            args=(game_id, item_name, category),
        )


def start_game(game_id: int, caller_player_id: int, selected_item_names: list[str] | None = None) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["created_by_player_id"] != caller_player_id:
        raise ValueError("Only the host can start the draft")
    if game["status"] == STATUS_LOBBY or game["status"] == STATUS_GENERATING:
        raise ValueError("Upload a YAML and wait for the seed to generate before starting")
    if game["status"] != STATUS_POOL_SELECTION:
        raise ValueError("This draft game has already started")
    seats = get_seats(game_id)
    if len(seats) < MINIMUM_PLAYERS:
        raise ValueError("Need at least 2 players to start")

    selected_items = build_selected_items(get_candidates(game_id), selected_item_names)
    pool_items = build_pool(selected_items, total_items(game, len(seats)))

    connection = mysql_tools.get_connection()
    if game["draft_type"] == "grid":
        save_grid_pool(connection, game_id, game["num_grids"], pool_items)
    else:
        save_plain_pool(connection, game_id, pool_items)
    mysql_tools.execute(
        connection, "UPDATE draft_games SET status = %s WHERE game_id = %s",
        args=(STATUS_DRAFTING, game_id),
    )
    mysql_tools.close_connection(connection)


def total_items(game: dict, number_of_seats: int) -> int:
    if game["draft_type"] == "grid":
        return game["num_grids"] * GRID_SIZE * GRID_SIZE
    return number_of_seats * game["picks_per_player"]


def get_pool(game_id: int) -> list[dict]:
    return mysql_tools.fetch_rows(
        "SELECT item_name, category FROM draft_pool WHERE game_id = %s AND taken_flag = 'N' ORDER BY item_name",
        args=(game_id,),
    )


def get_grid(game_id: int) -> list[dict]:
    return mysql_tools.fetch_rows(
        """SELECT grid_number, grid_row, grid_col, item_name, category, taken_flag
           FROM draft_pool WHERE game_id = %s ORDER BY grid_number, grid_row, grid_col""",
        args=(game_id,),
    )


def get_picks(game_id: int) -> list[dict]:
    return mysql_tools.fetch_rows(
        """SELECT pick_number, seat_number, item_name, turn_number FROM draft_picks
           WHERE game_id = %s ORDER BY pick_number""",
        args=(game_id,),
    )


def raise_if_not_seats_turn(game: dict, seats: list[dict], picks: list[dict], seat: dict) -> None:
    draft_format = get_draft_format(game["draft_type"])
    pool_size = total_items(game, len(seats))
    on_the_clock_index = draft_format.seat_on_the_clock(len(seats), picks, pool_size)
    if on_the_clock_index is None:
        raise ValueError("It is not your turn")
    if seats[on_the_clock_index]["seat_number"] != seat["seat_number"]:
        raise ValueError("It is not your turn")


def finish_draft_if_complete(connection, game_id: int, picks_made: int, pool_size: int) -> None:
    if picks_made >= pool_size:
        mysql_tools.execute(
            connection, "UPDATE draft_games SET status = %s WHERE game_id = %s",
            args=(STATUS_SENDING_ITEMS, game_id),
        )


def insert_pick(connection, game_id: int, pick_number: int, seat_number: int, item_name: str,
                turn_number: int) -> None:
    mysql_tools.execute(
        connection,
        "INSERT INTO draft_picks (game_id, pick_number, seat_number, item_name, turn_number) VALUES (%s, %s, %s, %s, %s)",
        args=(game_id, pick_number, seat_number, item_name, turn_number),
    )


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
    raise_if_not_seats_turn(game, seats, picks, seat)

    connection = mysql_tools.get_connection()
    one_untaken_copy = mysql_tools.execute(
        connection,
        "SELECT pool_id FROM draft_pool WHERE game_id = %s AND item_name = %s AND taken_flag = 'N' LIMIT 1",
        args=(game_id, item_name), fetch_results=True,
    )
    if not one_untaken_copy:
        mysql_tools.close_connection(connection)
        raise ValueError("That item is not available")
    pool_id = one_untaken_copy[0]["pool_id"]

    pick_number = len(picks) + 1
    turn_number = pick_number
    insert_pick(connection, game_id, pick_number, seat["seat_number"], item_name, turn_number)
    mysql_tools.execute(
        connection, "UPDATE draft_pool SET taken_flag = 'Y' WHERE pool_id = %s",
        args=(pool_id,),
    )
    finish_draft_if_complete(connection, game_id, pick_number, total_items(game, len(seats)))
    mysql_tools.close_connection(connection)


def group_untaken_cells_by_grid(grid_cells: list[dict]) -> dict[int, list[dict]]:
    untaken_cells_by_grid = {}
    for cell in grid_cells:
        if cell["taken_flag"] != "N":
            continue
        grid_number = cell["grid_number"]
        if grid_number not in untaken_cells_by_grid:
            untaken_cells_by_grid[grid_number] = []
        untaken_cells_by_grid[grid_number].append(cell)
    return untaken_cells_by_grid


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
    raise_if_not_seats_turn(game, seats, picks, seat)

    untaken_cells_by_grid = group_untaken_cells_by_grid(get_grid(game_id))
    if not untaken_cells_by_grid:
        raise ValueError("This draft game is not currently drafting")
    current_grid_number = min(untaken_cells_by_grid)
    if grid_number != current_grid_number:
        raise ValueError("That grid is not currently being drafted")

    line_positions = GRID_LINES[(line_type, line_index)]
    cells_to_take = []
    for cell in untaken_cells_by_grid[grid_number]:
        cell_position = (cell["grid_row"], cell["grid_col"])
        if cell_position in line_positions:
            cells_to_take.append(cell)
    if not cells_to_take:
        raise ValueError("That line has no cards left to take")

    connection = mysql_tools.get_connection()
    turn_number = len(picks) + 1
    pick_number = len(picks)
    for cell in cells_to_take:
        pick_number = pick_number + 1
        mysql_tools.execute(
            connection,
            """UPDATE draft_pool SET taken_flag = 'Y'
               WHERE game_id = %s AND grid_number = %s AND grid_row = %s AND grid_col = %s""",
            args=(game_id, grid_number, cell["grid_row"], cell["grid_col"]),
        )
        insert_pick(connection, game_id, pick_number, seat["seat_number"], cell["item_name"], turn_number)
    finish_draft_if_complete(connection, game_id, pick_number, total_items(game, len(seats)))
    mysql_tools.close_connection(connection)


def set_error(game_id: int, message: str) -> None:
    mysql_tools.run_statement(
        "UPDATE draft_games SET status = %s, error_message = %s WHERE game_id = %s",
        args=(STATUS_ERROR, message, game_id),
    )


def start_generation(game_id: int, caller_player_id: int, yaml_path: str) -> None:
    game = get_game(game_id)
    if game is None:
        raise ValueError("No such draft game")
    if game["created_by_player_id"] != caller_player_id:
        raise ValueError("Only the host can upload settings for this draft game")
    if game["status"] != STATUS_LOBBY and game["status"] != STATUS_POOL_SELECTION:
        raise ValueError("Settings can only be uploaded before the draft starts")

    connection = mysql_tools.get_connection()
    mysql_tools.execute(connection, "DELETE FROM draft_candidates WHERE game_id = %s", args=(game_id,))
    mysql_tools.execute(
        connection,
        """UPDATE draft_games SET status = %s, seed_zip_path = %s, error_message = NULL,
           server_password = NULL, seed_link = NULL, slot_name = NULL WHERE game_id = %s""",
        args=(STATUS_GENERATING, yaml_path, game_id),
    )
    mysql_tools.close_connection(connection)


def set_generation_result(game_id: int, server_password: str, seed_link: str, slot_name: str,
                          candidates: list[tuple[str, str, int]]) -> None:
    connection = mysql_tools.get_connection()
    for item_name, category, quantity in candidates:
        mysql_tools.execute(
            connection,
            "INSERT INTO draft_candidates (game_id, item_name, category, quantity) VALUES (%s, %s, %s, %s)",
            args=(game_id, item_name, category, quantity),
        )
    mysql_tools.execute(
        connection,
        "UPDATE draft_games SET status = %s, server_password = %s, seed_link = %s, slot_name = %s WHERE game_id = %s",
        args=(STATUS_POOL_SELECTION, server_password, seed_link, slot_name, game_id),
    )
    mysql_tools.close_connection(connection)


def set_generation_failed(game_id: int, message: str) -> None:
    mysql_tools.run_statement(
        "UPDATE draft_games SET status = %s, error_message = %s WHERE game_id = %s",
        args=(STATUS_LOBBY, message, game_id),
    )


def set_seat_room_link(game_id: int, seat_number: int, room_link: str) -> None:
    mysql_tools.run_statement(
        "UPDATE draft_seats SET room_link = %s WHERE game_id = %s AND seat_number = %s",
        args=(room_link, game_id, seat_number),
    )


def set_seat_items_sent(game_id: int, seat_number: int) -> None:
    mysql_tools.run_statement(
        "UPDATE draft_seats SET items_sent_flag = 'Y' WHERE game_id = %s AND seat_number = %s",
        args=(game_id, seat_number),
    )

    every_seat_has_items = True
    for seat in get_seats(game_id):
        if seat["items_sent_flag"] != "Y":
            every_seat_has_items = False
    if every_seat_has_items:
        mysql_tools.run_statement(
            "UPDATE draft_games SET status = %s WHERE game_id = %s",
            args=(STATUS_COMPLETE, game_id),
        )
