"""Pluggable draft-format strategies for the KH1 item draft feature.

Adding a new format means adding a new DraftFormat subclass and registering
it in DRAFT_FORMATS - draft_tools.py and flask_app.py only ever go through
this registry, keyed by draft_games.draft_type, and never hard-code
turn-order logic.
"""


def _snake_seat(num_players: int, turn_index: int) -> int:
    """0-based seat whose turn it is at 0-based turn_index, under a snake
    order that starts at seat 0: 0..N-1, N-1..0, 0..N-1, ..."""
    round_number, position = divmod(turn_index, num_players)
    return position if round_number % 2 == 0 else num_players - 1 - position


class DraftFormat:
    def seat_on_the_clock(self, num_players: int, picks: list[dict], total_items: int) -> int | None:
        """0-based seat index whose turn it is, or None if every item in the
        pool has already been claimed (draft complete)."""
        raise NotImplementedError


class SnakeDraft(DraftFormat):
    """1..N, N..1, 1..N, ... - generalizes to any player count. One pick is
    one turn, so the item count doubles as the turn count."""

    def seat_on_the_clock(self, num_players: int, picks: list[dict], total_items: int) -> int | None:
        if len(picks) >= total_items:
            return None
        return _snake_seat(num_players, len(picks))


class GridDraft(DraftFormat):
    """Grid draft (https://luckypaper.co/resources/formats/grid-draft/),
    fixed to 2 players: items are dealt into one or more 3x3 grids, drafted
    one grid at a time. Each turn a player claims every still-available item
    along one row, column, or diagonal of the current grid - so a turn can
    net 1-3 items, not always exactly 1, and a grid can take anywhere from 3
    to 9 turns to clear depending on which lines get picked.

    Turn order snakes within each grid same as SnakeDraft, but resets at
    every grid boundary: the starting seat rotates by grid number, so who
    picks first alternates every grid regardless of how many turns the
    previous grid actually took (not just whichever seat's turn it happened
    to land on next under a continuous, un-reset counter).
    """

    CELLS_PER_GRID = 9  # 3x3

    def seat_on_the_clock(self, num_players: int, picks: list[dict], total_items: int) -> int | None:
        if len(picks) >= total_items:
            return None
        current_grid_number = len(picks) // self.CELLS_PER_GRID
        picks_in_current_grid = picks[current_grid_number * self.CELLS_PER_GRID:]
        turns_taken_in_grid = len({pick["turn_number"] for pick in picks_in_current_grid})
        starting_seat = current_grid_number % num_players
        return (starting_seat + _snake_seat(num_players, turns_taken_in_grid)) % num_players


DRAFT_FORMATS: dict[str, DraftFormat] = {
    "snake": SnakeDraft(),
    "grid": GridDraft(),
}


def get_draft_format(draft_type: str) -> DraftFormat:
    try:
        return DRAFT_FORMATS[draft_type]
    except KeyError:
        raise ValueError(f"Unknown draft_type: {draft_type}")
