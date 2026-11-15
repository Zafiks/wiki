"""Small offline fixtures: .venv/bin/python -I tools/test_item_icons.py."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from item_icons import Catalogue, IconIndex, render_icon, select_idle
from gen_item_icons import generate


def png(color, size=(32, 32)):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, "PNG")
    return output.getvalue()


class IconTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="nightworld-icons-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.files = {
            "assets/test/models/base.json": {"parent": "minecraft:builtin/generated"},
            "assets/test/models/flat.json": {"parent": "test:base", "textures": {"layer0": "test:item/flat"}},
            "assets/test/textures/item/flat.png": png((255, 255, 255, 255)),
        }
        self.node = {"type": "minecraft:model", "model": "test:flat"}

    def catalogue(self):
        pack = self.root / "pack.zip"
        with zipfile.ZipFile(pack, "w") as archive:
            for path, value in self.files.items():
                archive.writestr(path, value if isinstance(value, bytes) else json.dumps(value))
        return Catalogue(pack)

    def key(self, node=None):
        with self.catalogue() as catalogue:
            return catalogue.prepare(node or self.node)[0]

    def cube(self, texture="test:item/flat"):
        self.files["assets/test/models/cube.json"] = {
            "textures": {"all": texture},
            "display": {"gui": {"rotation": [30, 225, 0], "scale": [0.6, 0.6, 0.6]}},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16],
                          "faces": {side: {"texture": "#all"} for side in
                                    ("north", "south", "east", "west", "up", "down")}}],
        }
        return {"type": "minecraft:model", "model": "test:cube"}

    def test_named_gui_case_uses_idle_pose(self):
        node = {"type": "minecraft:select", "property": "minecraft:component",
                "component": "minecraft:custom_name", "fallback": {"type": "minecraft:empty"},
                "cases": [{"when": ["Меч", "Sword"], "model": {
                    "type": "minecraft:select", "property": "minecraft:display_context",
                    "cases": [{"when": "gui", "model": {
                        "type": "minecraft:condition", "property": "minecraft:using_item",
                        "on_true": {"type": "minecraft:model", "model": "test:pose"},
                        "on_false": {"type": "minecraft:range_dispatch", "property": "minecraft:damage",
                                     "fallback": self.node,
                                     "entries": [{"threshold": 0.5, "model": {"type": "minecraft:empty"}}]},
                    }}], "fallback": {"type": "minecraft:empty"},
                }}]}
        self.assertEqual(select_idle(node, "Меч"), [self.node])
        self.assertEqual(select_idle(node, "Sword"), [self.node])
        self.assertEqual(select_idle(node, "Other"), [])

    def test_content_key_tracks_parent_texture_and_tint(self):
        original = self.key()
        self.assertEqual(original, self.key())
        self.files["assets/test/models/base.json"]["display"] = {"gui": {"scale": [0.5, 0.5, 0.5]}}
        self.assertNotEqual(original, self.key())
        parent_key = self.key()
        self.files["assets/test/textures/item/flat.png"] = png((0, 255, 0, 255))
        self.assertNotEqual(parent_key, self.key())
        self.assertNotEqual(self.key(), self.key(self.node | {"tints": [{"type": "minecraft:dye", "default": 0x804020}]}))

    def test_flat_animation_layers_and_default_dye(self):
        strip = Image.new("RGBA", (32, 64), (255, 0, 0, 255))
        strip.paste((255, 255, 255, 255), (0, 32, 32, 64))
        output = io.BytesIO()
        strip.save(output, "PNG")
        self.files["assets/test/textures/item/flat.png"] = output.getvalue()
        self.files["assets/test/textures/item/flat.png.mcmeta"] = {"animation": {"frames": [{"index": 1}]}}
        overlay = Image.new("RGBA", (32, 32))
        overlay.putpixel((0, 0), (0, 0, 255, 255))
        output = io.BytesIO()
        overlay.save(output, "PNG")
        self.files["assets/test/textures/item/overlay.png"] = output.getvalue()
        self.files["assets/test/models/flat.json"]["textures"]["layer1"] = "test:item/overlay"
        node = self.node | {"tints": [{"type": "minecraft:dye", "default": 0x804020}]}
        with self.catalogue() as catalogue:
            _, leaves = catalogue.prepare(node)
            image, flat = render_icon(catalogue, leaves)
            self.assertTrue(flat)
            self.assertEqual(image.size, (64, 64))
            self.assertEqual(image.getpixel((10, 10)), (128, 64, 32, 255))
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 255, 255))
            self.assertEqual(image.getpixel((1, 1)), (0, 0, 255, 255))

    def test_cube_is_transparent_and_textures_are_shared(self):
        node = self.cube()
        with self.catalogue() as catalogue:
            _, leaves = catalogue.prepare(node)
            image, flat = render_icon(catalogue, leaves)
            self.assertFalse(flat)
            self.assertEqual(image.size, (64, 64))
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertGreater(image.getpixel((32, 32))[3], 0)
            catalogue.release()
            self.assertFalse(catalogue._textures)
            self.assertFalse(catalogue.store._cache)

    def test_unchanged_vanilla_models_have_no_icon(self):
        with self.catalogue() as catalogue:
            for model in ("minecraft:item/diamond_sword", "minecraft:block/stone"):
                self.assertIsNone(catalogue.prepare({"type": "minecraft:model", "model": model}))

    def test_bad_assets_are_reported_and_do_not_stop_other_items(self):
        node = self.cube("test:block/other")
        self.files["assets/test/textures/block/other.png"] = png((255, 255, 255, 255))
        self.files["assets/test/models/cube.json"]["elements"][0]["faces"]["north"]["texture"] = "test:item/flat"
        with self.catalogue() as catalogue:
            icons = IconIndex(catalogue, cache=self.root / "cache.json", docs=self.root)
            self.assertEqual(icons.icon(node, "Mixed atlases"), "—")
            self.assertTrue(any("атласов" in error for error in catalogue.errors))
            missing = self.node | {"model": "test:absent"}
            self.assertEqual(icons.icon(missing, "Missing"), "—")
            self.assertIsNotNone(catalogue.prepare(self.node))
        self.files["assets/test/models/cube.json"]["elements"][0]["from"][0] = -17
        with self.catalogue() as catalogue:
            with self.assertRaisesRegex(ValueError, "вне"):
                catalogue.prepare(node)

    def test_cache_reuses_deduplicates_and_prunes_changed_icons(self):
        self.files["assets/minecraft/items/diamond_sword.json"] = {"model": {
            "type": "minecraft:select", "property": "minecraft:component", "component": "minecraft:custom_name",
            "cases": [{"when": name, "model": self.node} for name in ("Alpha", "Beta")],
            "fallback": {"type": "minecraft:empty"},
        }}
        cache, docs = self.root / "cache.json", self.root / "docs"
        def run():
            with self.catalogue() as catalogue, redirect_stdout(io.StringIO()):
                return generate(catalogue, {}, IconIndex(catalogue, cache=cache, docs=docs))
        first = run()
        self.assertEqual(len(first), 1)
        filename = docs / next(iter(first.values()))
        modified = filename.stat().st_mtime_ns
        with patch("gen_item_icons.render_icon", side_effect=AssertionError("cached icon rendered again")):
            self.assertEqual(first, run())
        self.assertEqual(modified, filename.stat().st_mtime_ns)
        unrelated = filename.with_name("manual.webp")
        unrelated.write_bytes(b"keep")
        self.files["assets/test/textures/item/flat.png"] = png((0, 255, 0, 255))
        changed = run()
        self.assertEqual(len(changed), 1)
        self.assertNotEqual(first, changed)
        self.assertFalse(filename.exists())
        self.assertEqual(unrelated.read_bytes(), b"keep")
        self.assertEqual(json.loads(cache.read_text()), changed)


if __name__ == "__main__":
    unittest.main()
