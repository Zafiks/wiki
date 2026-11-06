"""Каталог «переименуй предмет в наковальне» для вики — прямо из ресурс-пака сервера.

Читает assets/minecraft/items/*.json, собирает все варианты select по minecraft:custom_name
и пишет docs/renames.md: разделы по категориям, внутри — по предмету-основе.
Мечи/топоры/кирки/лопаты/мотыги/пластинки склеиваются в одну таблицу «любой меч» и т.п.

    python3 -I tools/gen_renames.py <пак.zip> docs/renames.md

Запускайте заново после каждой новой версии пака.
"""
import json, re, sys, zipfile

CYR = re.compile(r"[а-яё]", re.I)

ITEM_RU = {
    "iron_ingot": "Железный слиток", "carved_pumpkin": "Вырезанная тыква", "leather_horse_armor": "Кожаная конская броня",
    "potion": "Зелье (бутылочка)", "bow": "Лук", "painting": "Картина", "crossbow": "Арбалет", "totem_of_undying": "Тотем бессмертия",
    "writable_book": "Книга с пером", "written_book": "Подписанная книга", "cod": "Сырая треска", "honey_bottle": "Бутылочка мёда",
    "cookie": "Печенье", "shield": "Щит", "stick": "Палка", "shulker_box": "Шалкер", "bundle": "Мешок", "minecart": "Вагонетка",
    "arrow": "Стрела", "bread": "Хлеб", "shears": "Ножницы", "spyglass": "Подзорная труба", "brush": "Кисть", "apple": "Яблоко",
    "armor_stand": "Стойка для брони", "carrot": "Морковь", "flint_and_steel": "Огниво", "cooked_beef": "Стейк",
    "dried_kelp": "Сушёная ламинария", "name_tag": "Бирка", "cooked_chicken": "Жареная курица", "cooked_porkchop": "Жареная свинина",
    "filled_map": "Карта", "map": "Пустая карта", "goat_horn": "Козий рог", "pumpkin_pie": "Тыквенный пирог", "snowball": "Снежок",
    "splash_potion": "Взрывное зелье", "trident": "Трезубец", "cooked_salmon": "Жареный лосось", "firework_rocket": "Фейерверк",
    "glass_bottle": "Пустая бутылочка", "lingering_potion": "Оседающее зелье", "milk_bucket": "Ведро молока",
    "mushroom_stew": "Грибной суп", "nether_wart": "Незерский нарост", "rotten_flesh": "Гнилая плоть", "beetroot": "Свёкла",
    "bowl": "Миска", "fishing_rod": "Удочка", "mace": "Булава", "melon_slice": "Ломтик арбуза", "poisonous_potato": "Ядовитый картофель",
    "potato": "Картофель", "spectral_arrow": "Спектральная стрела", "spider_eye": "Паучий глаз", "suspicious_stew": "Загадочное рагу",
    "sweet_berries": "Сладкие ягоды",
}
MATERIAL_RU = {"wooden": "деревянный", "stone": "каменный", "iron": "железный", "golden": "золотой", "diamond": "алмазный",
               "netherite": "незеритовый", "copper": "медный"}
FAMILIES = {  # суффикс → (название группы, как называть материал)
    "_sword": "Любой меч", "_axe": "Любой топор", "_pickaxe": "Любая кирка", "_shovel": "Любая лопата", "_hoe": "Любая мотыга",
}
CATEGORIES = [
    ("Мебель и декор", ["iron_ingot", "armor_stand", "painting", "name_tag", "minecart"]),
    ("Головные уборы", ["carved_pumpkin"]),
    ("Оружие", ["Любой меч", "Любой топор", "bow", "crossbow", "trident", "mace", "shield", "arrow", "spectral_arrow",
                "splash_potion", "lingering_potion", "snowball", "firework_rocket"]),
    ("Инструменты и гаджеты", ["Любая кирка", "Любая лопата", "Любая мотыга", "shears", "brush", "flint_and_steel", "spyglass",
                               "fishing_rod", "stick", "goat_horn", "totem_of_undying"]),
    ("Музыка", ["leather_horse_armor", "Любая пластинка"]),
    ("Еда и напитки", ["potion", "honey_bottle", "glass_bottle", "cookie", "bread", "apple", "carrot", "potato", "poisonous_potato",
                       "beetroot", "melon_slice", "sweet_berries", "cooked_beef", "cooked_chicken", "cooked_porkchop", "cooked_salmon",
                       "cod", "dried_kelp", "pumpkin_pie", "milk_bucket", "mushroom_stew", "suspicious_stew", "bowl", "nether_wart",
                       "rotten_flesh", "spider_eye"]),
    ("Книги, карты и прочее", ["Любая книга", "Любая карта", "shulker_box", "bundle"]),
]


