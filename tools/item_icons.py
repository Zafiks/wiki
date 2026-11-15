"""Shared pack lookup, idle GUI selection and content-addressed wiki icons.

Only 64px rendered WebP files and their hashes are written to the wiki.
The pack and the local Minecraft client remain read-only.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import resource
import sys
import zipfile

# A single 256px render needs no BLAS worker pool. Keep both threads and the
# process address space bounded, including when the generators run separately.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import numpy as np
from PIL import Image
import yaml

HERE = Path(__file__).resolve().parent
WIKI = HERE.parent
RESOURCES = WIKI.parent / "resourcepack"
DEFAULT_COSMETICS = Path("/home/yuki/Documents/idea/VCore/src/main/resources/cosmetics.yml")
DEFAULT_PACKS = DEFAULT_COSMETICS.with_name("packs.yml")
sys.path.insert(0, str(RESOURCES))
import modelpreview as mp  # noqa: E402


def kind(value):
    return value.removeprefix("minecraft:")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def select_idle(node, name=None):
    """Resolve the named case in GUI, unused, uncharged and undamaged state."""
    if not isinstance(node, dict):
        raise ValueError("нет описания основного вида")
    t = kind(node.get("type", ""))
    if t == "model":
        return [node]
    if t == "empty":
        return []
    if t == "composite":
        return [leaf for child in node["models"] for leaf in select_idle(child, name)]
    if t == "select":
        prop = kind(node.get("property", ""))
        value = {"display_context": "gui", "main_hand": "right", "charge_type": "none"}.get(prop)
        if kind(node.get("component", "")) == "custom_name":
            value = name
        for case in node.get("cases", []):
            when = case["when"]
            if value is not None and value in (when if isinstance(when, list) else [when]):
                return select_idle(case["model"], name)
        return select_idle(node.get("fallback"), name)
    if t == "condition":
        # No active use, selected bundle contents, cast bobber or pressed keys.
        active = kind(node.get("property", "")) == "has_component" and kind(node.get("component", "")) == "custom_name" and name is not None
        return select_idle(node.get("on_true" if active else "on_false"), name)
    if t == "range_dispatch":
        chosen = node.get("fallback")
        for entry in sorted(node.get("entries", []), key=lambda e: e["threshold"]):
            if entry["threshold"] <= 0:
                chosen = entry["model"]
        return select_idle(chosen, name)
    raise ValueError(f"неподдерживаемый вид предмета: {t}")


def name_cases(node):
    """Preserve the existing rename catalogue's order and all aliases."""
    if isinstance(node, dict):
        if kind(node.get("type", "")) == "select" and kind(node.get("component", "")) == "custom_name":
            for case in node.get("cases", []):
                names = case["when"]
                yield tuple(names) if isinstance(names, list) else (names,)
        for value in node.values():
            yield from name_cases(value)
    elif isinstance(node, list):
        for value in node:
            yield from name_cases(value)


def load_cosmetics(path=DEFAULT_COSMETICS):
    with Path(path).open(encoding="utf-8") as f:
        return yaml.safe_load(f)["cosmetics"]


