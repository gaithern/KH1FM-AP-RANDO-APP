import random
from collections import Counter

DEFAULT_CATEGORIES = ["Keyblades", "Accessories"]

EXCLUDED_CATEGORIES = {
    "Augments", "Camping Items", "Consumables", "Level Ups", "Limited Level Ups", "Stat Ups", "Weapons",
}

HOST_PLAYER_NUMBER = 1


def get_category(item_data) -> str:
    first_group = item_data.groups[0]
    return first_group


def available_categories() -> list[str]:
    from worlds.kh1.Items import item_table

    categories = set()
    for item_data in item_table.values():
        category = get_category(item_data)
        if category not in EXCLUDED_CATEGORIES:
            categories.add(category)
    return sorted(categories)


def validate_categories(item_categories: list[str]) -> None:
    unknown_categories = set(item_categories) - set(available_categories())
    if unknown_categories:
        raise ValueError(f"Unknown item categories: {sorted(unknown_categories)}")


def is_draftable_location_item(location, item_table, item_categories: list[str]) -> bool:
    item = location.item
    if item is None:
        return False
    if item.player != HOST_PLAYER_NUMBER:
        return False
    if item.code is None:
        return False
    if item.name not in item_table:
        return False
    category = get_category(item_table[item.name])
    return category in item_categories


def seed_candidates(multiworld, item_categories: list[str]) -> list[tuple[str, str, int]]:
    from worlds.kh1.Items import item_table

    quantity_by_item_name = Counter()
    for location in multiworld.get_locations(HOST_PLAYER_NUMBER):
        if is_draftable_location_item(location, item_table, item_categories):
            quantity_by_item_name[location.item.name] += 1

    candidates = []
    for item_name, quantity in quantity_by_item_name.items():
        category = get_category(item_table[item_name])
        candidates.append((item_name, category, quantity))
    return sorted(candidates)


def build_pool(selected: list[tuple[str, str]], count: int) -> list[tuple[str, str]]:
    if len(selected) < count:
        raise ValueError(f"Select at least {count} items for this draft (selected {len(selected)})")
    return random.sample(selected, count)
