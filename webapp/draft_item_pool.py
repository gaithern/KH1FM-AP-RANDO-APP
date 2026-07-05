"""Draftable KH1 item pool, sourced from worlds/kh1/Items.py's item_table.

Draft games choose which categories to draft from at creation time, so
new categories in item_table are available without code changes here.
Keyblades and Accessory are the recommended default: pure equipment
upgrades, none of them gate world progression (unlike the Key/Torn Pages/
Worlds categories, which must not be draftable away from a player who
needs them), and none are filler consumables (the Item category).
"""

from worlds.kh1.Items import item_table

DEFAULT_CATEGORIES = ["Keyblades", "Accessory"]


def available_categories() -> list[str]:
    return sorted({data.category for data in item_table.values()})


def build_pool(item_categories: list[str]) -> list[str]:
    unknown = set(item_categories) - set(available_categories())
    if unknown:
        raise ValueError(f"Unknown item categories: {sorted(unknown)}")
    return sorted(name for name, data in item_table.items() if data.category in item_categories)
