# Builds the "cutting a glass strawberry" ASMR scene and saves it as a .blend.
# Run:  blender -b -P build_scene.py -- <output_dir>
# Then render with Blender (CLI or GUI). Writes events.json for the sound generator.
import bpy, bmesh, math, random, json, os, sys
from mathutils import Vector, Matrix, noise, kdtree

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.dirname(__file__))
FPS, DUR = 24, 8
FRAMES = FPS * DUR
random.seed(7)

# timeline (seconds)
T = dict(approach0=0.5, touch=2.4, enter=2.75, cutEnd=5.2, lift0=5.55, lift1=6.3, slide0=5.35, slide1=7.5)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, FRAMES
scene.render.fps = FPS


def clamp(x, a, b): return max(a, min(b, x))
def lerp(a, b, t): return a + (b - a) * t
def seg(t, a, b): return clamp((t - a) / (b - a), 0, 1)
def smooth(t): return t * t * (3 - 2 * t)
def ease_out(t): return 1 - (1 - t) ** 3
def ease_in(t): return t ** 3


# ---------------------------------------------------------------- materials
def principled(name, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    for k, v in inputs.items():
        b.inputs[k.replace('_', ' ')].default_value = v
    if hasattr(m, 'use_raytrace_refraction'):
        m.use_raytrace_refraction = True
    return m, b


def add_bump(m, bsdf, build):
    """build(nodes, links, coord_socket) -> height socket; wires a bump into Normal."""
    nt = m.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    bump = nt.nodes.new('ShaderNodeBump')
    nt.links.new(build(nt.nodes, nt.links, tc.outputs['Object']), bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return bump


DEEP_RED = (0.3, 0.0, 0.012, 1)
skin_mat, b = principled('GlassSkin', Base_Color=DEEP_RED, Roughness=0.04, IOR=1.5, Coat_Weight=1.0, Coat_Roughness=0.02)
def skin_ripple(n, l, co):   # faint hand-blown unevenness
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 18.0
    l.new(co, nz.inputs['Vector'])
    return nz.outputs['Fac']
add_bump(skin_mat, b, skin_ripple).inputs['Strength'].default_value = 0.04

seed_mat, _ = principled('GlassSeed', Base_Color=(1.0, 0.5, 0.0, 1), Roughness=0.04, IOR=1.5, Transmission_Weight=0.6,
                         Coat_Weight=1.0, Coat_Roughness=0.01)
rim_mat, _ = principled('GlassRim', Base_Color=(0.32, 0.0, 0.015, 1), Roughness=0.15, IOR=1.5, Coat_Weight=0.6)

# frosted icy interior: crystalline voronoi + fine noise bump, milky translucency
frost_mat, b = principled('FrostCore', Base_Color=(0.93, 0.93, 0.9, 1), Roughness=0.32, IOR=1.31, Transmission_Weight=0.3,
                          Coat_Weight=0.6, Coat_Roughness=0.08)
def frost_height(n, l, co):
    vor = n.new('ShaderNodeTexVoronoi'); vor.inputs['Scale'].default_value = 140.0
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 600.0; nz.inputs['Detail'].default_value = 8.0
    mix = n.new('ShaderNodeMath'); mix.operation = 'ADD'
    l.new(co, vor.inputs['Vector']); l.new(co, nz.inputs['Vector'])
    l.new(vor.outputs['Distance'], mix.inputs[0]); l.new(nz.outputs['Fac'], mix.inputs[1])
    return mix.outputs['Value']
add_bump(frost_mat, b, frost_height).inputs['Strength'].default_value = 0.35

leaf_mat, _ = principled('GlassLeaf', Base_Color=(0.06, 0.42, 0.08, 1), Roughness=0.05, IOR=1.5, Transmission_Weight=0.65,
                         Subsurface_Weight=0.2, Coat_Weight=1.0, Coat_Roughness=0.02)
chip_clear, _ = principled('ChipClear', Base_Color=(1, 1, 1, 1), Roughness=0.0, IOR=1.5, Transmission_Weight=1.0)
chip_gold, _ = principled('ChipGold', Base_Color=(1.0, 0.62, 0.05, 1), Roughness=0.02, IOR=1.5, Transmission_Weight=0.85)

steel_mat, b = principled('BrushedSteel', Base_Color=(0.9, 0.91, 0.92, 1), Metallic=1.0, Roughness=0.16, Anisotropic=0.5)
def brushed(n, l, co):
    mp = n.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (8.0, 2500.0, 2500.0)
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 6.0
    l.new(co, mp.inputs['Vector']); l.new(mp.outputs['Vector'], nz.inputs['Vector'])
    return nz.outputs['Fac']
add_bump(steel_mat, b, brushed).inputs['Strength'].default_value = 0.006
handle_mat, _ = principled('HandlePolymer', Base_Color=(0.02, 0.02, 0.022, 1), Roughness=0.3, Coat_Weight=0.5)

# oiled wooden board: wave-texture grain
wood_mat, b = principled('Wood', Roughness=0.45, Coat_Weight=0.25, Coat_Roughness=0.3)
nt = wood_mat.node_tree
tc = nt.nodes.new('ShaderNodeTexCoord')
mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1.0, 14.0, 1.0)
wave = nt.nodes.new('ShaderNodeTexWave'); wave.wave_type = 'BANDS'; wave.bands_direction = 'Y'
wave.inputs['Scale'].default_value = 3.0; wave.inputs['Distortion'].default_value = 16.0
wave.inputs['Detail'].default_value = 6.0; wave.inputs['Detail Scale'].default_value = 2.5
nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 25.0
ramp = nt.nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].color = (0.035, 0.014, 0.006, 1); ramp.color_ramp.elements[1].color = (0.13, 0.06, 0.025, 1)
mix = nt.nodes.new('ShaderNodeMath'); mix.operation = 'MULTIPLY_ADD'; mix.inputs[1].default_value = 0.6
bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.08
nt.links.new(tc.outputs['Object'], mp.inputs['Vector']); nt.links.new(mp.outputs['Vector'], wave.inputs['Vector'])
nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
nt.links.new(nz.outputs['Fac'], mix.inputs[0]); nt.links.new(wave.outputs['Fac'], mix.inputs[2])
nt.links.new(mix.outputs['Value'], ramp.inputs['Fac']); nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
nt.links.new(wave.outputs['Fac'], bump.inputs['Height']); nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])

backdrop_mat, _ = principled('Backdrop', Base_Color=(0.42, 0.41, 0.4, 1), Roughness=0.9)


