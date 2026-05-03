"""
Procedural Blender scene builder used by Ay-Eye.

This module turns a short visual/task description into a robust bpy script.
The goal is not to replace a human artist, but to give the agent a dependable
first-pass scene construction tool for reference-image requests.
"""

from __future__ import annotations


def build_scene_script(description: str = "", reference_summary: str = "") -> str:
    """Return a self-contained Blender Python script for a described scene."""
    prompt = f"{description}\n{reference_summary}".lower()
    if "container" in prompt and ("cafe" in prompt or "coffee" in prompt or "shop" in prompt):
        return _container_cafe_script(description, reference_summary)
    return _generic_reference_scene_script(description, reference_summary)


def _safe_text(value: str, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    text = text.replace("\\", "\\\\").replace("'", "\\'")
    return text[:160] or fallback


def _container_cafe_script(description: str, reference_summary: str) -> str:
    title = _safe_text(description or reference_summary, "Reference Container Cafe")
    return f"""
import bpy
import math

SCENE_TAG = 'ayeye_container_cafe'
for existing in list(bpy.data.objects):
    if existing.get('ayeye_generated_scene') == SCENE_TAG:
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
    return mark(ob)

def add_bevel(ob, amount=0.04, segments=2):
    bevel = ob.modifiers.new('soft bevels', 'BEVEL')
    bevel.width = amount
    bevel.segments = segments
    ob.modifiers.new('weighted cafe normals', 'WEIGHTED_NORMAL')

ground = cube('wide concrete patio slab', (0, 0, -0.08), (12.5, 8.0, 0.16), groundmat)
add_bevel(ground, 0.02, 1)

container = cube('shipping container cafe body', (0, 0, 1.35), (7.5, 2.4, 2.7), steel)
add_bevel(container, 0.06, 3)

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
counter = cube('wood serving counter under window', (-1.15, -1.72, 1.0), (3.75, 0.65, 0.22), wood)
add_bevel(counter, 0.045, 2)
awning = cube('folded black metal awning over service window', (-1.15, -1.78, 2.45), (4.1, 0.82, 0.12), trim)
awning.rotation_euler[0] = math.radians(-10)
add_bevel(awning, 0.025, 1)

door = cube('staff door with round handle', (2.85, -1.29, 1.22), (1.0, 0.08, 1.95), trim)
add_bevel(door, 0.035, 2)
handle = cyl('small brass door handle', (3.22, -1.36, 1.22), 0.055, 0.05, cream, vertices=20)
handle.rotation_euler[0] = math.radians(90)

sign = cube('cream sign board CAFE', (-1.15, -1.36, 2.95), (2.55, 0.08, 0.42), cream)
add_bevel(sign, 0.025, 2)
bpy.ops.object.text_add(location=(-1.92, -1.43, 2.89), rotation=(math.radians(90), 0, 0))
txt = bpy.context.object
txt.name = 'raised sign text: CONTAINER CAFE'
txt.data.body = 'CONTAINER CAFE'
txt.data.align_x = 'LEFT'
txt.data.align_y = 'CENTER'
txt.data.size = 0.26
txt.data.extrude = 0.015
txt.data.materials.append(trim)
mark(txt)

interior = cube('warm lit interior rectangle', (-1.15, -1.33, 1.65), (3.05, 0.05, 0.95), lightmat)

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


def _generic_reference_scene_script(description: str, reference_summary: str) -> str:
    title = _safe_text(description or reference_summary, "Reference Inspired Scene")
    return f"""
import bpy
import math

SCENE_TAG = 'ayeye_reference_scene'
for existing in list(bpy.data.objects):
    if existing.get('ayeye_generated_scene') == SCENE_TAG:
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
