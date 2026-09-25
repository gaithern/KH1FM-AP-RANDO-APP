"""Draftable KH1 item pool, sourced from the host's generated seed.

The host uploads their YAML before the draft starts; the seed is generated
up front and every item it contains (in the game's chosen categories)
becomes a draft candidate. The host then chooses which candidates go into
the draft. Drafting an item doesn't remove it from the seed - the drafter
just gets an extra copy sent at the start, so they have it early and will
usually still find the seed's own copy later.

Categories still come from worlds/kh1/Items.py's item_table, so new
categories are available without code changes here.
"""

import random
from collections import Counter

DEFAULT_CATEGORIES = ["Keyblades", "Accessory"]

# Excluded entirely from the draft UI (not just unchecked by default) -
# Augment and Weapons have no single icon that represents them well, and
# the rest were dropped as too fiddly/uninteresting for a quick draft.
EXCLUDED_CATEGORIES = {
    "Augment", "Camping", "Item", "Level Up", "Limited Level Up", "Stat Ups", "Weapons",
}


def available_categories() -> list[str]:
    from worlds.kh1.Items import item_table
    categories = {data.category for data in item_table.values()}
    return sorted(categories - EXCLUDED_CATEGORIES)


def validate_categories(item_categories: list[str]) -> None:
    unknown = set(item_categories) - set(available_categories())
    if unknown:
        raise ValueError(f"Unknown item categories: {sorted(unknown)}")


def seed_candidates(multiworld, item_categories: list[str]) -> list[tuple[str, str, int]]:
    """(item_name, category, quantity) for every item placed in player 1's
    seed whose category is one of item_categories. Reads placed location
    items rather than multiworld.itempool so items the world locks directly
    onto locations (never passing through itempool) are included too.
    Starting inventory isn't a location item, so it's naturally left out -
    the player already has it."""
    from worlds.kh1.Items import item_table
    counts = Counter(
        location.item.name
        for location in multiworld.get_locations(1)
        if location.item is not None and location.item.player == 1 and location.item.code is not None
        and location.item.name in item_table and item_table[location.item.name].category in item_categories
    )
    return sorted((name, item_table[name].category, quantity) for name, quantity in counts.items())


def build_pool(selected: list[tuple[str, str]], count: int) -> list[tuple[str, str]]:
    """Returns exactly `count` (item_name, category) pairs sampled without
    replacement from the host's selection. The host must select at least
    `count` items - selecting more lets chance decide which of them make it
    into the draft."""
    if len(selected) < count:
        raise ValueError(f"Select at least {count} items for this draft (selected {len(selected)})")
    return random.sample(selected, count)