def mesh_obj(name, bm, mats, parent=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    for m in mats: me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    if parent: ob.parent = parent
    return ob


# ---------------------------------------------------------------- strawberry (local units, ~2 long)
def shape(co):
    x, y, z = co
    t = (z + 1) / 2                      # 0 = tip, 1 = top
    k = 0.55 + 0.6 * t                   # cone: narrow tip, broad shoulders
    z = z * 1.25 if z < 0 else z * 0.78  # longer tip, flatter top
    x, y = x * k, y * k
    r = math.hypot(x, y)
    if z > 0: z -= 0.16 * math.exp(-(r / 0.32) ** 2)   # calyx dimple
    s = 1 + 0.035 * noise.noise(Vector((x * 1.6, y * 1.6, z * 1.6)))
    return Vector((x * s, y * s, z))

bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=384, v_segments=288, radius=1.0)
for v in bm.verts: v.co = shape(v.co)
bm.normal_update()

Z_CUT = -0.15
# seed pits, kept away from the tip, the calyx and the cut plane
cands = [v for v in bm.verts if -1.1 < v.co.z < 0.55 and abs(v.co.z - Z_CUT) > 0.07]
random.shuffle(cands)
seeds = []
for v in cands:
    if len(seeds) >= 230: break
    if any((v.co - p).length < 0.15 for p, _ in seeds): continue
    seeds.append((v.co.copy(), v.normal.copy()))
kd_v = kdtree.KDTree(len(bm.verts))
for i, v in enumerate(bm.verts): kd_v.insert(v.co, i)
kd_v.balance()
verts = list(bm.verts)
for p, n in seeds:
    for co, i, d in kd_v.find_range(p, 0.09):
        verts[i].co -= verts[i].normal * 0.032 * math.exp(-(d / 0.035) ** 2)
bm.normal_update()

# radial profile (for chip collisions and knife contact)
PROFILE = {}
for v in bm.verts:
    key = round(v.co.z, 2)
    PROFILE[key] = max(PROFILE.get(key, 0.0), math.hypot(v.co.x, v.co.y))
ZMIN, ZMAX = min(v.co.z for v in bm.verts), max(v.co.z for v in bm.verts)
def prof_r(z): return PROFILE.get(round(z, 2), 0.0)
R_CUT = prof_r(Z_CUT)


def make_half(keep_top):
    h = bm.copy()
    bmesh.ops.bisect_plane(h, geom=h.verts[:] + h.edges[:] + h.faces[:], plane_co=(0, 0, Z_CUT), plane_no=(0, 0, 1),
                           clear_inner=keep_top, clear_outer=not keep_top)
    boundary = [e for e in h.edges if e.is_boundary]
    for f in h.faces: f.smooth = True
    for e in boundary: e.smooth = False
    cap = bmesh.ops.contextual_create(h, geom=boundary)['faces']
    inset = bmesh.ops.inset_region(h, faces=cap, thickness=0.06, depth=0.0, use_even_offset=True)
    for f in inset['faces']: f.material_index = 1          # skin ring
    for f in cap: f.material_index = 2; f.smooth = False    # frosted core
    for f in inset['faces']: f.smooth = False
    return h

berry = bpy.data.objects.new('Berry', None)
scene.collection.objects.link(berry)
SCALE = 0.03
AXIS = Vector((0.62, 0.78, 0.0)).normalized()     # local +Z (toward calyx) points back-right
rot = AXIS.to_track_quat('Z', 'X').to_matrix().to_4x4()
berry.matrix_world = rot @ Matrix.Scale(SCALE, 4)
bpy.context.view_layer.update()
minz = min((berry.matrix_world @ v.co).z for v in bm.verts)
berry.location.z = -minz
bpy.context.view_layer.update()
BM = berry.matrix_world.copy()

# inside: raspberry-pink strawberry filling, ringed by a layer of golden yellow liquid that spills out
# the liquid that flows out matches the filling: raspberry-pink syrup with colour streaks,
# tiny pulp specks and a slightly uneven surface
PINK, PINK_DARK, PULP = (0.85, 0.03, 0.22, 1), (0.5, 0.0, 0.13, 1), (0.25, 0.0, 0.05, 1)
liquid_mat, b = principled('PinkLiquid', Roughness=0.02, IOR=1.47, Transmission_Weight=0.4,
                           Subsurface_Weight=0.3, Subsurface_Scale=0.002, Coat_Weight=0.9, Coat_Roughness=0.01)
nt = liquid_mat.node_tree; N_, L_ = nt.nodes, nt.links
tc = N_.new('ShaderNodeTexCoord')
streak = N_.new('ShaderNodeTexNoise'); streak.inputs['Scale'].default_value = 6.0; streak.inputs['Detail'].default_value = 4.0
streak.inputs['Distortion'].default_value = 2.0
L_.new(tc.outputs['Object'], streak.inputs['Vector'])
tone = N_.new('ShaderNodeValToRGB'); tone.color_ramp.elements[0].position = 0.35; tone.color_ramp.elements[0].color = PINK_DARK
tone.color_ramp.elements[1].position = 0.65; tone.color_ramp.elements[1].color = PINK
L_.new(streak.outputs['Fac'], tone.inputs['Fac'])
specks = N_.new('ShaderNodeTexVoronoi'); specks.inputs['Scale'].default_value = 40.0
L_.new(tc.outputs['Object'], specks.inputs['Vector'])
speck_mask = N_.new('ShaderNodeValToRGB')
speck_mask.color_ramp.elements[0].position = 0.06; speck_mask.color_ramp.elements[0].color = (1, 1, 1, 1)
speck_mask.color_ramp.elements[1].position = 0.1; speck_mask.color_ramp.elements[1].color = (0, 0, 0, 1)
L_.new(specks.outputs['Distance'], speck_mask.inputs['Fac'])
mix = N_.new('ShaderNodeMixRGB'); mix.inputs['Color2'].default_value = PULP
L_.new(speck_mask.outputs['Color'], mix.inputs['Fac']); L_.new(tone.outputs['Color'], mix.inputs['Color1'])
L_.new(mix.outputs['Color'], b.inputs['Base Color'])
L_.new(mix.outputs['Color'], b.inputs['Subsurface Radius'])
ripple = N_.new('ShaderNodeTexNoise'); ripple.inputs['Scale'].default_value = 22.0; ripple.inputs['Detail'].default_value = 6.0
L_.new(tc.outputs['Object'], ripple.inputs['Vector'])
hsum = N_.new('ShaderNodeMath'); hsum.operation = 'MULTIPLY_ADD'; hsum.inputs[1].default_value = 0.4
L_.new(speck_mask.outputs['Color'], hsum.inputs[0]); L_.new(ripple.outputs['Fac'], hsum.inputs[2])
bump = N_.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.045
L_.new(hsum.outputs['Value'], bump.inputs['Height']); L_.new(bump.outputs['Normal'], b.inputs['Normal'])

