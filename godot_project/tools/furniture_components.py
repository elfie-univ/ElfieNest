"""Identify editable V044 furniture components and their scene placements."""

from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from review_asset_relationships import CHAIR_LABELS


class Component(NamedTuple):
    key: str
    title: str
    placement: str


PLANTS = {
    "floor_plant": "大叶橡皮树",
    "floor_fineleaf": "细叶灌木",
    "niche_front_fern": "壁龛蕨",
}
DECOR = {
    "games_niche_books": ("niche-books", "壁龛书籍"),
    "games_niche_frame_stand": ("niche-frame-stand", "相架支座"),
}
CUP_PLACEMENTS = (
    "quiet_central_reading_table_cups",
    "quiet_left_tea_table_cups",
    "quiet_front_daybed_side_table_cups",
    "quiet_rear_reading_side_table_cups",
)
BOTANICAL = {
    "coffee ": ("plants", "coffee-vase", "茶几花瓶"),
    "tall ": ("plants", "niche-vase", "壁龛枝叶花瓶"),
    "front shallow ceramic bowl": ("decor", "niche-bowl", "壁龛陶碗"),
    "rear rounded ivory vase": ("decor", "rear-vase", "后壁龛花瓶"),
    "botanical picture frame": ("decor", "niche-art", "壁龛植物画"),
    "matte botanical illustration": ("decor", "niche-art", "壁龛植物画"),
}
TITLES = {
    **CHAIR_LABELS,
    "uniform_frame": "画框",
    "high_oak_coffee_table": "高橡木茶几",
    "oak_side_table": "橡木边几",
    "music_coffee_table": "矮桌",
    "cabinet_trailing_foliage": "柜上垂叶盆栽",
    "natural_floor_plant": "高盆栽",
    "coffee_plant": "茶几盆栽",
    "pod_desk_planter": "桌面盆栽",
    "pod_amber_lamp": "台灯",
    "pod_petal_chair": "花瓣转椅",
    "pod_bed": "床与床品",
    "natural_woven_rug": "编织地垫",
}
TERRACE_FITTINGS = {
    "rear_cabinet_conformal_liner": "柜体内衬",
    "television_recessed_soft_light": "屏幕灯槽",
    "wardrobe_recessed_soft_light": "柜体灯槽",
    "curved_niche_oak_liner": "壁龛内衬",
    "television_flat_mounting_backboard": "屏幕背板",
}

