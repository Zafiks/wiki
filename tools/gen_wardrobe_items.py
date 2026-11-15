"""All wardrobe items, grouped by set, with the same pack icons as renames.

    .venv/bin/python -I tools/gen_wardrobe_items.py <pack.zip> [docs/wardrobe-items.md]
"""
import argparse
import html
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from item_icons import Catalogue, DEFAULT_COSMETICS, DEFAULT_PACKS, IconIndex, WIKI, load_cosmetics

TARGETS = {
    "SWORD": "меч", "AXE": "топор", "PICKAXE": "кирка", "SHOVEL": "лопата", "HOE": "мотыга",
    "TRIDENT": "трезубец", "MACE": "булава", "BOW": "лук", "CROSSBOW": "арбалет", "SHIELD": "щит",
    "FISHING_ROD": "удочка", "SPYGLASS": "подзорная труба", "LANTERN": "фонарь", "TOTEM": "тотем",
}
RARITIES = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая", "legendary": "Легендарная"}


def esc(value):
    return html.escape(str(value), quote=False).replace("|", "&#124;")


def slot_label(item):
    slot = item["slot"]
    if slot == "HAND":
        return "Для рук: " + ", ".join(TARGETS.get(target, target.lower().replace("_", " ")) for target in item.get("targets", []))
    return {"HAT": "Шапка — на шлем", "BACK": "На спину / на нагрудник", "ARMOR": "Доспехи комплекта — на всю броню"}.get(slot, slot)


def generate(catalogue, cosmetics, rarity, out_md):
    icons, groups = IconIndex(catalogue), {}
    for cid, item in cosmetics.items():
        groups.setdefault(item.get("set") or "Без набора", []).append((cid, item))
    lines = [
        "---", "title: Все вещи гардероба", "hide:", "  - toc", "---", "", "# Все вещи гардероба", "",
        f"В гардеробе **{len(cosmetics)} вещей**. Ниже — все наборы, внешний вид, подходящие предметы и редкость.", "",
        "Как надеть и получить вещи — на странице [«Гардероб»](wardrobe.md).", "",
        "Для вещей с выбором цвета показан исходный цвет. Доспехи комплекта представлены нагрудником;",
        "скин применяется ко всей надетой броне.", "",
        '<input id="wardrobe-filter" class="nw-filter" type="search" aria-label="Поиск по вещам гардероба" placeholder="Поиск: название, набор, меч, легендарная…" autocomplete="off">',
        '<p class="nw-filter-empty" hidden>Ничего не нашлось.</p>', "",
    ]
    for title, items in groups.items():
        # The existing filter hides whole groups and their h2 when empty.
        lines += [f"## {esc(title)}", "", '<div class="nw-filter-group" markdown>', "",
                  "| Вид | Название | Куда надевается | Редкость |", "|---|---|---|---|"]
        for cid, item in items:
            try:
                icon = icons.icon(catalogue.wardrobe_node(item), item["title"])
            except Exception as e:
                catalogue.errors.add(f"гардероб {cid}: {e}")
                icon = "—"
            # VCore always treats full armor skins as legendary.
            rank = "legendary" if item["slot"] == "ARMOR" else rarity.get("items", {}).get(cid, rarity.get("by-slot", {}).get(item["slot"], "common"))
            name = esc(item["title"])
            lines.append(f'| {icon} | {name} <span class="nw-item-set">{esc(title)}</span> | {esc(slot_label(item))} | {RARITIES.get(rank, esc(rank))} |')
        lines += ["", "</div>", ""]
    Path(out_md).write_text("\n".join(lines), encoding="utf-8")
    print(f"{out_md}: {len(cosmetics)} вещей, {len(groups)} наборов")
    catalogue.report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("out_md", type=Path, nargs="?", default=WIKI / "docs/wardrobe-items.md")
    parser.add_argument("--cosmetics", type=Path, default=DEFAULT_COSMETICS)
    parser.add_argument("--packs", type=Path, default=DEFAULT_PACKS)
    args = parser.parse_args()
    with args.packs.open(encoding="utf-8") as f:
        rarity = yaml.safe_load(f)["cosmetic-rarity"]
    with Catalogue(args.pack) as catalogue:
        generate(catalogue, load_cosmetics(args.cosmetics), rarity, args.out_md)


if __name__ == "__main__":
    main()