# cut face shader: radius from the section centre (object space) drives filling -> liquid layers
face_mat, b = principled('FillingFace', IOR=1.47, Coat_Weight=0.4, Coat_Roughness=0.08)
nt = face_mat.node_tree; N_, L_ = nt.nodes, nt.links
tc = N_.new('ShaderNodeTexCoord')
sep = N_.new('ShaderNodeSeparateXYZ'); L_.new(tc.outputs['Object'], sep.inputs[0])
flat = N_.new('ShaderNodeCombineXYZ'); L_.new(sep.outputs['X'], flat.inputs['X']); L_.new(sep.outputs['Y'], flat.inputs['Y'])
ln = N_.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; L_.new(flat.outputs[0], ln.inputs[0])
rad = N_.new('ShaderNodeMath'); rad.operation = 'DIVIDE'; rad.inputs[1].default_value = R_CUT
L_.new(ln.outputs['Value'], rad.inputs[0])
wob = N_.new('ShaderNodeTexNoise'); wob.inputs['Scale'].default_value = 3.0   # organic, not perfectly round
L_.new(tc.outputs['Object'], wob.inputs['Vector'])
r_in = N_.new('ShaderNodeMath'); r_in.operation = 'MULTIPLY_ADD'; r_in.inputs[1].default_value = 0.12
L_.new(wob.outputs['Fac'], r_in.inputs[0]); L_.new(rad.outputs['Value'], r_in.inputs[2])
def ramp(stops):
    r = N_.new('ShaderNodeValToRGB'); els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0]; els[1].position, els[1].color = stops[-1]
    for pos, col in stops[1:-1]:
        e = els.new(pos); e.color = col
    L_.new(r_in.outputs['Value'], r.inputs['Fac'])
    return r
colour = ramp([(0.0, (0.85, 0.42, 0.52, 1)), (0.16, (0.9, 0.36, 0.5, 1)), (0.27, (0.9, 0.02, 0.2, 1)),
               (0.6, (0.5, 0.0, 0.17, 1)), (0.68, (0.42, 0.0, 0.11, 1)), (0.72, PINK), (1.0, (0.78, 0.02, 0.2, 1))])
liquid_mask = ramp([(0.0, (0, 0, 0, 1)), (0.68, (0, 0, 0, 1)), (0.73, (1, 1, 1, 1)), (1.0, (1, 1, 1, 1))])
fill_mask = ramp([(0.0, (0, 0, 0, 1)), (0.22, (0, 0, 0, 1)), (0.3, (1, 1, 1, 1)), (0.62, (1, 1, 1, 1)), (0.68, (0, 0, 0, 1)), (1.0, (0, 0, 0, 1))])
# fine radial streaks through the filling, like a real strawberry slice
ang = N_.new('ShaderNodeTexGradient'); ang.gradient_type = 'RADIAL'; L_.new(flat.outputs[0], ang.inputs['Vector'])
st = N_.new('ShaderNodeMath'); st.operation = 'MULTIPLY'; st.inputs[1].default_value = 2 * math.pi * 34
L_.new(ang.outputs['Fac'], st.inputs[0])
sn = N_.new('ShaderNodeMath'); sn.operation = 'SINE'; L_.new(st.outputs['Value'], sn.inputs[0])
sm = N_.new('ShaderNodeMath'); sm.operation = 'MULTIPLY'; L_.new(sn.outputs['Value'], sm.inputs[0]); L_.new(fill_mask.outputs['Color'], sm.inputs[1])
sw = N_.new('ShaderNodeMath'); sw.operation = 'MULTIPLY'; sw.inputs[1].default_value = 0.2   # subtle
L_.new(sm.outputs['Value'], sw.inputs[0]); sm = sw
mixs = N_.new('ShaderNodeMixRGB'); mixs.inputs['Color2'].default_value = (1.0, 0.42, 0.62, 1)
L_.new(sm.outputs['Value'], mixs.inputs['Fac']); L_.new(colour.outputs['Color'], mixs.inputs['Color1'])
L_.new(mixs.outputs['Color'], b.inputs['Base Color'])
for src, dst, scale in ((liquid_mask, 'Transmission Weight', 0.5),):
    m = N_.new('ShaderNodeMath'); m.operation = 'MULTIPLY'; m.inputs[1].default_value = scale
    L_.new(src.outputs['Color'], m.inputs[0]); L_.new(m.outputs['Value'], b.inputs[dst])
rough = N_.new('ShaderNodeMath'); rough.operation = 'MULTIPLY_ADD'; rough.inputs[1].default_value = -0.16; rough.inputs[2].default_value = 0.17
L_.new(liquid_mask.outputs['Color'], rough.inputs[0]); L_.new(rough.outputs['Value'], b.inputs['Roughness'])
def jam_texture(n, l, co):   # glossy, slightly uneven jam surface
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 60.0; nz.inputs['Detail'].default_value = 3.0
    l.new(co, nz.inputs['Vector'])
    return nz.outputs['Fac']
add_bump(face_mat, b, jam_texture).inputs['Strength'].default_value = 0.08
# the cut face is seared by the hot blade: it glows briefly when the halves part, then cools
b.inputs['Emission Color'].default_value = (1.0, 0.28, 0.04, 1)
sear = b.inputs['Emission Strength']
for t_k, v in ((0.0, 0.0), (T['slide0'], 0.0), (T['slide0'] + 0.15, 2.2), (T['slide0'] + 1.7, 0.0)):
    sear.default_value = v; sear.keyframe_insert('default_value', frame=int(t_k * FPS) + 1)
top_half = mesh_obj('BerryTop', make_half(True), [skin_mat, rim_mat, face_mat], berry)
tip_half = mesh_obj('BerryTip', make_half(False), [skin_mat, rim_mat, face_mat], berry)

# seeds as small glossy ellipsoids sitting in the pits, split by side of the cut
for name, side, parent in (('SeedsTop', 1, top_half), ('SeedsTip', -1, tip_half)):
    sb = bmesh.new()
    for p, n in seeds:
        if (p.z - Z_CUT) * side <= 0: continue
        tang = (Vector((0, 0, 1)) - n * n.z).normalized()
        m = Matrix((tang.cross(n), tang, n)).transposed().to_4x4()
        m.translation = p - n * 0.012
        g = bmesh.ops.create_uvsphere(sb, u_segments=10, v_segments=7, radius=1.0)
        bmesh.ops.transform(sb, matrix=m @ Matrix.Diagonal((0.022, 0.042, 0.016, 1)), verts=g['verts'])
    for f in sb.faces: f.smooth = True
    mesh_obj(name, sb, [seed_mat], parent)

# calyx: glass sepals draped over the shoulders, plus a stem
def surf_top(rr):
    r0 = rr / 1.12
    return 0.78 * math.sqrt(max(0.0, 1 - r0 * r0)) - 0.16 * math.exp(-(rr / 0.32) ** 2)