class Catalogue:
    def __init__(self, pack):
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = 768 * 1024 * 1024
        if soft != resource.RLIM_INFINITY:
            limit = min(limit, soft)
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
        self.pack = zipfile.ZipFile(pack)
        self.names = set(self.pack.namelist())
        self.store = mp.Store([str(pack)])
        self.vanilla = next((source[0] for kind_, source in self.store.sources
                             if kind_ == "zip" and Path(source[0].filename) == Path(mp.CLIENT_JAR)), None)
        self.renames = {}
        self.errors = set()
        self._prepared = {}
        self._leaves = {}
        self._textures = {}
        self._atlas_cache = {}
        self.atlases = {}
        for atlas in ("items", "blocks"):
            path = f"assets/minecraft/atlases/{atlas}.json"
            self.atlases[atlas] = self.store.json(path) or {"sources": []}
        for path in self.pack.namelist():
            if path.startswith("assets/minecraft/items/") and path.endswith(".json"):
                try:
                    root = self.store.json(path)["model"]
                    names = list(dict.fromkeys(name_cases(root)))
                    if names:
                        self.renames[Path(path).stem] = (root, names)
                except Exception as e:
                    self.errors.add(f"{path}: {e}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.pack.close()
        for kind_, source in self.store.sources:
            if kind_ == "zip":
                source[0].close()
        self.release()

    def release(self):
        """Only the current icon may retain decoded textures or model caches."""
        self._prepared.clear()
        self._leaves.clear()
        self._textures.clear()
        self.store._cache.clear()
        mp._tex_cache.clear()

    def wardrobe_node(self, item):
        ns, path = mp.split_ref(item["model"])
        data = self.store.json(f"assets/{ns}/items/{path}.json")
        if data is None:
            raise FileNotFoundError(f"нет описания предмета {item['model']}")
        return data["model"]

    def chain(self, ref):
        chain, seen = [], set()
        while ref:
            ns, path = mp.split_ref(ref)
            ref = f"{ns}:{path}"
            if ref in seen:
                raise ValueError(f"цикл parent: {ref}")
            seen.add(ref)
            if path.startswith("builtin/"):
                if path != "builtin/generated":
                    raise ValueError(f"неподдерживаемый родитель {ref}")
                chain.append({"builtin": ref})
                break
            data = self.store.json(f"assets/{ns}/models/{path}.json")
            if data is None:
                raise FileNotFoundError(f"нет модели {ref}")
            chain.append(data)
            ref = data.get("parent")
        return chain

    def texture(self, ref):
        if ref in self._textures:
            return self._textures[ref]
        ns, path = mp.split_ref(ref)
        rel = f"assets/{ns}/textures/{path}.png"
        raw = self.store.read(rel)
        if raw is None:
            raise FileNotFoundError(f"нет текстуры {ref}")
        meta = self.store.read(rel + ".mcmeta")
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        animation = json.loads(meta).get("animation") if meta else None
        if animation is not None:
            # Without explicit dimensions Minecraft uses square cells, including
            # horizontal strips. Explicit dimensions may describe a frame grid.
            default = min(image.size)
            width = animation.get("width", image.width if "height" in animation else default)
            height = animation.get("height", image.height if "width" in animation else default)
            if width <= 0 or height <= 0 or width > image.width or height > image.height:
                raise ValueError(f"неверный размер кадра {ref}")
            frame = animation.get("frames", [0])[0]
            frame = frame["index"] if isinstance(frame, dict) else frame
            columns, rows = image.width // width, image.height // height
            if not isinstance(frame, int) or not 0 <= frame < columns * rows:
                raise ValueError(f"неверный первый кадр {ref}")
            x, y = (frame % columns) * width, (frame // columns) * height
            image = image.crop((x, y, x + width, y + height))
        self._textures[ref] = (raw, meta, image)
        return self._textures[ref]

    def texture_atlases(self, ref):
        if ref in self._atlas_cache:
            return self._atlas_cache[ref]
        ns, path = mp.split_ref(ref)
        ref = f"{ns}:{path}"
        # Vanilla 1.21.11's default directory sources; pack sources extend them.
        result = {"items"} if path.startswith("item/") else {"blocks"} if path.startswith("block/") else set()
        for atlas, data in self.atlases.items():
            present = atlas in result
            for source in data.get("sources", []):
                t = kind(source["type"])
                if t == "single":
                    rns, rp = mp.split_ref(source["resource"])
                    if f"{rns}:{rp}" == ref:
                        present = True
                elif t == "directory":
                    if ns == "minecraft" and path.startswith(source["source"].rstrip("/") + "/"):
                        present = True
                elif t == "filter":
                    pattern = source.get("pattern", {})
                    if re.fullmatch(pattern.get("namespace", ".*"), ns) and re.fullmatch(pattern.get("path", ".*"), path):
                        present = False
            if present:
                result.add(atlas)
            else:
                result.discard(atlas)
        self._atlas_cache[ref] = result
        return result

    def custom(self, textures):
        # A wrapper that merely points at unchanged vanilla assets has no icon.
        for ref in textures:
            ns, path = mp.split_ref(ref)
            rel = f"assets/{ns}/textures/{path}.png"
            if rel in self.names:
                if self.vanilla is None or rel not in self.vanilla.NameToInfo or self.pack.read(rel) != self.vanilla.read(rel):
                    return True
        return False

    def prepare_leaf(self, node):
        lookup = canonical(node)
        if lookup in self._leaves:
            return self._leaves[lookup]
        ref = node["model"]
        chain = self.chain(ref)
        model = mp.load_model(self.store, ref)
        if not model.generated and not model.elements:
            raise ValueError(f"пустая геометрия {ref}")
        used = []
        if model.generated:
            used = [f"#{key}" for key in sorted(model.textures, key=lambda k: int(k[5:]) if k.startswith("layer") and k[5:].isdigit() else -1) if re.fullmatch(r"layer\d+", key)]
        else:
            for element in model.elements:
                if any(not -16 <= float(v) <= 32 for key in ("from", "to") for v in element[key]):
                    raise ValueError(f"кубы вне −16..32: {ref}")
                used.extend(face["texture"] for face in element.get("faces", {}).values())
        refs = []
        for value in used:
            texture = mp.resolve_texture(model.textures, value)
            if not texture:
                raise FileNotFoundError(f"не разрешена текстура {value} в {ref}")
            refs.append(texture)
        if not refs:
            raise ValueError(f"нет видимых текстур {ref}")
        common = {"items", "blocks"}
        fingerprints = []
        for texture in dict.fromkeys(refs):
            ns, path = mp.split_ref(texture)
            rel = f"assets/{ns}/textures/{path}.png"
            raw, meta = self.store.read(rel), self.store.read(rel + ".mcmeta")
            if raw is None:
                raise FileNotFoundError(f"нет текстуры {texture}")
            fingerprints.append([texture, hashlib.sha1(raw).hexdigest(), hashlib.sha1(meta or b"").hexdigest()])
            common &= self.texture_atlases(texture)
        if not common:
            raise ValueError(f"текстуры из разных или неизвестных атласов: {ref}")
        # Namespace alone is insufficient: many paid models live in minecraft:.
        custom_geometry = False
        if model.elements:
            current = ref
            for data in chain:
                ns, path = mp.split_ref(current)
                if "elements" in data:
                    try:
                        vanilla_data = json.loads(self.vanilla.read(f"assets/{ns}/models/{path}.json")) if self.vanilla else {}
                        custom_geometry = data["elements"] != vanilla_data.get("elements")
                    except KeyError:
                        custom_geometry = True
                    break
                current = data.get("parent", "")
        own = custom_geometry or self.custom(refs)
        colors = []
        for tint in node.get("tints", []):
            value = tint.get("value", 0xFFFFFF) if kind(tint.get("type", "")) == "constant" else tint.get("default", 0xFFFFFF)
            if isinstance(value, list):
                value = sum(int(c * 255) << shift for c, shift in zip(value, (16, 8, 0)))
            colors.append(int(value) & 0xFFFFFF)
        key_data = {"chain": chain, "textures": fingerprints, "tints": colors}
        self._leaves[lookup] = {"ref": ref, "model": model, "textures": list(dict.fromkeys(refs)), "colors": colors, "own": own, "key_data": key_data}
        return self._leaves[lookup]

    def prepare(self, node, name=None):
        lookup = hashlib.sha1(canonical([node, name])).digest()
        if lookup not in self._prepared:
            try:
                leaves = [self.prepare_leaf(leaf) for leaf in select_idle(node, name)]
                if not leaves or not any(leaf["own"] for leaf in leaves):
                    self._prepared[lookup] = None
                else:
                    key = hashlib.sha1(canonical([leaf["key_data"] for leaf in leaves])).hexdigest()
                    self._prepared[lookup] = (key, leaves)
            except Exception as e:
                self._prepared[lookup] = e.with_traceback(None)
        value = self._prepared[lookup]
        if isinstance(value, Exception):
            raise value
        return value

    def report(self):
        print(f"Пропущено с ошибкой: {len(self.errors)}")
        for error in sorted(self.errors):
            print(f"  {error}")


def tinted(image, color):
    if color == 0xFFFFFF:
        return image
    pixels = np.array(image)
    rgb = np.array([(color >> shift) & 255 for shift in (16, 8, 0)], dtype=np.uint16)
    pixels[..., :3] = (pixels[..., :3].astype(np.uint16) * rgb // 255).astype(np.uint8)
    return Image.fromarray(pixels)


def render_icon(catalogue, leaves):
    flat = all(leaf["model"].generated for leaf in leaves)
    if flat:
        image = Image.new("RGBA", (64, 64))
        for leaf in leaves:
            model = leaf["model"]
            layers = sorted((int(key[5:]), value) for key, value in model.textures.items() if re.fullmatch(r"layer\d+", key))
            for index, value in layers:
                layer = catalogue.texture(mp.resolve_texture(model.textures, value))[2]
                if index < len(leaf["colors"]):
                    layer = tinted(layer, leaf["colors"][index])
                image.alpha_composite(layer.resize((64, 64), Image.Resampling.NEAREST))
        return image, True
    quads = []
    textures = {}
    def pixels(ref, color=0xFFFFFF):
        key = (ref, color)
        if key not in textures:
            image = tinted(catalogue.texture(ref)[2], color)
            textures[key] = np.asarray(image).astype(np.float32) / 255
        return textures[key]
    for leaf in leaves:
        if leaf["model"].generated:
            raise ValueError("составной предмет смешивает плоскую и объёмную геометрию")
        for ref in leaf["textures"]:
            mp._tex_cache[id(catalogue.store), ref] = pixels(ref)
        scene = mp.gui_view(catalogue.store, leaf["ref"], "gui")
        # modelpreview ignores face tintindex. Apply it without changing its code.
        faces = [face for el in leaf["model"].elements for direction, face in el.get("faces", {}).items() if direction in mp.FACE_CORNERS]
        for (points, uv, _), face in zip(scene, faces, strict=True):
            ref = mp.resolve_texture(leaf["model"].textures, face["texture"])
            index = face.get("tintindex", -1)
            color = leaf["colors"][index] if 0 <= index < len(leaf["colors"]) else 0xFFFFFF
            quads.append((points, uv, pixels(ref, color)))
    # The supplied renderer returns opaque RGBA even for a transparent background.
    # Recover coverage from its actual depth buffer, preserving black texels.
    original = mp.raster_tri
    buffers = []
    def raster_with_coverage(color, depth, *args):
        if not buffers:
            buffers.append(depth)
        return original(color, depth, *args)
    mp.raster_tri = raster_with_coverage
    try:
        image = mp.render(quads, size=256, fit=(np.array([-0.5, -0.5, -2]), np.array([0.5, 0.5, 2])), background=(0, 0, 0, 0))
    finally:
        mp.raster_tri = original
    alpha = np.uint8(buffers[0] > -1e9) * 255 if buffers else np.zeros((256, 256), dtype=np.uint8)
    image.putalpha(Image.fromarray(alpha))
    if not image.getbbox():
        raise ValueError("основной GUI-вид пуст или полностью за пределами кадра")
    return image.resize((64, 64), Image.Resampling.LANCZOS), False


class IconIndex:
    def __init__(self, catalogue, cache=HERE / "item-icons.json", docs=WIKI / "docs"):
        self.catalogue, self.cache, self.docs = catalogue, Path(cache), Path(docs)
        self.files = json.loads(self.cache.read_text()) if self.cache.exists() else {}

    def icon(self, node, label, name=None):
        try:
            prepared = self.catalogue.prepare(node, name)
            if prepared is None:
                return "—"
            key, leaves = prepared
            filename = self.files.get(key)
            if not filename or not (self.docs / filename).is_file():
                raise FileNotFoundError("нет иконки в кэше; запустите gen_item_icons.py")
            classes = ".nw-item-icon" + (" .nw-item-icon-pixel" if all(leaf["model"].generated for leaf in leaves) else "")
            alt = html.escape(label, quote=True).replace("|", "&#124;").replace("[", "&#91;").replace("]", "&#93;")
            return f'![{alt}]({filename}){{ {classes} width="32" height="32" loading="lazy" decoding="async" }}'
        except Exception as e:
            self.catalogue.errors.add(f"{label}: {e}")
            return "—"
        finally:
            self.catalogue.release()
