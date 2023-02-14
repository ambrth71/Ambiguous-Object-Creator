#############################################
# Ambiguous Object Creator
# ------------------------
# (c) 2023 Thierry AMBROISE
# GNU GPLv3 Licence
#
# From the ambiguous object illusion created by SUGIHARA Kokichi
# http://www.isc.meiji.ac.jp/~kokichis/ambiguousc/ambiguouscylindere.html
#
#############################################
import bpy
import sys
import math
import mathutils

# Constants
ROTATION = math.pi / 4
EXTRUSION_FACTOR = 2.0
TUBE_EXTRUSION = 1.6
PLANE_POSITION = 1.2
MERGE_FACTOR = 0.01
SMALL_DISTANCE = 1e-3
ORIGIN = (0.0, 0.0, 0.0)


# Error exception
class ExitError(Exception):
    pass


# Add-on info
bl_info = {
    "name": "Ambiguous object",
    "blender": (2, 80, 0),
    "category": "Object",
}


# Add-on class
class AmbiguousObject(bpy.types.Operator):
    """Ambiguous object creator"""
    bl_idname = "object.ambiguous_object"
    bl_label = "Ambiguous object"
    bl_options = {'REGISTER', 'UNDO'}

    # Flag for creating a plane shape inside the tube
    # useful for forcing the tube shape when creating a papertoy
    cross_plane: bpy.props.BoolProperty(name='Cross plane', default=True)

    # Add-on execution
    def execute(self, context):
        try:
            ambiguous_object(self, context, self.cross_plane)
        except ExitError:
            print("End")
        return {'FINISHED'}


# Add-on menu
def menu_func(self, context):
    self.layout.separator()
    self.layout.operator(AmbiguousObject.bl_idname)


# Add-on registering
def register():
    bpy.utils.register_class(AmbiguousObject)
    bpy.types.VIEW3D_MT_object.append(menu_func)


# Add-on unregistering
def unregister():
    bpy.utils.unregister_class(AmbiguousObject)
    bpy.types.VIEW3D_MT_object.remove(menu_func)


# Object min/max on global X axis
def object_width(object):
    minx = 1e10
    maxx = -1e10
    for c in object.bound_box:
        v = mathutils.Vector((c[0], c[1], c[2]))
        wv = object.matrix_world @ v
        minx = min(minx, wv.x)
        maxx = max(maxx, wv.x)
    return minx, maxx


# Apply object transformations to its mesh
def apply_object_transform(object):
    matrix = object.matrix_world.copy()
    for vertex in object.data.vertices:
        vertex.co = matrix @ vertex.co
    object.matrix_world.identity()


# Shortest edge length inside an object
def shortest_edge_length(object):
    min_lsq = 1e10
    for e in object.data.edges:
        p1 = object.data.vertices[e.vertices[0]].co
        p2 = object.data.vertices[e.vertices[1]].co
        lsq = (p1[0]-p2[0])**2+(p1[1]-p2[1])**2+(p1[2]-p2[2])**2
        min_lsq = min(min_lsq, lsq)
    return min_lsq**0.5


# Object validity check
def check_object(s, object):
    # Check the number of faces
    if len(object.data.polygons) != 1:
        s.report({'ERROR'}, object.name+' should have a unique face')
        return False
    # Check the object center
    if object.matrix_world.translation != mathutils.Vector(ORIGIN):
        s.report({'ERROR'}, object.name+' origin isn\'t at 0,0,0')
        return False
    # Check the flatness
    for v in object.data.vertices:
        if v.co.z > SMALL_DISTANCE:
            s.report({'ERROR'}, object.name+' isn\'t flat')
            return False
    # Check that the face covers the origin
    result, location, normal, index = \
        object.closest_point_on_mesh(ORIGIN, distance=1e10)
    if not result or math.dist(location, ORIGIN) > SMALL_DISTANCE:
        s.report({'ERROR'}, object.name+' doesn\'t include the origin')
        return False
    return True


# Transforms a flat object to a 3D shape as if it's viewed from one camera
def transform_shape(object, rotation_sign):
    # Select the object
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = object
    object.select_set(True)
    depth = object.dimensions.y
    # Edit the object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')

    # Extrude the flat shape
    bpy.ops.mesh.extrude_region_move(
        TRANSFORM_OT_translate={"value": (0, 0, EXTRUSION_FACTOR*depth)})
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.translate(value=(0.0, 0.0, -EXTRUSION_FACTOR*depth/2.0))
    # Scale it on Y axis
    bpy.ops.transform.resize(value=(1.0, math.cos(ROTATION), 1.0))
    # Rotate it
    bpy.ops.transform.rotate(value=ROTATION*rotation_sign, orient_axis='X',
                             orient_type='GLOBAL')
    # Stop editing
    bpy.ops.object.mode_set(mode='OBJECT')


# Find the vertex with the minimum Z from a list of vertex indices
def min_z_vertex(vertices, indices):
    min_abs_z = sys.float_info.max
    min_z_index = -1
    for i in indices:
        if abs(vertices[i].co.z) < min_abs_z:
            min_abs_z = abs(vertices[i].co.z)
            min_z_index = i
    return min_z_index