lb = bmesh.new()
NS = 9
for i in range(NS):
    phi = i / NS * 2 * math.pi + random.uniform(-0.15, 0.15)
    length = random.uniform(0.85, 1.05)
    rows = []
    for a in range(13):
        l = a / 12
        rr = 0.1 + length * l
        z = max(surf_top(rr), 0.2 - 0.6 * (rr - 1.0)) + 0.03 + 0.05 * math.sin(math.pi * l) + 0.12 * l ** 3
        w = 0.17 * math.sin(math.pi * min(l * 1.1, 1)) ** 0.7 + 0.01
        c = Vector((math.cos(phi) * rr, math.sin(phi) * rr, z))
        side = Vector((-math.sin(phi), math.cos(phi), 0))
        rows.append([lb.verts.new(c + side * w * (b / 2 - 1)) for b in range(5)])
    for a in range(12):
        for b in range(4):
            lb.faces.new((rows[a][b], rows[a][b + 1], rows[a + 1][b + 1], rows[a + 1][b]))
for f in lb.faces: f.smooth = True
leaves = mesh_obj('Sepals', lb, [leaf_mat], top_half)
sol = leaves.modifiers.new('thick', 'SOLIDIFY'); sol.thickness = 0.03
leaves.modifiers.new('smooth', 'SUBSURF').levels = 2
stem_curve = bpy.data.curves.new('Stem', 'CURVE'); stem_curve.dimensions = '3D'
stem_curve.bevel_depth = 0.04; stem_curve.bevel_resolution = 4
sp = stem_curve.splines.new('BEZIER'); sp.bezier_points.add(2)
for bp, co in zip(sp.bezier_points, [(0, 0, 0.6), (0.03, 0.0, 0.85), (0.12, 0.03, 1.02)]):
    bp.co = co; bp.handle_left_type = bp.handle_right_type = 'AUTO'
stem = bpy.data.objects.new('Stem', stem_curve); stem_curve.materials.append(leaf_mat)
scene.collection.objects.link(stem); stem.parent = top_half

# ---------------------------------------------------------------- board, backdrop
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.05, -0.015))
board = bpy.context.object; board.scale = (0.9, 0.7, 0.03); board.data.materials.append(wood_mat)
bev = board.modifiers.new('bevel', 'BEVEL'); bev.width = 0.004; bev.segments = 3
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0.75, 0.4), rotation=(math.radians(90), 0, 0))
back = bpy.context.object; back.scale = (3, 1.2, 1); back.data.materials.append(backdrop_mat)

# ---------------------------------------------------------------- knife (local: edge along X, height Z, thickness Y)
kb = bmesh.new()
outline = [(0.08, 0.0), (-0.05, 0.0)]
for i in range(1, 11):
    a = i / 10; outline.append((lerp(-0.05, -0.125, a), 0.032 * a ** 1.8))
for i in range(1, 9):
    a = i / 8; outline.append((lerp(-0.125, -0.03, a), lerp(0.032, 0.046, math.sin(a * math.pi / 2))))
outline.append((0.08, 0.046))
face = kb.faces.new([kb.verts.new((x, 0, z)) for x, z in outline])
ext = bmesh.ops.extrude_face_region(kb, geom=[face])
ev = [g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)]
bmesh.ops.translate(kb, verts=ev, vec=(0, 0.0018, 0))
for v in kb.verts:   # flat grind: thin at the edge, full thickness at the spine
    v.co.y = (v.co.y - 0.0009) * (0.06 + 0.94 * clamp(v.co.z / 0.03, 0, 1))
bmesh.ops.recalc_face_normals(kb, faces=kb.faces[:])
knife = bpy.data.objects.new('Knife', None); scene.collection.objects.link(knife)
# red-hot blade: white-yellow at the edge cooling through orange and red into scorched steel,
# with flickering lava veins. Edge height (object Z: 0 at the edge, 0.046 at the spine) drives the heat.
hot_mat, b = principled('LavaBlade', Base_Color=(0.05, 0.04, 0.035, 1), Metallic=0.85, Roughness=0.35)
b.inputs['Emission Color'].default_value = (1, 1, 1, 1)
nt = hot_mat.node_tree; N_, L_ = nt.nodes, nt.links
tc = N_.new('ShaderNodeTexCoord')
sep = N_.new('ShaderNodeSeparateXYZ'); L_.new(tc.outputs['Object'], sep.inputs[0])
edge_heat = N_.new('ShaderNodeMapRange'); edge_heat.inputs['From Min'].default_value = 0.034; edge_heat.inputs['From Max'].default_value = 0.0
L_.new(sep.outputs['Z'], edge_heat.inputs['Value'])
veins = N_.new('ShaderNodeTexVoronoi'); veins.feature = 'DISTANCE_TO_EDGE'; veins.voronoi_dimensions = '4D'
veins.inputs['Scale'].default_value = 260.0
flicker = N_.new('ShaderNodeTexNoise'); flicker.noise_dimensions = '4D'; flicker.inputs['Scale'].default_value = 120.0
for tex in (veins, flicker):
    L_.new(tc.outputs['Object'], tex.inputs['Vector'])
    w = tex.inputs['W']; w.default_value = 0.0; w.keyframe_insert('default_value', frame=1)
    w.default_value = DUR * 0.6; w.keyframe_insert('default_value', frame=FRAMES)
vein_line = N_.new('ShaderNodeMapRange'); vein_line.inputs['From Min'].default_value = 0.06; vein_line.inputs['From Max'].default_value = 0.0
L_.new(veins.outputs['Distance'], vein_line.inputs['Value'])
vein_heat = N_.new('ShaderNodeMapRange'); vein_heat.inputs['From Min'].default_value = 0.036; vein_heat.inputs['From Max'].default_value = 0.008
L_.new(sep.outputs['Z'], vein_heat.inputs['Value'])
vein_amt = N_.new('ShaderNodeMath'); vein_amt.operation = 'MULTIPLY'
L_.new(vein_line.outputs['Result'], vein_amt.inputs[0]); L_.new(vein_heat.outputs['Result'], vein_amt.inputs[1])
heat = N_.new('ShaderNodeMath'); heat.operation = 'MULTIPLY_ADD'; heat.inputs[1].default_value = 0.55
L_.new(vein_amt.outputs['Value'], heat.inputs[0]); L_.new(edge_heat.outputs['Result'], heat.inputs[2])
fl = N_.new('ShaderNodeMath'); fl.operation = 'MULTIPLY_ADD'; fl.inputs[1].default_value = 0.25
L_.new(flicker.outputs['Fac'], fl.inputs[0]); L_.new(heat.outputs['Value'], fl.inputs[2])
heat_c = N_.new('ShaderNodeMath'); heat_c.operation = 'MINIMUM'; heat_c.inputs[1].default_value = 1.0
L_.new(fl.outputs['Value'], heat_c.inputs[0])
lava = N_.new('ShaderNodeValToRGB'); els = lava.color_ramp.elements
els[0].position, els[0].color = 0.12, (0, 0, 0, 1); els[1].position, els[1].color = 1.0, (1.0, 0.95, 0.6, 1)
for pos, col in ((0.3, (0.45, 0.02, 0.0, 1)), (0.55, (1.0, 0.18, 0.0, 1)), (0.8, (1.0, 0.6, 0.08, 1))):
    e = els.new(pos); e.color = col
