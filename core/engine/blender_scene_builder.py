"""
Procedural Blender scene builder used by Ay-Eye.

This module turns a short visual/task description into a robust bpy script.
The goal is not to replace a human artist, but to give the agent a dependable
first-pass scene construction tool for reference-image requests.
"""

from __future__ import annotations

import re


def build_scene_script(description: str = "", reference_summary: str = "") -> str:
    """Return a self-contained Blender Python script for a described scene."""
    prompt = f"{description}\n{reference_summary}".lower()
    if "container" in prompt and ("cafe" in prompt or "coffee" in prompt or "shop" in prompt):
        return _container_cafe_script(description, reference_summary)
    if _looks_like_mlo_request(prompt):
        return _mlo_scene_script(description, reference_summary)
    return _generic_reference_scene_script(description, reference_summary)


def build_enhance_script(description: str = "", reference_summary: str = "") -> str:
    """Return a non-destructive Blender Python detail/verification pass."""
    title = _safe_text(description or reference_summary, "Professional scene enhancement")
    reference = _safe_text(reference_summary or description, "Enhancement pass")
    header = (
        "import bpy\n"
        "import math\n\n"
        f"TASK_TITLE = {title!r}\n"
        f"REFERENCE_SUMMARY = {reference!r}\n"
    )
    return header + r"""

SCENE_TAG = 'ayeye_enhancement_pass'

def mark(ob, role='detail'):
    ob['ayeye_generated_scene'] = SCENE_TAG
    ob['ayeye_mlo_role'] = role
    return ob

def mat(name, color, roughness=0.58, metallic=0.0, alpha=1.0):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        if 'Base Color' in bsdf.inputs:
            bsdf.inputs['Base Color'].default_value = color
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = roughness
        if 'Metallic' in bsdf.inputs:
            bsdf.inputs['Metallic'].default_value = metallic
        if 'Alpha' in bsdf.inputs:
            bsdf.inputs['Alpha'].default_value = alpha
    if alpha < 1.0:
        m.blend_method = 'BLEND'
        try:
            m.use_screen_refraction = True
        except Exception:
            pass
    return m

trim_mat = mat('enhancement black metal trim', (0.018, 0.017, 0.015, 1), 0.62, 0.05)
wood_mat = mat('enhancement warm wood details', (0.56, 0.32, 0.14, 1), 0.48)
neutral_mat = mat('enhancement neutral material fill', (0.44, 0.43, 0.40, 1), 0.72)
glass_mat = mat('enhancement portal glass', (0.14, 0.45, 0.95, 0.28), 0.16, 0.0, 0.28)
guide_mat = mat('enhancement blue MLO guide', (0.08, 0.32, 1.0, 0.22), 0.34, 0.0, 0.22)
warning_mat = mat('enhancement red collision marker', (0.80, 0.04, 0.035, 0.35), 0.55, 0.0, 0.35)
accent_mat = mat('enhancement warm accent', (1.0, 0.56, 0.16, 1), 0.45)
white_mat = mat('enhancement white labels', (0.94, 0.91, 0.82, 1), 0.5)
green_mat = mat('enhancement plant green', (0.10, 0.34, 0.14, 1), 0.72)

def cube(name, loc, scale, material, role='detail'):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        ob.data.materials.append(material)
    return mark(ob, role)

def cyl(name, loc, radius, depth, material, vertices=24, role='detail'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    ob = bpy.context.object
    ob.name = name
    if material:
        ob.data.materials.append(material)
    try:
        for poly in ob.data.polygons:
            poly.use_smooth = True
    except Exception:
        pass
    return mark(ob, role)

def text_obj(name, body, loc, size, material, rotation=(math.radians(75), 0, 0), align='LEFT', role='label'):
    bpy.ops.object.text_add(location=loc, rotation=rotation)
    ob = bpy.context.object
    ob.name = name
    ob.data.body = body
    ob.data.align_x = align
    ob.data.align_y = 'CENTER'
    ob.data.size = size
    ob.data.extrude = 0.012
    if material:
        ob.data.materials.append(material)
    return mark(ob, role)

def add_bevel(ob, amount=0.025, segments=1):
    if getattr(ob, 'type', '') != 'MESH':
        return
    if not any(mod.type == 'BEVEL' for mod in ob.modifiers):
        bevel = ob.modifiers.new('enhancement bevel', 'BEVEL')
        bevel.width = amount
        bevel.segments = segments
    if not any(mod.type == 'WEIGHTED_NORMAL' for mod in ob.modifiers):
        ob.modifiers.new('enhancement weighted normals', 'WEIGHTED_NORMAL')

def object_bounds(ob):
    try:
        corners = [ob.matrix_world @ mathutils.Vector(corner) for corner in ob.bound_box]
        min_x = min(c.x for c in corners)
        max_x = max(c.x for c in corners)
        min_y = min(c.y for c in corners)
        max_y = max(c.y for c in corners)
        min_z = min(c.z for c in corners)
        max_z = max(c.z for c in corners)
        center = ((min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2)
        dims = (max(max_x - min_x, 0.08), max(max_y - min_y, 0.08), max(max_z - min_z, 0.08))
        return center, dims
    except Exception:
        loc = getattr(ob, 'location', (0, 0, 0))
        dims = getattr(ob, 'dimensions', (1, 1, 1))
        return (float(loc[0]), float(loc[1]), float(loc[2])), (max(float(dims[0]), 0.08), max(float(dims[1]), 0.08), max(float(dims[2]), 0.08))

def scene_bounds(objects):
    meshes = [ob for ob in objects if getattr(ob, 'type', '') == 'MESH']
    if not meshes:
        return (0, 0, 1.2), (6.0, 4.0, 2.4)
    mins = [999999, 999999, 999999]
    maxs = [-999999, -999999, -999999]
    for ob in meshes:
        center, dims = object_bounds(ob)
        for axis in range(3):
            mins[axis] = min(mins[axis], center[axis] - dims[axis] / 2)
            maxs[axis] = max(maxs[axis], center[axis] + dims[axis] / 2)
    center = tuple((mins[i] + maxs[i]) / 2 for i in range(3))
    dims = tuple(max(maxs[i] - mins[i], 1.0) for i in range(3))
    return center, dims

def name_has(ob, terms):
    name = ob.name.lower()
    return any(term in name for term in terms)

try:
    import mathutils
except Exception:
    mathutils = None

objects = list(bpy.context.scene.objects)
mesh_objects = [ob for ob in objects if getattr(ob, 'type', '') == 'MESH']
existing_generated = [ob for ob in objects if str(ob.get('ayeye_generated_scene') or '').startswith('ayeye_')]

for ob in mesh_objects:
    if existing_generated and ob not in existing_generated:
        continue
    add_bevel(ob, 0.018, 1)
    try:
        if hasattr(ob.data, 'materials') and len(ob.data.materials) == 0:
            ob.data.materials.append(neutral_mat)
    except Exception:
        pass

rooms = [
    ob for ob in objects
    if str(ob.get('ayeye_mlo_role') or '') == 'room'
    or name_has(ob, ('room volume', 'mlo room', 'room guide'))
]
portals = [
    ob for ob in objects
    if str(ob.get('ayeye_mlo_role') or '') == 'portal'
    or name_has(ob, ('portal guide', 'mlo portal'))
]
collisions = [
    ob for ob in objects
    if str(ob.get('ayeye_mlo_role') or '') == 'collision'
    or name_has(ob, ('collision proxy', 'mlo collision'))
]

task_text = (TASK_TITLE + ' ' + REFERENCE_SUMMARY).lower()
looks_like_mlo = bool(rooms or portals or collisions or any(term in task_text for term in (
    'mlo', 'fivem', 'gta', 'sollumz', 'portal', 'collision', 'interior', 'room'
)))

center, dims = scene_bounds(objects)
sx, sy, sz = dims
base_z = max(center[2] - sz / 2, 0.0)
added = 0

if looks_like_mlo and not rooms:
    room = cube(
        'enhanced MLO fallback room volume guide',
        (center[0], center[1], base_z + max(sz * 0.45, 1.2)),
        (max(sx * 0.82, 3.0), max(sy * 0.72, 2.0), max(sz * 0.72, 2.2)),
        guide_mat,
        'room',
    )
    room.display_type = 'WIRE'
    room.hide_render = True
    rooms.append(room)
    added += 1

if looks_like_mlo and not portals:
    portal = cube(
        'enhanced MLO front portal guide',
        (center[0], center[1] - max(sy * 0.46, 1.4), base_z + 1.25),
        (max(sx * 0.34, 1.1), 0.055, 2.05),
        glass_mat,
        'portal',
    )
    portal.display_type = 'WIRE'
    portal.hide_render = True
    portals.append(portal)
    added += 1

if looks_like_mlo and not collisions:
    collision = cube(
        'enhanced MLO collision proxy guide',
        (center[0], center[1], base_z + max(sz * 0.5, 1.2)),
        (max(sx + 0.35, 3.5), max(sy + 0.35, 2.4), max(sz + 0.25, 2.3)),
        warning_mat,
        'collision',
    )
    collision.display_type = 'WIRE'
    collision.hide_render = True
    collisions.append(collision)
    added += 1

room_sources = rooms[:8] if rooms else []
for idx, room in enumerate(room_sources):
    (rx, ry, rz), (rw, rd, rh) = object_bounds(room)
    floor_z = max(rz - rh / 2 + 0.05, base_z + 0.08)
    top_z = rz + rh / 2
    trim_specs = [
        ('front', (rx, ry - rd / 2, floor_z + 0.08), (rw, 0.06, 0.10)),
        ('back', (rx, ry + rd / 2, floor_z + 0.08), (rw, 0.06, 0.10)),
        ('left', (rx - rw / 2, ry, floor_z + 0.08), (0.06, rd, 0.10)),
        ('right', (rx + rw / 2, ry, floor_z + 0.08), (0.06, rd, 0.10)),
    ]
    for side, loc, scale in trim_specs:
        add_bevel(cube('room baseboard trim - ' + room.name + ' - ' + side, loc, scale, trim_mat, 'finish'), 0.01, 1)
        added += 1
    fixture = cube('room ceiling light fixture - ' + room.name, (rx, ry, top_z - 0.16), (min(rw * 0.34, 1.2), 0.12, 0.055), accent_mat, 'light_fixture')
    add_bevel(fixture, 0.012, 1)
    added += 1
    bpy.ops.object.light_add(type='POINT', location=(rx, ry, top_z - 0.35))
    light = bpy.context.object
    light.name = 'enhanced warm room light - ' + room.name[:28]
    light.data.energy = 105
    light.data.color = (1.0, 0.72, 0.45)
    light.data.shadow_soft_size = 1.6
    mark(light, 'light')
    added += 1
    table = cube('room detail worktable/counter - ' + room.name, (rx - rw * 0.18, ry, floor_z + 0.38), (min(rw * 0.36, 1.35), min(rd * 0.24, 0.78), 0.42), wood_mat, 'prop')
    add_bevel(table, 0.025, 1)
    shelf = cube('room wall shelf detail - ' + room.name, (rx + rw * 0.22, ry + rd * 0.34, floor_z + 1.35), (min(rw * 0.30, 1.05), 0.08, 0.18), trim_mat, 'prop')
    add_bevel(shelf, 0.014, 1)
    for n in range(3):
        prop = cube('small staged room prop - ' + room.name, (rx + rw * (0.08 + n * 0.08), ry + rd * 0.34, floor_z + 1.52), (0.12, 0.07, 0.18 + n * 0.04), accent_mat if n % 2 else white_mat, 'prop')
        add_bevel(prop, 0.012, 1)
        added += 1
    text_obj('room verification label - ' + room.name, 'ROOM OK: ' + room.name[:30], (rx - rw / 2 + 0.12, ry, floor_z + 0.35), 0.12, white_mat, role='label')
    added += 4

for idx, portal in enumerate(portals[:10]):
    (px, py, pz), (pw, pd, ph) = object_bounds(portal)
    top = cube('portal lintel frame - ' + portal.name, (px, py, pz + ph / 2), (pw + 0.18, max(pd, 0.07), 0.08), trim_mat, 'portal_frame')
    bottom = cube('portal threshold frame - ' + portal.name, (px, py, pz - ph / 2), (pw + 0.18, max(pd, 0.07), 0.08), trim_mat, 'portal_frame')
    left = cube('portal left jamb - ' + portal.name, (px - pw / 2, py, pz), (0.08, max(pd, 0.07), ph + 0.08), trim_mat, 'portal_frame')
    right = cube('portal right jamb - ' + portal.name, (px + pw / 2, py, pz), (0.08, max(pd, 0.07), ph + 0.08), trim_mat, 'portal_frame')
    for frame in (top, bottom, left, right):
        add_bevel(frame, 0.01, 1)
    text_obj('portal verification label - ' + portal.name, 'PORTAL', (px - pw / 2, py - 0.08, pz + ph / 2 + 0.18), 0.11, glass_mat, role='label')
    added += 5

for idx, collision in enumerate(collisions[:4]):
    (cx, cy, cz), (cw, cd, ch) = object_bounds(collision)
    marker = cube('collision visible corner marker - ' + collision.name, (cx - cw / 2, cy - cd / 2, cz + ch / 2), (0.20, 0.20, 0.20), warning_mat, 'collision')
    marker.display_type = 'WIRE'
    text_obj('collision verification label - ' + collision.name, 'COLLISION PROXY', (cx - cw / 2, cy - cd / 2, cz + ch / 2 + 0.25), 0.12, warning_mat, role='label')
    added += 2

if not room_sources:
    for x in (center[0] - sx * 0.28, center[0] + sx * 0.28):
        planter = cyl('generic scene planter detail', (x, center[1] - sy * 0.38, base_z + 0.32), 0.22, 0.45, trim_mat, vertices=24, role='prop')
        for n in range(6):
            angle = (n / 6.0) * math.tau
            leaf = cube('generic plant leaf detail', (x + math.cos(angle) * 0.10, center[1] - sy * 0.38 + math.sin(angle) * 0.10, base_z + 0.68), (0.07, 0.18, 0.28), green_mat, 'prop')
            leaf.rotation_euler[2] = angle
            added += 1
        added += 1
    add_bevel(cube('generic foreground detail rail', (center[0], center[1] - sy * 0.52, base_z + 0.32), (max(sx * 0.65, 2.0), 0.08, 0.22), trim_mat, 'detail'), 0.018, 1)
    added += 1

if len([ob for ob in bpy.context.scene.objects if getattr(ob, 'type', '') == 'LIGHT']) == 0:
    bpy.ops.object.light_add(type='AREA', location=(center[0], center[1] - max(sy, 4.0), base_z + max(sz, 3.0) + 2.0))
    area = bpy.context.object
    area.name = 'enhancement large soft key light'
    area.data.energy = 520
    area.data.size = max(max(sx, sy) * 0.55, 4.0)
    mark(area, 'light')
    added += 1

if bpy.context.scene.camera is None:
    bpy.ops.object.camera_add(
        location=(center[0] + max(sx, 4.0) * 0.75, center[1] - max(sy, 4.0) * 0.95, base_z + max(sz, 2.5) * 0.85),
        rotation=(math.radians(62), 0, math.radians(42)),
    )
    bpy.context.scene.camera = bpy.context.object
    mark(bpy.context.object, 'camera')
    added += 1

check_items = [
    'DETAIL PASS',
    'materials/bevels checked',
    'rooms: ' + str(len(rooms)),
    'portals: ' + str(len(portals)),
    'collision: ' + str(len(collisions)),
]
label_body = '\n'.join(check_items)
board = cube('Ay-Eye enhancement checklist board', (center[0] - sx * 0.46, center[1] + sy * 0.56, base_z + 1.15), (2.4, 0.08, 1.1), trim_mat, 'label')
add_bevel(board, 0.018, 1)
text_obj('Ay-Eye enhancement checklist text', label_body, (center[0] - sx * 0.46 - 1.05, center[1] + sy * 0.61, base_z + 1.2), 0.105, white_mat, rotation=(math.radians(82), 0, 0), align='LEFT', role='label')
added += 2

try:
    bpy.context.scene.render.engine = 'CYCLES'
    if hasattr(bpy.context.scene, 'cycles'):
        bpy.context.scene.cycles.samples = max(getattr(bpy.context.scene.cycles, 'samples', 64), 80)
    bpy.context.scene.view_settings.view_transform = 'Filmic'
    bpy.context.scene.view_settings.look = 'Medium High Contrast'
except Exception as render_settings_error:
    print('AYEYE_ENHANCEMENT_RENDER_WARNING:', render_settings_error)

screen = getattr(bpy.context, 'screen', None)
if screen:
    try:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                region_3d = area.spaces.active.region_3d
                region_3d.view_location = (center[0], center[1], base_z + max(sz * 0.45, 1.0))
                region_3d.view_distance = max(sx, sy, 5.0) * 1.12
    except Exception as view_error:
        print('AYEYE_ENHANCEMENT_VIEW_WARNING:', view_error)

for ob in bpy.context.scene.objects:
    ob.select_set(False)

print(
    'AYEYE_ENHANCEMENT_RESULT: added={} rooms={} portals={} collision={} title={}'.format(
        added, len(rooms), len(portals), len(collisions), TASK_TITLE
    )
)
"""