CENTRAL_FURNITURE = {
    "living_tv": "电视与电视柜",
    "living_reference_sofa": "客厅沙发",
    "games_central_table": "桌游桌与棋盘",
    "games_central_puzzle": "拼图",
    "games_central_rug": "桌游区地毯",
    "games_left_chess_table": "棋桌与棋盘",
    "games_left_chess_rug": "棋桌区地毯",
    "games_right_console": "游戏机与电视柜",
    "games_right_console_rug": "游戏机区地毯",
    "games_front_castle": "积木城堡与积木",
    "games_front_play_rug": "积木区地毯",
    "games_front_toy_car": "玩具车",
    "games_front_toy_chest": "玩具收纳箱",
    "games_left_curved_bookshelf": "弧形书架",
    "games_rear_display": "陈列柜",
    "quiet_central_reading_table": "阅读桌",
    "quiet_central_reading_rug": "阅读区地毯",
    "quiet_left_conversation_rug": "交谈区地毯",
    "quiet_left_curved_sofa": "弧形沙发",
    "quiet_front_sage_daybed": "躺榻",
    "quiet_front_daybed_rug": "躺榻区地毯",
    "quiet_rear_library": "弧形书架",
    "quiet_rear_reading_armchair": "阅读椅与脚凳",
    "quiet_rear_reading_side_table": "橡木边几",
    "quiet_right_journaling_desk": "书写桌",
    "quiet_rear_lamp": "阅读台灯",
}
CENTRAL_GROUPS = {
    "games_left_rug_border": "games_left_chess_rug",
    "games_front_loose_blocks": "games_front_castle",
    "quiet_rear_footstool": "quiet_rear_reading_armchair",
    "quiet_left_sofa_pillow_": "quiet_left_curved_sofa",
    "quiet_left_sofa_seat_": "quiet_left_curved_sofa",
    "quiet_front_daybed_mattress": "quiet_front_sage_daybed",
    "quiet_front_daybed_pillow_": "quiet_front_sage_daybed",
    "quiet_front_daybed_bolster_": "quiet_front_sage_daybed",
    "quiet_front_daybed_throw": "quiet_front_sage_daybed",
}
ATTACHED_FIXTURES = {
    "TV connected support neck ": ("central-living", "living_tv"),
    "Draft L2 curved bookcase ": (
        "central-games-bookshelf",
        "games_left_curved_bookshelf",
    ),
    "Working reading bookcase ": ("central-quiet-rear", "quiet_rear_library"),
    "Draft L3 lower tier ": ("central-quiet-rear", "quiet_rear_library"),
    "Working reading lamp ": ("central-quiet-rear", "quiet_rear_lamp"),
    "Draft L3 writing desk ": ("central-quiet-desk", "quiet_right_journaling_desk"),
}
TERRACE_FURNITURE = {
    **TERRACE_FITTINGS,
    "additional_art_work_and_paint": "绘画作品与颜料",
    "additional_low_collectors_plant": "矮盆栽",
    "additional_low_reading_plant": "矮盆栽",
    "botanical_painting_easel": "植物画架",
    "coffee_table_magazine": "茶几杂志",
    "coffee_table_turntable": "唱片机",
    "complete_chess_set": "整套棋盘棋子",
    "linen_reading_lamp": "阅读灯",
    "listening_tea_cup": "茶杯",
    "painting_tools_and_palette": "画具与调色盘",
    "porcelain_coffee_cup": "咖啡杯",
    "porcelain_tea_service": "整套茶具",
    "reading_book_and_cup": "书与杯碟",
    "reference_rear_open_storage": "后墙储物柜",
    "reference_theme_niche_woodwork_and_display": "主题陈列柜",
    "rounded_oak_coffee_table": "橡木茶几",
    "single_surface_flat_display": "电视屏幕",
    "tabletop_natural_foliage": "桌面盆栽",
    "tall_floor_plant": "落地盆栽",
    "television_left_speaker": "左音箱",
    "television_right_speaker": "右音箱",
    "television_remote": "遥控器",
    "theme_lower_fitted_doors": "储物柜门",
    "three_lobed_game_table": "三瓣游戏桌",
    "two_game_controllers": "游戏手柄",
    "sofa_following_actual_wall": "贴墙沙发",
    "wall_fitted_gaming_sofa": "游戏沙发",
    "wall_fitted_music_loveseat": "双人音乐沙发",
    "left_wall_fitted_tea_sofa": "左侧茶座沙发",
    "right_wall_fitted_tea_sofa": "右侧茶座沙发",
}
TERRACE_GROUPS = {
    "linen_throw_on_fitted_sofa": "sofa_following_actual_wall",
    "gaming_sofa_linen_throw": "wall_fitted_gaming_sofa",
}
TERRACE_KINDS = {
    "chair": "扶手椅",
    "ottoman": "坐墩",
    "plant": "盆栽",
}


def attached_fixture(path):
    for segment in path.split("/"):
        for prefix, group in ATTACHED_FIXTURES.items():
            if segment.startswith(prefix):
                return group
    return None