L_.new(heat_c.outputs['Value'], lava.inputs['Fac'])
L_.new(lava.outputs['Color'], b.inputs['Emission Color'])
sq = N_.new('ShaderNodeMath'); sq.operation = 'POWER'; sq.inputs[1].default_value = 2.0
L_.new(heat_c.outputs['Value'], sq.inputs[0])
strength = N_.new('ShaderNodeMath'); strength.operation = 'MULTIPLY'; strength.inputs[1].default_value = 9.0
L_.new(sq.outputs['Value'], strength.inputs[0]); L_.new(strength.outputs['Value'], b.inputs['Emission Strength'])
blade = mesh_obj('Blade', kb, [hot_mat], knife)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.145, 0, 0.022))
handle = bpy.context.object; handle.scale = (0.13, 0.016, 0.03); handle.data.materials.append(handle_mat); handle.parent = knife
hb = handle.modifiers.new('bevel', 'BEVEL'); hb.width = 0.006; hb.segments = 4
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.082, 0, 0.024))
bolster = bpy.context.object; bolster.scale = (0.006, 0.012, 0.044); bolster.data.materials.append(steel_mat); bolster.parent = knife
for x in (0.11, 0.145, 0.18):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.003, depth=0.018, location=(x, 0, 0.022), rotation=(math.radians(90), 0, 0))
    rv = bpy.context.object; rv.data.materials.append(steel_mat); rv.parent = knife

# knife frame: blade plane perpendicular to the strawberry axis
KY = Vector((AXIS.x, AXIS.y, 0)).normalized(); KZ = Vector((0, 0, 1)); KX = KY.cross(KZ)
KROT = Matrix((KX, KY, KZ)).transposed().to_4x4()
C = BM @ Vector((0, 0, Z_CUT))        # centre of the cut section (world)
RC = R_CUT * SCALE                     # section radius (world)
TOP = C.z + RC

# one smooth, unbroken glide from the top of the strawberry to the board
def cut_depth(u):
    return -(math.cos(math.pi * clamp(u, 0, 1)) - 1) / 2

def knife_state(t):
    high = TOP + 0.12
    pull = 0.0
    if t < T['approach0']: h = high
    elif t < T['touch']: h = lerp(high, TOP + 0.0005, ease_out(seg(t, T['approach0'], T['touch'])))
    elif t < T['cutEnd']:
        u = seg(t, T['touch'], T['cutEnd'])
        h = lerp(TOP, 0.0, cut_depth(u)); pull = lerp(0.02, -0.02, smooth(u))
    elif t < T['lift0']: h, pull = 0.0, -0.02
    else: h, pull = lerp(0.0, high + 0.05, ease_in(seg(t, T['lift0'], T['lift1']))), -0.02
    return h, pull

def knife_matrix(t):
    h, pull = knife_state(t)
    m = KROT.copy()
    m.translation = Vector((C.x, C.y, 0)) + KX * (0.005 + pull) + Vector((0, 0, h))
    return m

# ---------------------------------------------------------------- animation
CENT_TIP = sum((v.co for v in tip_half.data.vertices), Vector()) / len(tip_half.data.vertices)
tip_samples = [v.co.copy() for i, v in enumerate(tip_half.data.vertices) if i % 25 == 0]
LOW0 = min((BM @ v).z for v in tip_samples)
def tip_matrix(t):
    # stays exactly where the intact berry was until the cut is through, then rolls away to the left (not toward the camera)
    slide = smooth(seg(t, T['slide0'], T['slide1']))   # slow, so the liquid strands stretch
    world_off = -AXIS * 0.008 * slide - KX * 0.03 * slide
    off = BM.inverted().to_3x3() @ world_off
    r = Matrix.Rotation(-math.radians(25) * slide, 4, 'Z') @ Matrix.Rotation(math.radians(12 * slide), 4, 'X')
    m = Matrix.Translation(CENT_TIP + off) @ r @ Matrix.Translation(-CENT_TIP)
    low = min((BM @ m @ v).z for v in tip_samples)            # keep it resting on the board
    m = Matrix.Translation(BM.inverted().to_3x3() @ Vector((0, 0, LOW0 - low))) @ m
    return m

cam_data = bpy.data.cameras.new('Cam'); cam = bpy.data.objects.new('Cam', cam_data); scene.collection.objects.link(cam)
scene.camera = cam
cam_data.lens = 85; cam_data.sensor_width = 36
focus = bpy.data.objects.new('Focus', None); scene.collection.objects.link(focus)
focus.location = C + Vector((0, 0, -RC * 0.15))
cam_data.dof.use_dof = True; cam_data.dof.focus_object = focus; cam_data.dof.aperture_fstop = 18
def cam_matrix(t):
    rev = smooth(seg(t, 5.4, 8.0))
    d = lerp(0.32, 0.29, smooth(t / DUR)) - 0.015 * rev
    el, az = math.radians(lerp(14, 21, rev)), math.radians(lerp(6, -4, t / DUR) - 6 * rev)
    target = C + Vector((0, 0, lerp(0.004, -0.004, rev)))
    pos = target + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * d
    m = (target - pos).to_track_quat('-Z', 'Y').to_matrix().to_4x4(); m.translation = pos
    return m

# an intact strawberry stands in until the blade reaches the board, so no seam shows before the cut is through
whole = mesh_obj('BerryWhole', bm.copy(), [skin_mat], berry)
for p in whole.data.polygons: p.use_smooth = True
wsb = bmesh.new()
for p, n in seeds:
    tang = (Vector((0, 0, 1)) - n * n.z).normalized()
    m = Matrix((tang.cross(n), tang, n)).transposed().to_4x4(); m.translation = p - n * 0.012
    g = bmesh.ops.create_uvsphere(wsb, u_segments=10, v_segments=7, radius=1.0)
    bmesh.ops.transform(wsb, matrix=m @ Matrix.Diagonal((0.022, 0.042, 0.016, 1)), verts=g['verts'])
for fc in wsb.faces: fc.smooth = True
whole_seeds = mesh_obj('SeedsWhole', wsb, [seed_mat], berry)
F_ENTER = int(T['cutEnd'] * FPS) + 1
for ob, visible_before in ((whole, True), (whole_seeds, True), (top_half, False), (tip_half, False),
                           (bpy.data.objects['SeedsTop'], False), (bpy.data.objects['SeedsTip'], False)):
    ob.hide_render = not visible_before; ob.keyframe_insert('hide_render', frame=1)
    ob.hide_render = visible_before; ob.keyframe_insert('hide_render', frame=F_ENTER)

