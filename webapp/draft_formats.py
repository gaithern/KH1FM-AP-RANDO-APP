"""Pluggable draft-format strategies for the KH1 item draft feature.

Adding a new format (e.g. a booster-pack draft) means adding a new
DraftFormat subclass and registering it in DRAFT_FORMATS - draft_tools.py
and flask_app.py only ever go through this registry, keyed by
draft_games.draft_type, and never hard-code 'snake' turn-order logic.
"""


class DraftFormat:
    def turn_order(self, num_players: int, picks_per_player: int) -> list[int]:
        """Seat index (0-based) whose turn it is for each pick_number, in order."""
        raise NotImplementedError

    def is_draft_complete(self, num_players: int, picks_per_player: int, num_picks: int) -> bool:
        return num_picks >= num_players * picks_per_player

    def seat_on_the_clock(self, num_players: int, picks_per_player: int, num_picks: int) -> int | None:
        """0-based seat index whose turn it is, or None if the draft is complete."""
        if self.is_draft_complete(num_players, picks_per_player, num_picks):
            return None
        return self.turn_order(num_players, picks_per_player)[num_picks]


class SnakeDraft(DraftFormat):
    """1..N, N..1, 1..N, ... - generalizes to any player count."""

    def turn_order(self, num_players: int, picks_per_player: int) -> list[int]:
        order = []
        forward = list(range(num_players))
        backward = list(reversed(forward))
        for round_number in range(picks_per_player):
            order.extend(forward if round_number % 2 == 0 else backward)
        return order


DRAFT_FORMATS: dict[str, DraftFormat] = {
    "snake": SnakeDraft(),
}


def get_draft_format(draft_type: str) -> DraftFormat:
    try:
        return DRAFT_FORMATS[draft_type]
    except KeyError:
        raise ValueError(f"Unknown draft_type: {draft_type}")