def _looks_like_mlo_request(prompt: str) -> bool:
    return any(term in prompt for term in (
        "mlo", "fivem", "gta", "sollumz", "ymap", "ytyp", "ydr", "ybn",
        "interior", "portal", "room", "collision", "convert", "conversion",
        "house", "garage", "shop", "store", "restaurant", "office",
        "warehouse", "club", "bar", "motel", "apartment",
    ))


def _safe_text(value: str, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    text = text.replace("\\", "\\\\").replace("'", "\\'")
    return text[:160] or fallback


def _select_mlo_profile(prompt: str) -> dict:
    p = prompt.lower()
    profiles = {
        "garage": {
            "keywords": ("garage", "mechanic", "workshop", "car repair", "vehicle"),
            "title": "Mechanic Garage MLO",
            "shell": (8.8, 7.2, 3.2),
            "rooms": [
                ("vehicle service bay", (-1.7, 0.1, 1.55), (5.2, 5.6, 2.8)),
                ("tool office", (3.0, -1.8, 1.45), (2.1, 2.0, 2.55)),
                ("parts storage", (3.0, 1.55, 1.45), (2.1, 2.35, 2.55)),
            ],
            "portals": [
                ("front roller door portal", (-2.0, -3.68, 1.5), (3.8, 0.06, 2.5)),
                ("office door portal", (1.85, -1.8, 1.05), (0.9, 0.06, 1.9)),
                ("storage door portal", (1.85, 1.55, 1.05), (0.9, 0.06, 1.9)),
            ],
            "details": "garage",
        },
        "house": {
            "keywords": ("house", "home", "apartment", "flat", "villa"),
            "title": "Residential House MLO",
            "shell": (8.2, 6.4, 3.0),
            "rooms": [
                ("living room", (-2.0, -0.8, 1.35), (3.6, 3.2, 2.5)),
                ("kitchen", (2.0, -1.0, 1.35), (3.0, 2.8, 2.5)),
                ("bedroom", (-2.1, 2.0, 1.35), (3.4, 2.2, 2.5)),
                ("bathroom", (2.0, 2.0, 1.35), (2.2, 2.0, 2.5)),
            ],
            "portals": [
                ("front door portal", (0, -3.25, 1.05), (1.05, 0.06, 1.95)),
                ("living kitchen portal", (0.2, -0.9, 1.05), (1.2, 0.06, 1.95)),
                ("hall bedroom portal", (-0.5, 1.45, 1.05), (0.9, 0.06, 1.9)),
                ("hall bathroom portal", (0.95, 1.45, 1.05), (0.85, 0.06, 1.9)),
            ],
            "details": "house",
        },
        "restaurant": {
            "keywords": ("restaurant", "diner", "food", "kitchen", "cafe", "coffee"),
            "title": "Restaurant MLO",
            "shell": (9.0, 6.8, 3.2),
            "rooms": [
                ("dining room", (-1.8, -0.8, 1.45), (5.0, 4.4, 2.75)),
                ("commercial kitchen", (2.8, 0.9, 1.45), (2.8, 3.4, 2.75)),
                ("service counter", (2.4, -2.35, 1.35), (3.2, 1.2, 2.55)),
                ("restroom block", (-3.2, 2.05, 1.35), (1.8, 1.9, 2.5)),
            ],
            "portals": [
                ("front entry portal", (-1.6, -3.45, 1.08), (1.35, 0.06, 2.05)),
                ("kitchen swing door portal", (1.2, 0.9, 1.05), (1.0, 0.06, 1.95)),
                ("restroom corridor portal", (-2.1, 1.2, 1.05), (0.9, 0.06, 1.9)),
            ],
            "details": "restaurant",
        },
        "shop": {
            "keywords": ("shop", "store", "retail", "market", "boutique"),
            "title": "Retail Shop MLO",
            "shell": (8.6, 6.0, 3.0),
            "rooms": [
                ("retail floor", (-1.2, -0.7, 1.35), (5.8, 4.2, 2.55)),
                ("checkout zone", (2.8, -2.2, 1.25), (2.0, 1.3, 2.35)),
                ("stock room", (2.6, 1.4, 1.3), (2.3, 2.2, 2.45)),
            ],
            "portals": [
                ("glass storefront portal", (-1.2, -3.05, 1.15), (3.0, 0.06, 2.15)),
                ("stock door portal", (1.35, 1.25, 1.05), (0.9, 0.06, 1.9)),
            ],
            "details": "shop",
        },
        "office": {
            "keywords": ("office", "agency", "workspace", "conference", "meeting"),
            "title": "Office MLO",
            "shell": (9.2, 6.2, 3.0),
            "rooms": [
                ("reception", (-3.0, -1.8, 1.35), (2.4, 2.2, 2.5)),
                ("open office", (0.2, -0.6, 1.35), (4.4, 3.8, 2.5)),
                ("conference room", (3.0, 1.4, 1.35), (2.4, 2.5, 2.5)),
                ("manager office", (-3.0, 1.5, 1.35), (2.2, 2.2, 2.5)),
            ],
            "portals": [
                ("main office entry portal", (-3.0, -3.12, 1.05), (1.2, 0.06, 1.95)),
                ("conference glass portal", (1.65, 1.2, 1.05), (1.2, 0.06, 1.95)),
                ("manager door portal", (-1.85, 1.35, 1.05), (0.9, 0.06, 1.9)),
            ],
            "details": "office",
        },
        "warehouse": {
            "keywords": ("warehouse", "storage", "factory", "loading", "depot"),
            "title": "Warehouse MLO",
            "shell": (10.5, 8.0, 4.2),
            "rooms": [
                ("main warehouse floor", (-1.0, 0.4, 1.9), (7.4, 6.3, 3.6)),
                ("loading office", (3.8, -2.5, 1.35), (2.0, 2.0, 2.5)),
                ("secure storage cage", (3.4, 1.9, 1.35), (2.4, 2.2, 2.5)),
            ],
            "portals": [
                ("truck loading bay portal", (-2.0, -4.05, 1.7), (4.4, 0.06, 3.0)),
                ("office door portal", (2.6, -2.4, 1.05), (0.95, 0.06, 1.9)),
                ("storage cage portal", (2.2, 1.9, 1.05), (0.95, 0.06, 1.9)),
            ],
            "details": "warehouse",
        },
        "club": {
            "keywords": ("club", "bar", "lounge", "nightclub", "pub"),
            "title": "Club Bar MLO",
            "shell": (9.4, 7.0, 3.2),
            "rooms": [
                ("main lounge", (-1.4, -0.6, 1.45), (5.2, 4.6, 2.75)),
                ("bar service area", (2.9, -1.5, 1.35), (2.5, 2.6, 2.55)),
                ("stage booth", (-2.8, 2.1, 1.35), (2.4, 1.8, 2.45)),
                ("back room", (2.8, 1.9, 1.3), (2.3, 2.0, 2.45)),
            ],
            "portals": [
                ("club entry portal", (-1.4, -3.55, 1.1), (1.4, 0.06, 2.05)),
                ("back room portal", (1.65, 1.8, 1.05), (0.9, 0.06, 1.9)),
            ],
            "details": "club",
        },
    }
    def has_keyword(keyword: str) -> bool:
        return bool(re.search(r"\b" + re.escape(keyword) + r"\b", p))

    for profile in profiles.values():
        if any(has_keyword(k) for k in profile["keywords"]):
            return profile
    return profiles["shop"]


def _mlo_scene_script(description: str, reference_summary: str) -> str:
    prompt = f"{description}\n{reference_summary}"
    profile = _select_mlo_profile(prompt)
    title = _safe_text(description or reference_summary or profile["title"], profile["title"])
    detail_block = _mlo_detail_block(profile["details"])
    return f"""
import bpy
import math

SCENE_TAG = 'ayeye_mlo_scene'
for existing in list(bpy.data.objects):
    if str(existing.get('ayeye_generated_scene') or '').startswith('ayeye_'):
        bpy.data.objects.remove(existing, do_unlink=True)

MLO_TITLE = {profile["title"]!r}
ROOMS = {profile["rooms"]!r}
PORTALS = {profile["portals"]!r}
SHELL = {profile["shell"]!r}

def mark(ob, role='detail'):
    ob['ayeye_generated_scene'] = SCENE_TAG
    ob['ayeye_mlo_role'] = role
    return ob

def mat(name, color, roughness=0.58, metallic=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        if 'Base Color' in bsdf.inputs:
            bsdf.inputs['Base Color'].default_value = color
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = roughness
        if 'Metallic' in bsdf.inputs:
            bsdf.inputs['Metallic'].default_value = metallic
        if 'Alpha' in bsdf.inputs:
            bsdf.inputs['Alpha'].default_value = alpha
    if alpha < 1.0:
        m.blend_method = 'BLEND'
        m.use_screen_refraction = True
    return m

wall_mat = mat('painted plaster walls', (0.62, 0.60, 0.55, 1), 0.78)
floor_mat = mat('dark polished concrete floor', (0.18, 0.18, 0.17, 1), 0.72)
ceiling_mat = mat('plain acoustic ceiling panels', (0.72, 0.70, 0.64, 1), 0.84)
trim_mat = mat('black metal trim and frames', (0.025, 0.024, 0.022, 1), 0.6, 0.05)
wood_mat = mat('warm interior wood', (0.55, 0.32, 0.16, 1), 0.5)
glass_mat = mat('transparent glass portal surfaces', (0.18, 0.46, 0.75, 0.32), 0.12, 0.0, 0.32)
guide_mat = mat('blue MLO room portal collision guides', (0.08, 0.35, 1.0, 0.25), 0.35, 0.0, 0.25)
accent_mat = mat('warm accent props', (0.95, 0.55, 0.18, 1), 0.45)
green_mat = mat('interior plant green', (0.10, 0.34, 0.14, 1), 0.7)
red_mat = mat('red warning and interaction markers', (0.75, 0.04, 0.035, 1), 0.55)
white_mat = mat('white label text', (0.95, 0.92, 0.84, 1), 0.5)

def cube(name, loc, scale, material, role='detail'):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        ob.data.materials.append(material)
    return mark(ob, role)

def cyl(name, loc, radius, depth, material, vertices=28, role='detail'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    ob = bpy.context.object
    ob.name = name
    if material:
        ob.data.materials.append(material)
    try:
        for poly in ob.data.polygons:
            poly.use_smooth = True
    except Exception:
        pass
    return mark(ob, role)

def add_bevel(ob, amount=0.035, segments=2):
    bevel = ob.modifiers.new('professional bevels', 'BEVEL')
    bevel.width = amount
    bevel.segments = segments
    ob.modifiers.new('weighted normals', 'WEIGHTED_NORMAL')

def text_obj(name, body, loc, size, material, rotation=(math.radians(90), 0, 0), align='CENTER', role='label'):
    bpy.ops.object.text_add(location=loc, rotation=rotation)
    ob = bpy.context.object
    ob.name = name
    ob.data.body = body
    ob.data.align_x = align
    ob.data.align_y = 'CENTER'
    ob.data.size = size
    ob.data.extrude = 0.015
    if material:
        ob.data.materials.append(material)
    return mark(ob, role)

sx, sy, sz = SHELL
floor = cube('MLO main floor slab', (0, 0, 0), (sx + 1.2, sy + 1.2, 0.16), floor_mat, 'floor')
add_bevel(floor, 0.02, 1)
ceiling = cube('MLO ceiling plane', (0, 0, sz), (sx, sy, 0.12), ceiling_mat, 'ceiling')
add_bevel(ceiling, 0.015, 1)
wall_specs = [
    ('front exterior wall with openings', (0, -sy/2, sz/2), (sx, 0.16, sz)),
    ('rear exterior wall', (0, sy/2, sz/2), (sx, 0.16, sz)),
    ('left exterior wall', (-sx/2, 0, sz/2), (0.16, sy, sz)),
    ('right exterior wall', (sx/2, 0, sz/2), (0.16, sy, sz)),
]
for name, loc, scale in wall_specs:
    ob = cube(name, loc, scale, wall_mat, 'shell')
    add_bevel(ob, 0.015, 1)

for idx, (room_name, loc, scale) in enumerate(ROOMS):
    room = cube('MLO room volume guide - ' + room_name, loc, scale, guide_mat, 'room')
    room.display_type = 'WIRE'
    room.hide_render = True
    room['ayeye_mlo_room_id'] = idx
    text_obj('room label - ' + room_name, room_name.upper(), (loc[0], loc[1], loc[2] + scale[2] / 2 + 0.18), 0.18, white_mat, rotation=(math.radians(75), 0, 0), role='label')

for idx, (portal_name, loc, scale) in enumerate(PORTALS):
    portal = cube('MLO portal guide - ' + portal_name, loc, scale, glass_mat, 'portal')
    portal.display_type = 'WIRE'
    portal.hide_render = True
    portal['ayeye_mlo_portal_id'] = idx
    frame_top = cube('portal top frame - ' + portal_name, (loc[0], loc[1], loc[2] + scale[2]/2), (scale[0] + 0.18, 0.08, 0.08), trim_mat, 'portal_frame')
    frame_bottom = cube('portal threshold - ' + portal_name, (loc[0], loc[1], loc[2] - scale[2]/2), (scale[0] + 0.18, 0.08, 0.08), trim_mat, 'portal_frame')
    add_bevel(frame_top, 0.01, 1)
    add_bevel(frame_bottom, 0.01, 1)

collision = cube('collision proxy guide - whole MLO shell', (0, 0, sz/2), (sx + 0.25, sy + 0.25, sz + 0.15), guide_mat, 'collision')
collision.display_type = 'WIRE'
collision.hide_render = True

# Interior partition lines between room centers.
for i in range(len(ROOMS) - 1):
    a = ROOMS[i][1]
    b = ROOMS[i + 1][1]
    wall = cube('interior partition wall segment', ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 1.35), (0.12 if abs(a[0]-b[0]) > abs(a[1]-b[1]) else 2.2, 2.2 if abs(a[0]-b[0]) > abs(a[1]-b[1]) else 0.12, 2.4), wall_mat, 'partition')
    add_bevel(wall, 0.012, 1)

# Generic pro details every MLO needs.
for x in [-sx/2 + 0.7, sx/2 - 0.7]:
    for y in [-sy/2 + 0.7, sy/2 - 0.7]:
        lamp = cyl('recessed ceiling downlight', (x, y, sz - 0.14), 0.11, 0.04, accent_mat, vertices=24, role='light_fixture')
        bpy.ops.object.light_add(type='POINT', location=(x, y, sz - 0.35))
        light = bpy.context.object
        light.name = 'warm interior MLO point light'
        light.data.energy = 90
        light.data.color = (1.0, 0.72, 0.45)
        light.data.shadow_soft_size = 1.4
        mark(light, 'light')

for x in [-sx/2 + 0.55, sx/2 - 0.55]:
    duct = cube('ceiling HVAC duct run', (x, 0, sz - 0.28), (0.24, sy - 1.2, 0.18), trim_mat, 'utility')
    add_bevel(duct, 0.015, 1)
for y in [-sy/2 + 0.8, sy/2 - 0.8]:
    exit_sign = cube('red EXIT sign marker', (0, y, 2.35), (0.72, 0.06, 0.22), red_mat, 'signage')
    text_obj('EXIT text label', 'EXIT', (-0.22, y - 0.04, 2.35), 0.13, white_mat, role='signage')

{detail_block}

text_obj('MLO title label', MLO_TITLE + ' - rooms / portals / collision guides', (-sx/2 + 0.3, sy/2 + 0.45, 0.35), 0.20, white_mat, rotation=(math.radians(75), 0, 0), align='LEFT', role='label')

bpy.ops.object.light_add(type='AREA', location=(0, -sy/2 - 3.5, sz + 2.8))
area = bpy.context.object
area.name = 'large soft MLO preview light'
area.data.energy = 500
area.data.size = 5.5
mark(area, 'light')

bpy.ops.object.camera_add(location=(sx * 0.75, -sy * 0.95, sz * 0.85), rotation=(math.radians(62), 0, math.radians(42)))
bpy.context.scene.camera = bpy.context.object
mark(bpy.context.object, 'camera')

bpy.context.scene['ayeye_mlo_template'] = MLO_TITLE
bpy.context.scene['ayeye_mlo_note'] = 'Draft MLO blockout with room, portal, and collision guide objects. Final Sollumz export still needs manual validation.'

try:
    bpy.context.scene.render.engine = 'CYCLES'
    if hasattr(bpy.context.scene, 'cycles'):
        bpy.context.scene.cycles.samples = 80
    bpy.context.scene.view_settings.view_transform = 'Filmic'
    bpy.context.scene.view_settings.look = 'Medium High Contrast'
except Exception as render_settings_error:
    print('AYEYE_RENDER_SETTINGS_WARNING:', render_settings_error)

screen = getattr(bpy.context, 'screen', None)
if screen:
    try:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                region_3d = area.spaces.active.region_3d
                region_3d.view_location = (0, 0, 1.2)
                region_3d.view_distance = max(sx, sy) * 1.25
    except Exception as view_error:
        print('AYEYE_VIEW_WARNING:', view_error)

for ob in bpy.context.scene.objects:
    ob.select_set(False)

print('AYEYE_MLO_SCENE_CREATED: {title} template=' + MLO_TITLE)
"""


def _mlo_detail_block(kind: str) -> str:
    blocks = {
        "garage": """
for x in [-2.6, -0.8, 1.0]:
    lift = cube('hydraulic vehicle lift platform', (x, -0.2, 0.22), (1.05, 3.4, 0.14), trim_mat, 'prop')
    add_bevel(lift, 0.02, 1)
    for y in [-1.4, 1.0]:
        cyl('yellow lift arm pivot', (x, y, 0.42), 0.12, 0.12, accent_mat, vertices=20, role='prop')
for x in [2.5, 3.25]:
    bench = cube('tool workbench with drawers', (x, -2.6, 0.55), (1.1, 0.45, 0.72), wood_mat, 'prop')
    add_bevel(bench, 0.025, 1)
    peg = cube('tool pegboard wall', (x, -3.5, 1.55), (1.05, 0.06, 1.0), trim_mat, 'prop')
for i in range(8):
    cube('small hanging tool silhouettes', (2.0 + i*0.18, -3.56, 1.55 + (i%3)*0.18), (0.06, 0.035, 0.20), red_mat if i%2 else accent_mat, 'prop')
for x in [-3.4, -2.8, -2.2]:
    cyl('stacked tire prop', (x, 2.4, 0.32), 0.34, 0.22, trim_mat, vertices=32, role='prop')
""",
        "house": """
sofa = cube('living room sectional sofa', (-2.6, -1.4, 0.55), (1.8, 0.72, 0.55), wood_mat, 'prop')
add_bevel(sofa, 0.05, 2)
cube('coffee table', (-1.55, -1.0, 0.32), (0.9, 0.52, 0.18), trim_mat, 'prop')
for x in [1.4, 2.2, 3.0]:
    cab = cube('kitchen lower cabinet run', (x, -2.65, 0.55), (0.65, 0.45, 0.75), wood_mat, 'prop')
    add_bevel(cab, 0.025, 1)
cube('kitchen island with sink', (1.9, -0.9, 0.55), (1.45, 0.72, 0.78), wood_mat, 'prop')
bed = cube('bedroom bed with headboard', (-2.3, 2.2, 0.48), (1.65, 1.95, 0.36), white_mat, 'prop')
head = cube('bed headboard', (-2.3, 3.22, 0.92), (1.75, 0.15, 0.85), wood_mat, 'prop')
for x in [1.45, 2.2]:
    cube('bathroom fixture block', (x, 2.35, 0.48), (0.45, 0.55, 0.55), white_mat, 'prop')
""",
        "restaurant": """
for x in [-3.0, -1.6, -0.2]:
    for y in [-1.8, -0.55, 0.7]:
        cyl('round dining table', (x, y, 0.55), 0.34, 0.08, wood_mat, vertices=32, role='prop')
        for dx, dy in [(0.55,0),(-0.55,0),(0,0.55),(0,-0.55)]:
            seat = cube('dining chair', (x+dx, y+dy, 0.42), (0.34, 0.32, 0.22), trim_mat, 'prop')
            add_bevel(seat, 0.018, 1)
cube('long restaurant service counter', (2.2, -2.25, 0.72), (2.6, 0.55, 0.86), wood_mat, 'prop')
for x in [2.0, 2.55, 3.1]:
    cube('stainless kitchen prep table', (x, 1.0, 0.62), (0.62, 1.35, 0.78), trim_mat, 'prop')
cube('wall mounted menu board', (1.5, -3.35, 1.72), (1.8, 0.06, 0.95), trim_mat, 'signage')
text_obj('menu readable text', 'MENU  SPECIALS', (0.78, -3.42, 1.72), 0.14, white_mat, align='LEFT', role='signage')
""",
        "shop": """
for x in [-3.0, -1.8, -0.6, 0.6]:
    shelf = cube('retail gondola shelf unit', (x, -0.15, 0.82), (0.72, 2.8, 1.45), wood_mat, 'prop')
    add_bevel(shelf, 0.025, 1)
    for z in [0.55, 0.95, 1.35]:
        cube('individual retail shelf plank', (x, -0.15, z), (0.78, 2.85, 0.055), trim_mat, 'prop')
for y in [-2.2, -1.55, -0.9]:
    checkout = cube('checkout counter module', (2.85, y, 0.55), (1.45, 0.42, 0.72), wood_mat, 'prop')
    add_bevel(checkout, 0.025, 1)
cube('glass storefront display', (-1.15, -3.05, 1.35), (3.0, 0.06, 1.75), glass_mat, 'prop')
text_obj('storefront sign text', 'OPEN STORE', (-1.85, -3.12, 2.38), 0.22, accent_mat, align='LEFT', role='signage')
""",
        "office": """
for row, y in enumerate([-1.7, -0.55, 0.6]):
    for x in [-0.9, 0.55]:
        desk = cube('office workstation desk', (x, y, 0.55), (1.05, 0.62, 0.08), wood_mat, 'prop')
        add_bevel(desk, 0.02, 1)
        cube('thin monitor screen', (x, y-0.22, 0.96), (0.46, 0.05, 0.30), trim_mat, 'prop')
        cube('office chair', (x, y+0.42, 0.48), (0.42, 0.42, 0.32), trim_mat, 'prop')
cube('reception desk', (-3.0, -2.2, 0.65), (1.55, 0.62, 0.82), wood_mat, 'prop')
cube('conference table', (3.0, 1.4, 0.58), (1.7, 0.9, 0.10), wood_mat, 'prop')
for x in [2.25, 2.75, 3.25, 3.75]:
    cube('conference chair', (x, 0.76, 0.46), (0.34, 0.34, 0.30), trim_mat, 'prop')
cube('glass conference wall', (1.72, 1.4, 1.35), (0.06, 2.25, 1.85), glass_mat, 'prop')
""",
        "warehouse": """
for x in [-3.6, -2.2, -0.8, 0.6]:
    rack = cube('tall warehouse pallet rack frame', (x, 1.2, 1.35), (0.82, 3.5, 2.45), trim_mat, 'prop')
    rack.display_type = 'TEXTURED'
    for z in [0.55, 1.15, 1.75, 2.35]:
        cube('orange pallet rack beam', (x, 1.2, z), (0.9, 3.6, 0.07), accent_mat, 'prop')
for x in [-3.5, -2.6, -1.7, -0.8, 0.1, 1.0]:
    pallet = cube('wood pallet stack', (x, -2.2, 0.22), (0.75, 0.55, 0.16), wood_mat, 'prop')
    add_bevel(pallet, 0.012, 1)
fork = cube('forklift body proxy', (2.5, -0.7, 0.55), (1.0, 0.62, 0.65), red_mat, 'prop')
cube('forklift mast proxy', (2.05, -0.7, 1.05), (0.12, 0.72, 1.35), trim_mat, 'prop')
""",
        "club": """
bar = cube('long illuminated bar counter', (2.6, -1.6, 0.68), (2.4, 0.62, 0.86), wood_mat, 'prop')
add_bevel(bar, 0.035, 2)
for x in [1.55, 2.1, 2.65, 3.2, 3.75]:
    cyl('bar stool', (x, -2.3, 0.62), 0.18, 0.55, trim_mat, vertices=24, role='prop')
stage = cube('small DJ stage platform', (-2.9, 2.0, 0.28), (2.0, 1.25, 0.28), trim_mat, 'prop')
add_bevel(stage, 0.035, 1)
cube('DJ booth table', (-2.9, 2.0, 0.78), (1.35, 0.45, 0.35), wood_mat, 'prop')
for x in [-3.5, -2.9, -2.3]:
    bpy.ops.object.light_add(type='SPOT', location=(x, 0.8, 2.75), rotation=(math.radians(68), 0, 0))
    spot = bpy.context.object
    spot.name = 'colored club spot light'
    spot.data.energy = 160
    spot.data.color = (0.6, 0.2, 1.0)
    mark(spot, 'light')
""",
    }
    return blocks.get(kind, blocks["shop"])


def _container_cafe_script(description: str, reference_summary: str) -> str:
    title = _safe_text(description or reference_summary, "Reference Container Cafe")
    prompt = f"{description} {reference_summary}".lower()
    mlo_block = _container_cafe_mlo_block() if any(
        term in prompt for term in ("mlo", "interior", "convert", "conversion", "portal", "room")
    ) else ""
    return f"""
import bpy
import math

SCENE_TAG = 'ayeye_container_cafe'
for existing in list(bpy.data.objects):
    if str(existing.get('ayeye_generated_scene') or '').startswith('ayeye_'):
        bpy.data.objects.remove(existing, do_unlink=True)

def mark(ob):
    ob['ayeye_generated_scene'] = SCENE_TAG
    return ob

def mat(name, color, roughness=0.55, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        for socket_name, value in (
            ('Base Color', color),
            ('Roughness', roughness),
            ('Metallic', metallic),
        ):
            if socket_name in bsdf.inputs:
                bsdf.inputs[socket_name].default_value = value
    return m

steel = mat('warm dark corrugated steel', (0.12, 0.13, 0.12, 1), 0.72, 0.25)
trim = mat('matte black trim', (0.015, 0.014, 0.012, 1), 0.65, 0.05)
wood = mat('warm cafe wood', (0.55, 0.31, 0.13, 1), 0.48, 0.0)
glass = mat('slightly blue glass', (0.26, 0.50, 0.60, 0.38), 0.08, 0.0)
lightmat = mat('warm glowing interior', (1.0, 0.58, 0.18, 1), 0.2, 0.0)
cream = mat('painted cream signage', (0.90, 0.80, 0.58, 1), 0.5, 0.0)
green = mat('plant green', (0.12, 0.38, 0.16, 1), 0.65, 0.0)
groundmat = mat('concrete patio', (0.34, 0.33, 0.30, 1), 0.8, 0.0)
jointmat = mat('dark concrete control joints', (0.08, 0.08, 0.075, 1), 0.85, 0.0)
chalk = mat('matte chalkboard black', (0.02, 0.025, 0.022, 1), 0.9, 0.0)
white = mat('painted white lettering', (0.95, 0.92, 0.82, 1), 0.52, 0.0)
rust = mat('subtle weathered rust accents', (0.55, 0.20, 0.08, 1), 0.8, 0.0)
soil = mat('dark planter soil', (0.08, 0.045, 0.025, 1), 0.95, 0.0)
red = mat('small red utility accents', (0.72, 0.05, 0.035, 1), 0.55, 0.0)

def cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        ob.data.materials.append(material)
    return mark(ob)

def cyl(name, loc, radius, depth, material, vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    ob = bpy.context.object
    ob.name = name
    if material:
        ob.data.materials.append(material)
    try:
        for poly in ob.data.polygons:
            poly.use_smooth = True
    except Exception:
        pass
    return mark(ob)

def text_obj(name, body, loc, size, material, rotation=(math.radians(90), 0, 0), align='CENTER'):
    bpy.ops.object.text_add(location=loc, rotation=rotation)
    ob = bpy.context.object
    ob.name = name
    ob.data.body = body
    ob.data.align_x = align
    ob.data.align_y = 'CENTER'
    ob.data.size = size
    ob.data.extrude = 0.018
    if material:
        ob.data.materials.append(material)
    return mark(ob)

def add_bevel(ob, amount=0.04, segments=2):
    bevel = ob.modifiers.new('soft bevels', 'BEVEL')
    bevel.width = amount
    bevel.segments = segments
    ob.modifiers.new('weighted cafe normals', 'WEIGHTED_NORMAL')

ground = cube('wide concrete patio slab', (0, 0, -0.08), (12.5, 8.0, 0.16), groundmat)
add_bevel(ground, 0.02, 1)
for x in [i * 1.0 - 6.0 for i in range(13)]:
    cube('sawn patio control joint long line', (x, 0, 0.015), (0.025, 7.55, 0.018), jointmat)
for y in [i * 1.0 - 3.5 for i in range(8)]:
    cube('sawn patio control joint cross line', (0, y, 0.018), (12.0, 0.025, 0.018), jointmat)

container = cube('shipping container cafe body', (0, 0, 1.35), (7.5, 2.4, 2.7), steel)
add_bevel(container, 0.06, 3)
for x in (-3.9, 3.9):
    for y in (-1.28, 1.28):
        post = cube('heavy container corner post', (x, y, 1.35), (0.18, 0.18, 2.82), trim)
        add_bevel(post, 0.025, 1)
        for z in (0.06, 2.66):
            casting = cube('container corner casting block', (x, y, z), (0.38, 0.28, 0.18), rust)
            add_bevel(casting, 0.02, 1)
for z in (0.1, 2.66):
    rail_front = cube('horizontal container edge rail front', (0, -1.31, z), (7.75, 0.10, 0.14), trim)
    rail_back = cube('horizontal container edge rail rear', (0, 1.31, z), (7.75, 0.10, 0.14), trim)
    add_bevel(rail_front, 0.018, 1)
    add_bevel(rail_back, 0.018, 1)

# Corrugated ribs across front/back/sides.
for x in [i * 0.42 - 3.57 for i in range(18)]:
    rib = cube('vertical corrugation rib', (x, -1.235, 1.35), (0.055, 0.08, 2.58), trim)
    add_bevel(rib, 0.01, 1)
    rib2 = cube('rear corrugation rib', (x, 1.235, 1.35), (0.055, 0.08, 2.58), trim)
    add_bevel(rib2, 0.01, 1)
for x in (-3.82, 3.82):
    for y in [i * 0.34 - 1.02 for i in range(7)]:
        side_rib = cube('side corrugation rib', (x, y, 1.35), (0.08, 0.045, 2.58), trim)
        add_bevel(side_rib, 0.01, 1)

service = cube('large open service window with dark glass', (-1.15, -1.285, 1.65), (3.4, 0.08, 1.25), glass)
add_bevel(service, 0.035, 2)
for name, loc, scale in [
    ('service window top frame', (-1.15, -1.355, 2.31), (3.65, 0.07, 0.10)),
    ('service window bottom frame', (-1.15, -1.355, 0.99), (3.65, 0.07, 0.10)),
    ('service window left frame', (-3.02, -1.355, 1.65), (0.10, 0.07, 1.35)),
    ('service window right frame', (0.72, -1.355, 1.65), (0.10, 0.07, 1.35)),
    ('service window sliding split rail', (-1.15, -1.365, 1.65), (0.055, 0.08, 1.20)),
]:
    frame_ob = cube(name, loc, scale, trim)
    add_bevel(frame_ob, 0.012, 1)
counter = cube('wood serving counter under window', (-1.15, -1.72, 1.0), (3.75, 0.65, 0.22), wood)
add_bevel(counter, 0.045, 2)
for x in [-2.55, -1.75, -0.95, -0.15]:
    bracket = cube('black triangular counter bracket proxy', (x, -1.38, 0.78), (0.12, 0.16, 0.36), trim)
    bracket.rotation_euler[0] = math.radians(-18)
awning = cube('folded black metal awning over service window', (-1.15, -1.78, 2.45), (4.1, 0.82, 0.12), trim)
awning.rotation_euler[0] = math.radians(-10)
add_bevel(awning, 0.025, 1)
for x in [-3.0, -2.2, -1.4, -0.6, 0.2, 1.0]:
    slat = cube('individual awning rib detail', (x, -1.82, 2.39), (0.055, 0.82, 0.055), rust)
    slat.rotation_euler[0] = math.radians(-10)
under_light = cube('warm light strip under awning', (-1.15, -1.93, 2.27), (3.7, 0.035, 0.045), lightmat)
add_bevel(under_light, 0.01, 1)

door = cube('staff door with round handle', (2.85, -1.29, 1.22), (1.0, 0.08, 1.95), trim)
add_bevel(door, 0.035, 2)
handle = cyl('small brass door handle', (3.22, -1.36, 1.22), 0.055, 0.05, cream, vertices=20)
handle.rotation_euler[0] = math.radians(90)
for z in [0.55, 1.18, 1.82]:
    hinge = cube('visible staff door hinge plate', (2.36, -1.37, z), (0.08, 0.045, 0.18), rust)
    add_bevel(hinge, 0.008, 1)
step = cube('small anti-slip entry step', (2.85, -1.78, 0.16), (1.25, 0.55, 0.16), trim)
add_bevel(step, 0.03, 1)

sign = cube('cream sign board CAFE', (-1.15, -1.36, 2.95), (2.55, 0.08, 0.42), cream)
add_bevel(sign, 0.025, 2)
text_obj('raised sign text: CONTAINER CAFE', 'CONTAINER CAFE', (-1.92, -1.43, 2.89), 0.26, trim, align='LEFT')
text_obj('round coffee logo text', 'COFFEE', (1.62, -1.43, 2.88), 0.18, trim)

interior = cube('warm lit interior rectangle', (-1.15, -1.33, 1.65), (3.05, 0.05, 0.95), lightmat)
back_counter = cube('visible interior back counter', (-1.2, -1.05, 1.08), (2.8, 0.18, 0.30), wood)
espresso = cube('compact espresso machine with chrome top', (-1.85, -1.19, 1.35), (0.62, 0.26, 0.32), trim)
espresso_top = cube('espresso machine stainless warming tray', (-1.85, -1.34, 1.55), (0.58, 0.08, 0.08), cream)
grinder = cyl('coffee grinder hopper', (-1.05, -1.19, 1.48), 0.16, 0.28, glass, vertices=26)
grinder_base = cube('coffee grinder base', (-1.05, -1.2, 1.22), (0.28, 0.22, 0.24), trim)
for x in [-2.35, -2.08, -1.80, -1.52, -0.45, -0.18, 0.10]:
    cup = cyl('stacked white takeaway cup', (x, -1.25, 1.56), 0.055, 0.12, white, vertices=18)
    cup.rotation_euler[0] = math.radians(90)
for z in [1.75, 2.04]:
    shelf = cube('floating interior cup shelf', (-1.15, -1.18, z), (2.55, 0.10, 0.08), wood)
    add_bevel(shelf, 0.018, 1)
menu = cube('chalkboard menu with readable cafe items', (1.15, -1.36, 1.75), (1.05, 0.07, 0.90), chalk)
add_bevel(menu, 0.025, 2)
text_obj('chalk menu text espresso latte cold brew', 'ESPRESSO  LATTE\\nCOLD BREW  TEA', (0.72, -1.43, 1.78), 0.105, white, align='LEFT')
pickup = cube('order pickup shelf with pastry case', (1.14, -1.72, 0.92), (1.1, 0.48, 0.18), wood)
case = cube('glass pastry display case', (1.14, -1.83, 1.20), (0.92, 0.32, 0.26), glass)
for x in [0.82, 1.08, 1.34]:
    pastry = cyl('small pastry inside display case', (x, -1.88, 1.32), 0.07, 0.05, cream, vertices=18)
    pastry.rotation_euler[0] = math.radians(90)

# Roof and utility details.
roof_unit = cube('roof HVAC unit with fan grille', (2.35, 0.05, 2.96), (1.15, 0.88, 0.38), cream)
add_bevel(roof_unit, 0.035, 2)
for x in [1.92, 2.17, 2.42, 2.67, 2.92]:
    grille = cube('HVAC black grille slat', (x, -0.42, 3.18), (0.055, 0.08, 0.16), trim)
vent = cyl('round roof exhaust stack', (3.25, 0.78, 3.08), 0.16, 0.42, trim, vertices=24)
rain_pipe = cyl('front rainwater downpipe', (-3.62, -1.40, 1.20), 0.045, 2.30, trim, vertices=16)
rain_pipe.rotation_euler[0] = math.radians(0)
utility_box = cube('small electrical utility box', (3.55, 1.34, 1.15), (0.55, 0.10, 0.72), cream)
red_switch = cube('red emergency shutoff switch', (3.55, 1.41, 1.25), (0.22, 0.045, 0.16), red)

# Stools and queue details.
for x in [-2.5, -1.55, -0.60, 0.35]:
    seat = cyl('counter height stool round seat', (x, -2.18, 0.78), 0.22, 0.08, trim, vertices=28)
    leg = cyl('counter stool central leg', (x, -2.18, 0.47), 0.045, 0.58, trim, vertices=16)
    foot = cyl('counter stool foot ring', (x, -2.18, 0.27), 0.18, 0.025, rust, vertices=28)
for x in [1.85, 2.65, 3.45]:
    post = cyl('queue stanchion black post', (x, -2.55, 0.55), 0.045, 0.9, trim, vertices=16)
    rope = cube('queue rope segment', (x + 0.40, -2.55, 0.88), (0.78, 0.045, 0.045), red)
    add_bevel(rope, 0.015, 1)

# Patio furniture.
for i, x in enumerate([-3.2, -1.0, 1.35, 3.2]):
    table = cyl('round outdoor cafe table', (x, -3.05, 0.55), 0.42, 0.08, wood, vertices=40)
    leg = cyl('single black table pedestal', (x, -3.05, 0.28), 0.06, 0.48, trim, vertices=18)
    for sx, sy in [(0.75, 0), (-0.75, 0), (0, 0.75), (0, -0.75)]:
        seat = cube('simple patio chair seat', (x + sx, -3.05 + sy, 0.38), (0.45, 0.42, 0.10), trim)
        back = cube('simple patio chair back', (x + sx, -3.05 + sy + 0.19, 0.72), (0.45, 0.08, 0.55), trim)
        add_bevel(seat, 0.025, 1)
        add_bevel(back, 0.02, 1)

# Planters and greenery.
for x, y in [(-4.6, -1.8), (4.6, -1.8), (-4.8, 1.8), (4.8, 1.8), (0.8, -1.8)]:
    pot = cyl('dark round planter', (x, y, 0.28), 0.28, 0.45, trim, vertices=28)
    add_bevel(pot, 0.02, 1)
    dirt = cyl('visible planter soil disk', (x, y, 0.53), 0.24, 0.025, soil, vertices=28)
    for n in range(7):
        angle = (n / 7.0) * math.tau
        leaf = cube('stylized plant leaf', (x + math.cos(angle) * 0.13, y + math.sin(angle) * 0.13, 0.72), (0.08, 0.22, 0.36), green)
        leaf.rotation_euler[2] = angle
        leaf.rotation_euler[0] = math.radians(18)

# String lights.
for i in range(9):
    x = -4.0 + i
    bulb = cyl('warm string light bulb', (x, -2.05, 2.88 - abs(i - 4) * 0.035), 0.065, 0.09, lightmat, vertices=18)
    bulb.rotation_euler[0] = math.radians(90)
    bpy.ops.object.light_add(type='POINT', location=(x, -2.05, 2.78 - abs(i - 4) * 0.035))
    l = bpy.context.object
    l.name = 'warm cafe string light'
    l.data.energy = 80
    l.data.color = (1.0, 0.63, 0.32)
    l.data.shadow_soft_size = 1.5
    mark(l)

{mlo_block}

# Area lighting and camera.
bpy.ops.object.light_add(type='AREA', location=(0, -4.5, 6.5))
area = bpy.context.object
area.name = 'large soft evening key light'
area.data.energy = 450
area.data.size = 5
mark(area)

bpy.ops.object.camera_add(location=(6.5, -7.5, 4.3), rotation=(math.radians(62), 0, math.radians(41)))
bpy.context.scene.camera = bpy.context.object
mark(bpy.context.object)

try:
    bpy.context.scene.render.engine = 'CYCLES'
    if hasattr(bpy.context.scene, 'cycles'):
        bpy.context.scene.cycles.samples = 80
    bpy.context.scene.view_settings.view_transform = 'Filmic'
    bpy.context.scene.view_settings.look = 'Medium High Contrast'
except Exception as render_settings_error:
    print('AYEYE_RENDER_SETTINGS_WARNING:', render_settings_error)

for ob in bpy.context.scene.objects:
    ob.select_set(False)

screen = getattr(bpy.context, 'screen', None)
if screen:
    try:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                region_3d = area.spaces.active.region_3d
                region_3d.view_location = (0, 0, 1.2)
                region_3d.view_distance = 9
    except Exception as view_error:
        print('AYEYE_VIEW_WARNING:', view_error)

print('AYEYE_SCENE_CREATED: container cafe reference scene from task: {title}')
"""


def _container_cafe_mlo_block() -> str:
    """Return optional non-destructive MLO planning helpers for container cafes."""
    return """
# MLO conversion planning helpers. These are wireframe guide objects, not a final game export.
mlo = mat('blue MLO room and portal helper material', (0.10, 0.42, 1.0, 0.28), 0.35, 0.0)
try:
    mlo.blend_method = 'BLEND'
    mlo.use_screen_refraction = True
except Exception:
    pass
room = cube('MLO room volume guide - cafe interior', (-0.55, 0.08, 1.36), (6.6, 2.05, 2.35), mlo)
room['ayeye_mlo_role'] = 'room'
room.display_type = 'WIRE'
room.hide_render = True
portal_front = cube('MLO portal guide - service window opening', (-1.15, -1.42, 1.65), (3.45, 0.045, 1.28), mlo)
portal_front['ayeye_mlo_role'] = 'portal'
portal_front.display_type = 'WIRE'
portal_front.hide_render = True
portal_door = cube('MLO portal guide - staff door opening', (2.85, -1.42, 1.22), (1.02, 0.045, 1.95), mlo)
portal_door['ayeye_mlo_role'] = 'portal'
portal_door.display_type = 'WIRE'
portal_door.hide_render = True
collision_shell = cube('collision proxy guide - container shell', (0, 0, 1.35), (7.65, 2.55, 2.85), mlo)
collision_shell['ayeye_mlo_role'] = 'collision'
collision_shell.display_type = 'WIRE'
collision_shell.hide_render = True
text_obj('MLO helper label', 'MLO guides: room / portals / collision proxy', (-3.35, 1.55, 2.95), 0.16, mlo, rotation=(math.radians(72), 0, math.radians(180)), align='LEFT')
"""


def _generic_reference_scene_script(description: str, reference_summary: str) -> str:
    title = _safe_text(description or reference_summary, "Reference Inspired Scene")
    return f"""
import bpy
import math

SCENE_TAG = 'ayeye_reference_scene'
for existing in list(bpy.data.objects):
    if str(existing.get('ayeye_generated_scene') or '').startswith('ayeye_'):
        bpy.data.objects.remove(existing, do_unlink=True)

def mark(ob):
    ob['ayeye_generated_scene'] = SCENE_TAG
    return ob

def mat(name, color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        if 'Base Color' in bsdf.inputs:
            bsdf.inputs['Base Color'].default_value = color
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = 0.55
    return m

primary = mat('primary reference color', (0.20, 0.34, 0.48, 1))
accent = mat('warm accent color', (0.95, 0.58, 0.20, 1))
dark = mat('dark trim', (0.05, 0.05, 0.045, 1))
floor_mat = mat('simple studio floor', (0.38, 0.38, 0.35, 1))

def cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material)
    bevel = ob.modifiers.new('soft bevel', 'BEVEL')
    bevel.width = 0.04
    bevel.segments = 2
    ob.modifiers.new('weighted normals', 'WEIGHTED_NORMAL')
    return mark(ob)

cube('large base platform', (0, 0, -0.08), (8, 6, 0.16), floor_mat)
cube('main reference mass', (0, 0, 1.1), (3.8, 1.8, 2.2), primary)
cube('front feature panel', (0, -0.95, 1.2), (2.8, 0.08, 1.2), dark)
cube('accent canopy or header', (0, -1.25, 2.42), (4.4, 0.55, 0.18), accent)
cube('left supporting detail', (-2.25, -0.2, 0.9), (0.45, 1.4, 1.6), dark)
cube('right supporting detail', (2.25, -0.2, 0.9), (0.45, 1.4, 1.6), dark)

bpy.ops.object.text_add(location=(-3.3, -2.2, 0.35), rotation=(math.radians(75), 0, 0))
txt = bpy.context.object
txt.name = 'task label'
txt.data.body = '{title}'
txt.data.size = 0.28
txt.data.align_x = 'LEFT'
txt.data.materials.append(accent)
mark(txt)

bpy.ops.object.light_add(type='AREA', location=(0, -4, 5.5))
light = bpy.context.object
light.name = 'large soft reference light'
light.data.energy = 450
light.data.size = 5
mark(light)

bpy.ops.object.camera_add(location=(5.0, -6.0, 3.5), rotation=(math.radians(60), 0, math.radians(39)))
bpy.context.scene.camera = bpy.context.object
mark(bpy.context.object)
try:
    bpy.context.scene.render.engine = 'CYCLES'
    if hasattr(bpy.context.scene, 'cycles'):
        bpy.context.scene.cycles.samples = 64
except Exception as render_settings_error:
    print('AYEYE_RENDER_SETTINGS_WARNING:', render_settings_error)

screen = getattr(bpy.context, 'screen', None)
if screen:
    try:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                region_3d = area.spaces.active.region_3d
                region_3d.view_location = (0, 0, 1.0)
                region_3d.view_distance = 7
    except Exception as view_error:
        print('AYEYE_VIEW_WARNING:', view_error)

print('AYEYE_SCENE_CREATED: generic reference scene from task: {title}')
"""