for f in range(1, FRAMES + 1):
    t = (f - 1) / FPS
    for ob, m in ((knife, knife_matrix(t)), (cam, cam_matrix(t))):
        ob.matrix_world = m
        ob.keyframe_insert('location', frame=f); ob.keyframe_insert('rotation_euler', frame=f)
    tip_half.matrix_basis = tip_matrix(t)
    tip_half.keyframe_insert('location', frame=f); tip_half.keyframe_insert('rotation_euler', frame=f)

# ---------------------------------------------------------------- the hot blade burns the skin along the cut line
# glowing, charred band around the cut plane (berry-local Z), only where the edge has already passed (world height)
nt = skin_mat.node_tree; N_, L_ = nt.nodes, nt.links; sb = N_['Principled BSDF']
tc = N_.new('ShaderNodeTexCoord'); geo = N_.new('ShaderNodeNewGeometry')
def node_math(op, a, b_=None):
    m = N_.new('ShaderNodeMath'); m.operation = op
    for i, src in enumerate((a, b_)):
        if src is None: continue
        if isinstance(src, float): m.inputs[i].default_value = src
        else: L_.new(src, m.inputs[i])
    return m.outputs['Value']
def map_range(src, lo, hi):
    m = N_.new('ShaderNodeMapRange'); m.inputs['From Min'].default_value = lo; m.inputs['From Max'].default_value = hi
    L_.new(src, m.inputs['Value']); return m.outputs['Result']
local = N_.new('ShaderNodeSeparateXYZ'); L_.new(tc.outputs['Object'], local.inputs[0])
world = N_.new('ShaderNodeSeparateXYZ'); L_.new(geo.outputs['Position'], world.inputs[0])
band = map_range(node_math('ABSOLUTE', node_math('SUBTRACT', local.outputs['Z'], Z_CUT)), 0.13, 0.0)
lowest = N_.new('ShaderNodeValue').outputs[0]            # lowest height the edge has reached so far
burn_glow = N_.new('ShaderNodeValue').outputs[0]
burn_char = N_.new('ShaderNodeValue').outputs[0]
for f in range(1, FRAMES + 1):
    t = (f - 1) / FPS
    lowest.default_value = knife_state(min(t, T['cutEnd']))[0] if t >= T['touch'] else 1.0
    lowest.keyframe_insert('default_value', frame=f)
for out, keys in ((burn_glow, ((0, 0), (T['touch'], 0), (T['touch'] + 0.12, 5.0), (T['touch'] + 0.6, 3.0), (T['cutEnd'], 3.0),
                               (T['lift1'], 1.2), (DUR, 0.3))),
                  (burn_char, ((0, 0), (T['touch'], 0), (T['cutEnd'], 0.75), (DUR, 0.8)))):
    for t_k, v in keys:
        out.default_value = v; out.keyframe_insert('default_value', frame=int(t_k * FPS) + 1)
passed = map_range(node_math('SUBTRACT', world.outputs['Z'], lowest), -0.001, 0.002)
rough_edge = N_.new('ShaderNodeTexNoise'); rough_edge.inputs['Scale'].default_value = 40.0
L_.new(tc.outputs['Object'], rough_edge.inputs['Vector'])
irregular = node_math('ADD', node_math('MULTIPLY', rough_edge.outputs['Fac'], 0.8), 0.4)
mask = node_math('MULTIPLY', node_math('MULTIPLY', band, passed), irregular)
char = N_.new('ShaderNodeMixRGB'); char.inputs['Color1'].default_value = DEEP_RED; char.inputs['Color2'].default_value = (0.03, 0.008, 0.004, 1)
L_.new(node_math('MINIMUM', node_math('MULTIPLY', mask, burn_char), 1.0), char.inputs['Fac'])
L_.new(char.outputs['Color'], sb.inputs['Base Color'])
ember = N_.new('ShaderNodeValToRGB'); els = ember.color_ramp.elements
els[0].color = (0.5, 0.03, 0.0, 1); els[1].color = (1.0, 0.55, 0.08, 1)
L_.new(mask, ember.inputs['Fac'])
L_.new(ember.outputs['Color'], sb.inputs['Emission Color'])
L_.new(node_math('MULTIPLY', node_math('POWER', mask, 2.0), burn_glow), sb.inputs['Emission Strength'])

# ---------------------------------------------------------------- thick liquid (metaballs): beads, ooze, strands, drips, puddle
# Blender clamps metaball resolution to >= 5 mm, so the liquid is built 20x larger and the object scaled down
LS = 0.05
liquid_mb = bpy.data.metaballs.new('Liquid')
liquid_mb.resolution = 0.02; liquid_mb.render_resolution = 0.005; liquid_mb.threshold = 0.6
liquid_mb.materials.append(liquid_mat)
liquid = bpy.data.objects.new('Liquid', liquid_mb); scene.collection.objects.link(liquid)
liquid.scale = (LS, LS, LS)
VIS = 0.58                 # visible radius / element radius at this threshold
GRAV = 9.81
BM_INV = BM.inverted()
OUT_N = -AXIS              # the top half's cut face looks this way
FACE_ROT = AXIS.to_track_quat('Z', 'Y')
HIDDEN = (Vector((0, 0, -1)), 1e-6, None)
UP = Vector((0, 0, 1))

def face_pt(u, v): return C + KX * u + UP * v
def tip_pt(u, v, t): return BM @ tip_matrix(t) @ (BM_INV @ face_pt(u, v))
def edge_h(t): return knife_state(t)[0]

elems = []                 # (metaball element, fn(t) -> (co, radius, size or None))
def add_elem(fn, kind='BALL', rot=None):
    el = liquid_mb.elements.new(type=kind)
    if rot is not None: el.rotation = rot
    elems.append((el, fn))
liquid_events = []

# 1) liquid squeezes out where the blade meets the skin, riding down with the edge on both sides
for side in (-1, 1):
    def bead(t, side=side):
        if t < T['touch'] + 0.1: return HIDDEN
        h = edge_h(min(t, T['cutEnd']))
        w = math.sqrt(max(RC * RC - (h - C.z) ** 2, 0.0))
        grow = smooth(seg(t, T['touch'] + 0.1, T['touch'] + 0.6))
        p = Vector((C.x, C.y, max(h, 0.0012))) + KX * side * (w + 0.0006)
        if t > T['slide0']: return HIDDEN if t > T['slide0'] + 0.4 else (p, 0.0022 / VIS * (1 - seg(t, T['slide0'], T['slide0'] + 0.4)), None)
        return (p, 0.0022 / VIS * grow, None)
    add_elem(bead)

