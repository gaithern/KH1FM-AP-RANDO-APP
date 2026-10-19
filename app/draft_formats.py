CELLS_PER_GRID = 9


def get_snake_seat(number_of_players: int, turn_index: int) -> int:
    round_number = turn_index // number_of_players
    position_in_round = turn_index % number_of_players
    round_goes_forward = round_number % 2 == 0
    if round_goes_forward:
        return position_in_round
    else:
        return number_of_players - 1 - position_in_round


class DraftFormat:
    def seat_on_the_clock(self, number_of_players: int, picks: list[dict], total_items: int) -> int | None:
        raise NotImplementedError


class SnakeDraft(DraftFormat):
    def seat_on_the_clock(self, number_of_players: int, picks: list[dict], total_items: int) -> int | None:
        every_item_is_picked = len(picks) >= total_items
        if every_item_is_picked:
            return None
        return get_snake_seat(number_of_players, len(picks))


class GridDraft(DraftFormat):
    def seat_on_the_clock(self, number_of_players: int, picks: list[dict], total_items: int) -> int | None:
        every_item_is_picked = len(picks) >= total_items
        if every_item_is_picked:
            return None

        current_grid_number = len(picks) // CELLS_PER_GRID
        first_pick_in_current_grid = current_grid_number * CELLS_PER_GRID
        picks_in_current_grid = picks[first_pick_in_current_grid:]

        turn_numbers_in_current_grid = set()
        for pick in picks_in_current_grid:
            turn_numbers_in_current_grid.add(pick["turn_number"])
        turns_taken_in_current_grid = len(turn_numbers_in_current_grid)

        starting_seat = current_grid_number % number_of_players
        snake_seat = get_snake_seat(number_of_players, turns_taken_in_current_grid)
        return (starting_seat + snake_seat) % number_of_players


DRAFT_FORMATS: dict[str, DraftFormat] = {
    "snake": SnakeDraft(),
    "grid": GridDraft(),
}


def get_draft_format(draft_type: str) -> DraftFormat:
    if draft_type not in DRAFT_FORMATS:
        raise ValueError(f"Unknown draft_type: {draft_type}")
    return DRAFT_FORMATS[draft_type]
