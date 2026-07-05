"""Draftable KH1 item pool, sourced from worlds/kh1/Items.py's item_table.

Draft games choose which categories to draft from at creation time, so
new categories in item_table are available without code changes here.
Keyblades and Accessory are the recommended default: pure equipment
upgrades, none of them gate world progression (unlike the Key/Torn Pages/
Worlds categories, which must not be draftable away from a player who
needs them), and none are filler consumables (the Item category).
"""

import random

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


def build_pool(item_categories: list[str], count: int) -> list[tuple[str, str]]:
    """Returns exactly `count` (item_name, category) pairs drawn from the
    given categories - no extras sitting around unpicked. Sampled without
    replacement as long as there are enough unique items; once those run
    out, fills the remainder with random duplicates rather than raising, so
    a small category selection can still support a big draft. Category is
    included alongside each name so the frontend can show a representative
    icon per item without needing the full item table."""
    from worlds.kh1.Items import item_table
    unknown = set(item_categories) - set(available_categories())
    if unknown:
        raise ValueError(f"Unknown item categories: {sorted(unknown)}")
    candidates = [name for name, data in item_table.items() if data.category in item_categories]
    if not candidates:
        raise ValueError("Selected item categories have no draftable items")

    if count <= len(candidates):
        names = random.sample(candidates, count)
    else:
        names = list(candidates)
        names.extend(random.choices(candidates, k=count - len(candidates)))
        random.shuffle(names)

    return [(name, item_table[name].category) for name in names]