def component_for(path, extras):
    name = path.rsplit("/", 1)[-1]
    template = extras.get("designTemplate", "").removeprefix("part:")
    if template.startswith("shared_"):
        template = template.removeprefix("shared_").rsplit("_", 1)[0]
    instance = extras.get("designTemplateInstance", path)
    room = extras.get("module") or ""
    if template in PLANTS:
        return "plants", Component(template, PLANTS[template], instance)
    if extras.get("assembly") == "broadleaf_clump":
        return "plants", Component("broadleaf", "宽叶盆栽", "broadleaf")
    if name.startswith("Botanical V1 "):
        label = name.removeprefix("Botanical V1 ")
        if label.startswith(("front book ", "rear book ")):
            return "decor", Component("niche-book-stack", "壁龛叠书", label.split()[0])
        for prefix, (library, key, title) in BOTANICAL.items():
            if label.startswith(prefix):
                return library, Component(key, title, key)
    furnishing = extras.get("central_furnishing")
    if furnishing == "living_reference_side" and name.startswith("Lamp "):
        return "decor", Component("living-lamp", "客厅台灯", "living-lamp")
    if furnishing in CUP_PLACEMENTS:
        return "decor", Component("book-and-cups", "叠书与双杯碟", furnishing)
    if furnishing in DECOR:
        key, title = DECOR[furnishing]
        return "decor", Component(key, title, key)
    if template == "games_niche_ornament":
        return "decor", Component("niche-ornament", "壁龛摆件", instance)
    if furnishing == "games_stair_niche_frame":
        return None, Component("uniform_frame", "画框", "games-stair-frame")
    if template == "pod_bed":
        return None, Component(
            template, TITLES[template], f"{room}-{extras['resident']}"
        )
    if template in TITLES:
        return None, Component(template, TITLES[template], f"{room}/{instance}")
    fixture = attached_fixture(path)
    if fixture:
        furnishing = fixture[1]
    if furnishing:
        key = next(
            (
                key
                for prefix, key in CENTRAL_GROUPS.items()
                if furnishing.startswith(prefix)
            ),
            furnishing,
        )
        if key in CENTRAL_FURNITURE:
            return None, Component(key, CENTRAL_FURNITURE[key], key)
    layer = extras.get("exportLayer", "")
    if layer == "layout:pod":
        slot = f"{room}/{extras.get('resident', '')}"
        if " | Desk | " in name:
            return None, Component("desk-cabinet", "柜体与抽屉", slot)
        if " curved desktop " in name or "wall-following honeywood apron" in name:
            return None, Component("desk-top", "弧形桌面与围板", slot)
    if layer.startswith("layout:terrace"):
        key = extras.get("sourceNodeName", name.rstrip("0123456789"))
        key = TERRACE_GROUPS.get(key, key)
        title = TERRACE_FURNITURE.get(key) or TERRACE_KINDS.get(extras.get("kind"))
        if title:
            return None, Component(key, title, f"{room}/{key}")
    return None, None


def component_paths(paths, components):
    grouped = defaultdict(list)
    for path in paths:
        part = components.get(path)
        if part is not None:
            grouped[part.key].append(path)
    return grouped


def prototype_groups(paths, components, mesh_at):
    """Keep one placement per distinct render shape within each library component."""
    placements = defaultdict(list)
    for path in paths:
        part = components[path]
        placements[part.key, part.placement].append(path)
    groups = {}
    for (key, _), members in placements.items():
        signature = tuple(sorted(mesh_at[path] for path in members))
        groups.setdefault((key, signature), members)
    return list(groups.values())


def component_rows(paths, components, mesh_at):
    rows = []
    for key, members in component_paths(paths, components).items():
        placements = defaultdict(list)
        for path in members:
            placements[components[path].placement].append(path)
        instances = len(placements)
        row = {
            "id": key,
            "title": components[members[0]].title,
            "count": instances,
            "paths": members,
        }
        if instances > 1:
            signatures = {
                tuple(sorted(mesh_at[path] for path in placement))
                for placement in placements.values()
            }
            assert len(signatures) == 1, (key, "placements have different shapes")
            row["prototypePaths"] = next(iter(placements.values()))
        rows.append(row)
    return rows


def reference_rows(direct, children, coverage, owners, mesh_at, entries, components):
    by_file = defaultdict(list)
    component_files = defaultdict(set)
    for path in direct:
        if path in mesh_at:
            file = owners[mesh_at[path]]
            by_file[file].append(path)
            if path in components:
                component_files[components[path]].add(file)
    for path in direct:
        if (
            path not in mesh_at
            and path in components
            and components[path] in component_files
        ):
            files = component_files[components[path]]
            assert len(files) == 1, (path, sorted(files))
            by_file[next(iter(files))].append(path)
    parts = []
    bindings = {}
    for file, paths in sorted(by_file.items()):
        asset = f"source:{Path(file).stem}"
        bindings[asset] = paths
        visible = {part["id"]: part for part in entries[asset].get("components", [])}
        covered = set()
        for key, selected in component_paths(paths, components).items():
            if key not in visible:
                continue
            part = visible[key]
            covered.update(selected)
            parts.append(
                {
                    "id": asset,
                    "component": key,
                    "title": part["title"],
                    "count": len({components[path].placement for path in selected}),
                    "unit": "实例",
                    "paths": selected,
                    "targetPaths": part.get("prototypePaths", part["paths"]),
                }
            )
        remainder = [path for path in paths if path not in covered]
        if remainder:
            parts.append({"id": asset, "count": 1, "unit": "实例", "paths": remainder})
    parts.extend(
        {
            "id": key,
            "count": 1,
            "unit": "实例",
            "paths": sorted(coverage[key]),
        }
        for key in children
    )
    return parts, bindings