# 2) the golden layer between filling and skin wells up around the ring once the halves part;
#    the lower part carries more liquid and slowly slides down
RING = 0.82
def ring_pt(a, rr=RING): return face_pt(math.cos(a) * rr * RC, math.sin(a) * rr * RC)
for i in range(24):
    a = i / 24 * 2 * math.pi
    def film(t, a=a, d=random.uniform(0, 0.3)):
        e = smooth(seg(t, T['slide0'] + d, T['slide0'] + d + 0.8))
        if e <= 0: return HIDDEN
        low = 0.5 - 0.5 * math.sin(a)                  # 1 at the bottom of the ring, 0 at the top
        sag = (0.0008 + 0.006 * low) * e + 0.002 * low * max(0.0, t - T['slide0'] - 1.0)   # melted: runs further
        return (ring_pt(a) - UP * sag + OUT_N * 0.001 * e, (0.0045 + 0.004 * low) * e, (1.3, 1.3, 0.35))
    add_elem(film, 'ELLIPSOID', FACE_ROT)

# 3) one smooth, continuous spill from the bottom of the ring down onto the board
for i in range(22):
    ts, a = T['slide0'] + 0.25 + i * 0.08, -math.pi / 2 + random.uniform(-0.4, 0.4)
    def spill(t, ts=ts, a=a):
        tau = t - ts
        if tau < 0: return HIDDEN
        r = 0.0068 * smooth(seg(tau, 0, 0.2))
        start = ring_pt(a) + OUT_N * 0.0015
        z = start.z - (0.014 * tau + 0.022 * tau * tau)
        ground = 0.0015
        landed = smooth(seg(ground + 0.003 - z, 0, 0.003))
        p = Vector((start.x, start.y, max(z, ground))) + OUT_N * 0.004 * landed * min(tau, 2.5)
        return (p, r, (1 + 0.6 * landed, 1 + 0.6 * landed, lerp(1, 0.3, landed)))
    add_elem(spill, 'ELLIPSOID')

# 4) the golden puddle spreading smoothly in front of the cut face
for i in range(5):
    off = OUT_N * (0.005 + i * 0.006) + KX * random.uniform(-0.5, 0.5) * RC
    t0 = T['slide0'] + 0.5 + i * 0.25
    def pool(t, off=off, t0=t0):
        g = smooth(seg(t, t0, DUR))
        if g <= 0: return HIDDEN
        return (Vector((C.x, C.y, 0.0005)) + off, 0.017 * g ** 0.7, (1.8, 1.8, 0.2))
    add_elem(pool, 'ELLIPSOID')

# 5) strands between the two halves: stretch, thin out, snap, drip
def strand_set(name, ends, formed, r0, Lb, nb=14):
    """ends(t) -> (A, B) in world space. Adds the balls plus one drip; records when it snaps."""
    tb = None
    for k in range(int(DUR * 240)):
        t = k / 240
        if formed(t):
            A, B = ends(t)
            if (B - A).length > Lb: tb = t; break
    drop = None
    if tb is not None:
        A, B = ends(tb)
        M = (A + B) / 2 - UP * 12 * (B - A).length ** 2
        land = tb + math.sqrt(max(2 * (M.z - 0.0015), 0) / GRAV)
        drop = (tb, M, land)
        liquid_events.append(dict(kind='snap', t=tb, size=r0))
        liquid_events.append(dict(kind='drip', t=land, size=r0))
    def thin(L): return clamp(math.sqrt(0.004 / (L + 0.004)), 0.45, 1)
    for k in range(nb):
        s = k / (nb - 1)
        def ball(t, s=s):
            if not formed(t): return HIDDEN
            fade = 1.0 if tb is None or t < tb else 1 - seg(t, tb, tb + 0.12)
            if fade <= 0: return HIDDEN
            A, B = ends(min(t, tb) if tb is not None else t)
            L = (B - A).length
            if L < 0.0004: return HIDDEN
            p = A.lerp(B, s) - UP * 12 * L * L * 4 * s * (1 - s)
            return (p, r0 / VIS * (0.5 + 0.5 * (2 * s - 1) ** 2) * thin(L) * fade, None)
        add_elem(ball)
    if drop:
        def drip(t, drop=drop):
            tb, M, land = drop
            if t < tb: return HIDDEN
            z = max(M.z - 0.5 * GRAV * (t - tb) ** 2, 0.0015)
            shrink = 1 - seg(t, land, land + 0.4)
            if shrink <= 0: return HIDDEN
            return (Vector((M.x, M.y, z)), r0 / VIS * 1.3 * shrink, None)
        add_elem(drip)

for deg_a in (35, 150, 205, 250, 295, 330):   # strands come from the golden liquid layer
    a = math.radians(deg_a)
    u, v = math.cos(a) * RING * RC, math.sin(a) * RING * RC
    strand_set(f'face{u:.3f}',
               lambda t, u=u, v=v: (face_pt(u, v) + OUT_N * 0.0005, tip_pt(u, v, t) + AXIS * 0.0005),
               lambda t, v=v: t > T['touch'] and edge_h(t if t < T['cutEnd'] else T['cutEnd']) < C.z + v,
               random.uniform(0.0012, 0.002), random.uniform(0.008, 0.026))

# a strand off the knife edge as it lifts, plus beads riding on the edge
strand_set('knife', lambda t: (Vector((C.x, C.y, edge_h(t))), face_pt(0, -0.8 * RC) + OUT_N * 0.0008),
           lambda t: t >= T['lift0'], 0.0018, 0.03, nb=16)
for dx in (-0.6, -0.1, 0.45):
    def edge_bead(t, dx=dx * RC):
        if t < T['cutEnd'] - 0.3: return HIDDEN
        h = edge_h(t)
        return (Vector((C.x, C.y, h - 0.0008)) + KX * dx, 0.0016 / VIS * smooth(seg(t, T['cutEnd'] - 0.3, T['cutEnd'])), None)
    add_elem(edge_bead)

for f in range(1, FRAMES + 1):
    t = (f - 1) / FPS
    for el, fn in elems:
        co, rad, size = fn(t)
        el.co, el.radius = co / LS, rad / LS
        el.keyframe_insert('co', frame=f); el.keyframe_insert('radius', frame=f)
        if size is not None:
            el.size_x, el.size_y, el.size_z = size
            for a in ('size_x', 'size_y', 'size_z'): el.keyframe_insert(a, frame=f)
for fc in liquid_mb.animation_data.action.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'

for ob in (knife, cam, tip_half):
    for fc in ob.animation_data.action.fcurves:
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'