def cases_of(node, out):
    if isinstance(node, dict):
        if node.get("type") in ("minecraft:select", "select") and node.get("component") == "minecraft:custom_name":
            for c in node.get("cases", []):
                w = c["when"]
                out.append(tuple(w) if isinstance(w, list) else (w,))
        for v in node.values():
            cases_of(v, out)
    elif isinstance(node, list):
        for v in node:
            cases_of(v, out)


def split_names(names):
    ru = [n for n in names if CYR.search(n)]
    en = [n for n in names if not CYR.search(n)]
    return ru, en


def family_of(item):
    for suffix, title in FAMILIES.items():
        if item.endswith(suffix) and item.split("_")[0] in MATERIAL_RU:
            return title, MATERIAL_RU[item.split("_")[0]]
    if item.startswith("music_disc_"):
        return "Любая пластинка", item[len("music_disc_"):]
    if item in ("writable_book", "written_book"):
        return "Любая книга", ITEM_RU[item].lower()
    if item in ("map", "filled_map"):
        return "Любая карта", ITEM_RU[item].lower()
    return None, None


def esc(s):
    return s.replace("|", "\\|").replace("<", "&lt;")


def main():
    pack, out_md = sys.argv[1:3]
    z = zipfile.ZipFile(pack)
    per_item = {}
    for n in z.namelist():
        if n.startswith("assets/minecraft/items/") and n.endswith(".json"):
            found = []
            cases_of(json.loads(z.read(n).decode("utf-8-sig")), found)
            uniq = list(dict.fromkeys(found))
            if uniq:
                per_item[n.rsplit("/", 1)[1][:-5]] = uniq

    # склеить семейства: имя → у каких материалов оно есть
    groups = {}  # ключ группы → {names: [...], members: {names: [материалы]}, all: [материалы]}
    for item, names in per_item.items():
        fam, member = family_of(item)
        key = fam or item
        g = groups.setdefault(key, {"order": [], "where": {}, "all": []})
        g["all"].append(member)
        for nm in names:
            if nm not in g["where"]:
                g["where"][nm] = []
                g["order"].append(nm)
            g["where"][nm].append(member)

    placed = {k for _, keys in CATEGORIES for k in keys}
    extra = sorted(k for k in groups if k not in placed)
    cats = CATEGORIES + ([("Остальное", extra)] if extra else [])

    total = sum(len(g["order"]) for g in groups.values())
    lines = [
        "---", "title: Предметы по названию", "hide:", "  - toc", "---", "",
        "# Предметы по названию (наковальня)", "",
        "В нашем ресурс-паке у обычных предметов есть **другой вид**: мебель, шляпы, оружие, еда, инструменты.",
        "Чтобы его получить, **переименуйте предмет-основу в наковальне** одним из названий ниже —",
        "по-русски или по-английски, буква в букву (заглавные буквы важны).", "",
        "!!! tip \"Как это сделать\"",
        "    1. Возьмите предмет-основу из таблицы (например, **железный слиток** для мебели).",
        "    2. Положите его в наковальню и впишите название точно как в таблице.",
        "    3. Заберите предмет — он сразу поменяет вид. Работает только с включённым серверным ресурс-паком.", "",
        "    С модом [RPRenames](mods.md#rprenames) список названий появляется прямо в наковальне — ничего не нужно вводить руками.", "",
        "!!! note \"Это только внешний вид\"",
        "    Свойства предмета не меняются: «пулемёт» из лука стреляет как лук, «бургер» из стейка насыщает как стейк.", "",
        f"Всего вариантов: **{total}**. Список собран из пака автоматически.", "",
        '<input id="rename-filter" class="nw-filter" type="search" placeholder="Поиск по названию: кот, sword, гитара…" autocomplete="off">',
        '<p id="rename-filter-empty" class="nw-filter-empty" hidden>Ничего не нашлось.</p>', "",
    ]
    for cat, keys in cats:
        keys = [k for k in keys if k in groups]
        if not keys:
            continue
        lines += [f"## {cat}", ""]
        for key in keys:
            g = groups[key]
            title = key if key.startswith("Люб") else ITEM_RU.get(key, key)
            lines += [f'<div class="nw-rename-group" markdown>', "", f"### {title}", ""]
            if key == "Любая пластинка":
                lines += ["Работает на любой музыкальной пластинке.", ""]
            lines += ["| Русское название | English |", "|---|---|"]
            for nm in g["order"]:
                ru, en = split_names(nm)
                where = g["where"][nm]
                note = ""
                if key.startswith("Люб") and len(where) < len(g["all"]) and key != "Любая пластинка":
                    note = f" <small>(только {', '.join(where)})</small>"
                lines.append(f"| {esc(' / '.join(ru)) or '—'}{note} | {esc(' / '.join(en)) or '—'} |")
            lines += ["", "</div>", ""]
    open(out_md, "w", encoding="utf-8").write("\n".join(lines))
    print(f"{out_md}: {total} вариантов, {len(groups)} групп")


if __name__ == "__main__":
    main()