# Find the vertices connected to a vertex, excluding the previous connected one
# and filtering those in YZ plane except the symmetric ones across X axis
def connected_vertices(index, mesh, prev_index):
    indices = []
    for e in mesh.edges:
        if index in e.vertices:
            # Add the other vertex if it isn't already part of the contour
            if e.vertices[0] == index and e.vertices[1] != prev_index:
                indices.append(e.vertices[1])
            elif e.vertices[1] == index and e.vertices[0] != prev_index:
                indices.append(e.vertices[0])
    # Filter vertices that can't be part of the contour
    # (only if there are several connected vertices)
    if len(indices) > 1:
        filtered_indices = []
        v = mesh.vertices[index].co
        for i in indices:
            vi = mesh.vertices[i].co
            # Add the vertex if the edge isn't along Y axis
            # (faces from the intersection) or edge is symetrical across X axis
            # (from a concave point on X axis in original shape)
            if v.x != vi.x or (abs(v.y + vi.y) < SMALL_DISTANCE and
                               abs(v.z + vi.z) < SMALL_DISTANCE):
                filtered_indices.append(i)
        # If some points have been found, return them
        if len(filtered_indices) > 0:
            return filtered_indices
        # All connected vertices are on YZ plane, all of them are returned
    return indices


# Select an edge from its 2 vertex indices
def select_edge(mesh, index1, index2):
    for e in mesh.edges:
        if (e.vertices[0] == index1 and e.vertices[1] == index2) or \
                (e.vertices[0] == index2 and e.vertices[1] == index1):
            e.select = True
            break


# Keep only the contour line of objects intersection
# (top of the ambiguous object tube)
def contour_line(s, object):
    # Select the object
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    # Go back to object mode to select vertices and edges by index
    bpy.ops.object.mode_set(mode='OBJECT')

    contour = []
    # Find a starting vertex from all vertices
    index = min_z_vertex(object.data.vertices,
                         range(len(object.data.vertices)))
    contour.append(index)
    object.data.vertices[index].select = True
    prev_index = -1

    # Loop
    while True:
        # Find the candidate vertices connected by an edge
        connected = connected_vertices(index, object.data, prev_index)
        prev_index = index
        # Debug: error case
        if len(connected) < 1:
            s.report({'ERROR'}, 'No connected vertex found while building \
                        tube contour line')
            raise ExitError()
        # Find the connected vertice with minimum Z
        index = min_z_vertex(object.data.vertices, connected)
        # Stop if back on contour start
        if index in contour:
            break
        # Add the vertex to the contour
        contour.append(index)
        object.data.vertices[index].select = True

    # Select edges of the contour
    previous = contour[-1]
    for i in contour:
        select_edge(object.data, previous, i)
        previous = i

    # Switch to edit mode to work on selected vertices
    bpy.ops.object.mode_set(mode='EDIT')
    # Delete all the other edges
    bpy.ops.mesh.select_all(action='INVERT')
    bpy.ops.mesh.delete(type='EDGE')
    # Stop editing
    bpy.ops.object.mode_set(mode='OBJECT')


# Ambiguous object creation main procedure
def ambiguous_object(s, context, cross_plane):
    objects = context.selected_objects
    if len(objects) != 2:
        s.report({'ERROR'}, '2 objects must be selected')
        raise ExitError()
    object1 = objects[0]
    object2 = objects[1]
    # Apply object transformations to mesh
    apply_object_transform(object1)
    apply_object_transform(object2)
    # Check Object validity
    if not check_object(s, object1):
        raise ExitError()
    if not check_object(s, object2):
        raise ExitError()

    # Adjust objects to the same witdth
    bpy.ops.object.select_all(action='DESELECT')
    minx1, maxx1 = object_width(object1)
    minx2, maxx2 = object_width(object2)
    bpy.context.view_layer.objects.active = object2
    object2.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    scale = (maxx1 - minx1) / (maxx2 - minx2)
    bpy.ops.transform.resize(value=(scale, scale, 1.0))
    # Move the object so are aligned on their width
    # Get new X boundaries for object2, object1 is unchanged
    minx2, maxx2 = object_width(object2)
    bpy.ops.transform.translate(value=(minx1 - minx2, 0.0, 0.0))

    # Find the length of the shortest edge
    min_edge_length = shortest_edge_length(object1)
    min_edge_length = min(min_edge_length, shortest_edge_length(object2))

    # Transform the 2 objects to their camera visible shape
    bpy.ops.object.mode_set(mode='OBJECT')
    transform_shape(object1, 1)
    transform_shape(object2, -1)

    # Do the intersection
    bpy.context.view_layer.objects.active = object1
    modifier = object1.modifiers.new(name='intersect', type='BOOLEAN')
    modifier.object = object2
    modifier.operation = 'INTERSECT'
    bpy.ops.object.modifier_apply(modifier='intersect')
    depth = object1.dimensions.y

    # Merge close vertices
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=min_edge_length * MERGE_FACTOR)

    # Remove the second object
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = object2
    bpy.ops.object.delete()

    # Keep only the tube contour points
    contour_line(s, object1)

    # Extrude the vertices to create a tube
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = object1
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.extrude_edges_move(
        TRANSFORM_OT_translate={"value": (0, 0, -depth * TUBE_EXTRUSION)})

    # Cut the tube with a plane to create an internal cross shape
    if cross_plane:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.bisect(plane_co=(0.0, 0.0, -depth * PLANE_POSITION),
                            plane_no=(0.0, 0.0, 1.0), use_fill=True)

    # End
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = object1
    object1.select_set(True)


# Registering on script run for testing
if __name__ == "__main__":
    register()