# ---------------------------------------------------------------- lights + world
def area(name, loc, size, power, color=(1, 1, 1), size_y=None):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.color = color
    ld.shape = 'RECTANGLE'; ld.size = size; ld.size_y = size_y or size
    ob = bpy.data.objects.new(name, ld); scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (C - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob
area('Key', (-0.3, -0.22, 0.42), 0.45, 9, (1, 0.97, 0.93), 0.22)
area('Top', (0.02, 0.05, 0.5), 0.5, 6, (1, 1, 1), 0.18)
area('Rim', (0.32, 0.35, 0.16), 0.08, 5, (1, 0.95, 0.88), 0.45)
area('Fill', (0.15, -0.55, 0.12), 0.4, 1.5, (0.95, 0.97, 1), 0.3)
area('BladeCard', (-0.35, -0.2, 0.22), 0.5, 0.9, (1, 1, 1), 0.35)   # what the steel reflects into the lens

world = bpy.data.worlds.new('World'); scene.world = world; world.use_nodes = True
wn = world.node_tree.nodes; env = wn.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load(os.path.join(os.path.dirname(bpy.app.binary_path), '4.2', 'datafiles', 'studiolights', 'world', 'studio.exr'))
world.node_tree.links.new(env.outputs['Color'], wn['Background'].inputs['Color'])
wn['Background'].inputs['Strength'].default_value = 0.2

# ---------------------------------------------------------------- steam rising where the hot blade meets the filling
bpy.ops.mesh.primitive_cube_add(size=1, location=(C.x, C.y, 0.065))
steam = bpy.context.object; steam.name = 'Steam'; steam.scale = (0.12, 0.12, 0.13)
steam_mat = bpy.data.materials.new('Steam'); steam_mat.use_nodes = True
nt = steam_mat.node_tree; N_, L_ = nt.nodes, nt.links
N_.remove(N_['Principled BSDF'])
vol = N_.new('ShaderNodeVolumePrincipled'); vol.inputs['Color'].default_value = (0.95, 0.95, 0.95, 1)
L_.new(vol.outputs['Volume'], N_['Material Output'].inputs['Volume'])
tc = N_.new('ShaderNodeTexCoord')
mp = N_.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (3, 3, 2)
L_.new(tc.outputs['Generated'], mp.inputs['Vector'])
loc = mp.inputs['Location']                     # scrolling the noise makes the wisps rise
loc.default_value = (0, 0, 0); loc.keyframe_insert('default_value', frame=1)
loc.default_value = (0, 0, -DUR * 0.5); loc.keyframe_insert('default_value', frame=FRAMES)
wisp = N_.new('ShaderNodeTexNoise'); wisp.noise_dimensions = '4D'
wisp.inputs['Scale'].default_value = 2.5; wisp.inputs['Detail'].default_value = 6.0
w = wisp.inputs['W']; w.default_value = 0.0; w.keyframe_insert('default_value', frame=1)
w.default_value = 3.0; w.keyframe_insert('default_value', frame=FRAMES)
L_.new(mp.outputs['Vector'], wisp.inputs['Vector'])
gen = N_.new('ShaderNodeSeparateXYZ'); L_.new(tc.outputs['Generated'], gen.inputs[0])
def maprange(src, lo, hi):
    m = N_.new('ShaderNodeMapRange'); m.inputs['From Min'].default_value = lo; m.inputs['From Max'].default_value = hi
    L_.new(src, m.inputs['Value']); return m.outputs['Result']
def mul(a, b_):
    m = N_.new('ShaderNodeMath'); m.operation = 'MULTIPLY'; L_.new(a, m.inputs[0])
    if isinstance(b_, float): m.inputs[1].default_value = b_
    else: L_.new(b_, m.inputs[1])
    return m.outputs['Value']
cxy = N_.new('ShaderNodeCombineXYZ')
for axis in ('X', 'Y'):
    off = N_.new('ShaderNodeMath'); off.operation = 'SUBTRACT'; off.inputs[1].default_value = 0.5
    L_.new(gen.outputs[axis], off.inputs[0]); L_.new(off.outputs['Value'], cxy.inputs[axis])
rlen = N_.new('ShaderNodeVectorMath'); rlen.operation = 'LENGTH'; L_.new(cxy.outputs[0], rlen.inputs[0])
plume = mul(maprange(rlen.outputs['Value'], 0.35, 0.0), mul(maprange(gen.outputs['Z'], 0.02, 0.14), maprange(gen.outputs['Z'], 1.0, 0.5)))
wisps = maprange(wisp.outputs['Fac'], 0.45, 0.75)
amount = N_.new('ShaderNodeValue'); env = amount.outputs[0]
# a burst of smoke on first contact and another where the edge scorches the board
for t_k, v in ((0.0, 0.0), (T['touch'], 0.0), (T['touch'] + 0.12, 1.8), (T['touch'] + 0.6, 1.0), (T['cutEnd'], 1.0),
               (T['cutEnd'] + 0.12, 1.6), (T['lift1'], 0.5), (DUR, 0.2)):
    env.default_value = v; env.keyframe_insert('default_value', frame=int(t_k * FPS) + 1)
L_.new(mul(mul(mul(wisps, wisps), plume), mul(env, 40.0)), vol.inputs['Density'])
steam.data.materials.append(steam_mat)

# bloom so the hot edge glows
scene.use_nodes = True
ct = scene.node_tree
glare = ct.nodes.new('CompositorNodeGlare'); glare.glare_type = 'FOG_GLOW'; glare.quality = 'HIGH'
glare.threshold = 3.0; glare.size = 6; glare.mix = -0.4
ct.links.new(ct.nodes['Render Layers'].outputs['Image'], glare.inputs['Image'])
ct.links.new(glare.outputs['Image'], ct.nodes['Composite'].inputs['Image'])

# ---------------------------------------------------------------- render settings
r = scene.render
r.resolution_x, r.resolution_y, r.resolution_percentage = 1080, 1920, 100
r.engine = 'CYCLES'
cy = scene.cycles
cy.device = 'CPU'; cy.samples = 20; cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.05
cy.use_denoising = True; cy.denoiser = 'OPENIMAGEDENOISE'; cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
cy.max_bounces = 6; cy.transmission_bounces = 6; cy.glossy_bounces = 3; cy.diffuse_bounces = 1; cy.volume_bounces = 0
cy.caustics_reflective = cy.caustics_refractive = False; cy.sample_clamp_indirect = 6
cy.volume_step_rate = 4.0; cy.volume_max_steps = 256
r.use_persistent_data = True
scene.view_settings.view_transform = 'Standard'   # keeps the saturated gold that AgX mutes
scene.view_settings.exposure = -0.35
r.image_settings.file_format = 'PNG'
r.filepath = os.path.join(OUT, 'frames', 'f_####')

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, 'events.json'), 'w') as fh:
    cut = []
    for ms in range(DUR * 1000):
        t = ms / 1000
        if T['touch'] <= t <= T['cutEnd']:
            h0, p0 = knife_state(t); h1, p1 = knife_state(t + 0.001)
            w = math.sqrt(max(RC * RC - (h0 - C.z) ** 2, 0.0)) / RC
            cut.append([abs(h1 - h0) / 0.001, abs(p1 - p0) / 0.001, w])
        else: cut.append([0, 0, 0])
    json.dump(dict(T=T, liquid=sorted(liquid_events, key=lambda e: e['t']), cut=cut, top=TOP), fh)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'glass_strawberry.blend'))
print('BUILD OK', len(seeds), 'seeds', len(elems), 'liquid elements', liquid_events)
