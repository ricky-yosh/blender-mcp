"""
Blender Godot MCP Addon
Runs a TCP socket server inside Blender to receive and execute commands from the MCP server.
Install via Edit > Preferences > Add-ons > Install from Disk, then enable it.
"""

bl_info = {
    "name": "Godot Pipeline MCP",
    "author": "Custom",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Godot MCP",
    "description": "MCP server bridge for Godot-focused Blender workflows",
    "category": "Interface",
}

import bpy
import socket
import threading
import json
import os
import traceback
import mathutils
from bpy.props import StringProperty, IntProperty, BoolProperty


# ---------------------------------------------------------------------------
# Socket server
# ---------------------------------------------------------------------------

_server_thread = None
_server_socket = None
_server_running = False

HOST = "localhost"
PORT = 9877  # Different from the default blender-mcp port to avoid conflicts


def handle_command(data: dict) -> dict:
    """Dispatch a command to the appropriate handler and return a result dict."""
    cmd = data.get("command", "")
    params = data.get("params", {})

    handlers = {
        # Scene inspection
        "get_scene_info": cmd_get_scene_info,
        "get_object_info": cmd_get_object_info,
        "list_objects": cmd_list_objects,

        # Object manipulation
        "create_object": cmd_create_object,
        "delete_object": cmd_delete_object,
        "set_transform": cmd_set_transform,
        "set_name": cmd_set_name,

        # Materials & texturing
        "list_materials": cmd_list_materials,
        "create_material": cmd_create_material,
        "assign_material": cmd_assign_material,
        "set_material_color": cmd_set_material_color,
        "set_material_pbr": cmd_set_material_pbr,

        # Rigging & animation
        "create_armature": cmd_create_armature,
        "list_actions": cmd_list_actions,
        "set_keyframe": cmd_set_keyframe,

        # Godot export
        "export_gltf": cmd_export_gltf,
        "export_selected_gltf": cmd_export_selected_gltf,
        "set_godot_custom_properties": cmd_set_godot_custom_properties,

        # Utilities
        "execute_python": cmd_execute_python,
        "set_render_settings": cmd_set_render_settings,
    }

    handler = handlers.get(cmd)
    if handler is None:
        return {"status": "error", "message": f"Unknown command: '{cmd}'. Available: {sorted(handlers.keys())}"}

    try:
        result = handler(params)
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


def run_in_main_thread(func):
    """Schedule a callable on Blender's main thread and block until done."""
    result_container = {}
    event = threading.Event()

    def wrapper():
        try:
            result_container["value"] = func()
        except Exception as e:
            result_container["error"] = str(e)
            result_container["traceback"] = traceback.format_exc()
        event.set()
        return None  # Don't re-register timer

    bpy.app.timers.register(wrapper, first_interval=0.0)
    event.wait(timeout=30)

    if "error" in result_container:
        raise RuntimeError(result_container["error"])
    return result_container.get("value")


def client_handler(conn: socket.socket):
    try:
        raw = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk
            if raw.endswith(b"\n"):
                break

        if not raw:
            return

        data = json.loads(raw.decode("utf-8").strip())
        response = run_in_main_thread(lambda: handle_command(data))
        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
    except Exception as e:
        error_resp = {"status": "error", "message": str(e)}
        try:
            conn.sendall((json.dumps(error_resp) + "\n").encode("utf-8"))
        except Exception:
            pass
    finally:
        conn.close()


def server_loop():
    global _server_socket, _server_running
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind((HOST, PORT))
    _server_socket.listen(5)
    _server_socket.settimeout(1.0)
    print(f"[Godot MCP] Server listening on {HOST}:{PORT}")

    while _server_running:
        try:
            conn, _ = _server_socket.accept()
            t = threading.Thread(target=client_handler, args=(conn,), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break

    _server_socket.close()
    print("[Godot MCP] Server stopped.")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_get_scene_info(params):
    scene = bpy.context.scene
    objects = []
    for obj in scene.objects:
        objects.append({
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation_euler": list(obj.rotation_euler),
            "scale": list(obj.scale),
            "visible": not obj.hide_viewport,
            "parent": obj.parent.name if obj.parent else None,
        })
    return {
        "scene_name": scene.name,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "fps": scene.render.fps,
        "object_count": len(objects),
        "objects": objects,
    }


def cmd_list_objects(params):
    obj_type = params.get("type")  # optional filter: MESH, ARMATURE, LIGHT, CAMERA, etc.
    result = []
    for obj in bpy.context.scene.objects:
        if obj_type and obj.type != obj_type.upper():
            continue
        result.append({
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        })
    return result


def cmd_get_object_info(params):
    name = params["name"]
    obj = bpy.data.objects.get(name)
    if not obj:
        raise ValueError(f"Object '{name}' not found.")
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "visible": not obj.hide_viewport,
        "parent": obj.parent.name if obj.parent else None,
        "children": [c.name for c in obj.children],
        "materials": [s.material.name for s in obj.material_slots if s.material],
        "custom_properties": {k: obj[k] for k in obj.keys() if not k.startswith("_")},
    }
    if obj.type == "ARMATURE":
        info["bones"] = [b.name for b in obj.data.bones]
    if obj.type == "MESH":
        info["vertex_count"] = len(obj.data.vertices)
        info["polygon_count"] = len(obj.data.polygons)
    return info


def cmd_create_object(params):
    obj_type = params.get("type", "CUBE").upper()
    name = params.get("name", "NewObject")
    location = params.get("location", [0, 0, 0])
    scale = params.get("scale", [1, 1, 1])

    type_map = {
        "CUBE": "primitive_cube_add",
        "SPHERE": "primitive_uv_sphere_add",
        "CYLINDER": "primitive_cylinder_add",
        "PLANE": "primitive_plane_add",
        "CONE": "primitive_cone_add",
        "TORUS": "primitive_torus_add",
        "EMPTY": None,
    }

    if obj_type not in type_map:
        raise ValueError(f"Unsupported type '{obj_type}'. Choose from: {list(type_map.keys())}")

    if obj_type == "EMPTY":
        bpy.ops.object.empty_add(location=location)
    else:
        fn = getattr(bpy.ops.mesh, type_map[obj_type])
        fn(location=location)

    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    return {"created": obj.name, "type": obj.type}


def cmd_delete_object(params):
    name = params["name"]
    obj = bpy.data.objects.get(name)
    if not obj:
        raise ValueError(f"Object '{name}' not found.")
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": name}


def cmd_set_transform(params):
    name = params["name"]
    obj = bpy.data.objects.get(name)
    if not obj:
        raise ValueError(f"Object '{name}' not found.")
    if "location" in params:
        obj.location = params["location"]
    if "rotation_euler" in params:
        obj.rotation_euler = params["rotation_euler"]
    if "scale" in params:
        obj.scale = params["scale"]
    return {"name": obj.name, "location": list(obj.location), "rotation_euler": list(obj.rotation_euler), "scale": list(obj.scale)}


def cmd_set_name(params):
    old_name = params["name"]
    new_name = params["new_name"]
    obj = bpy.data.objects.get(old_name)
    if not obj:
        raise ValueError(f"Object '{old_name}' not found.")
    obj.name = new_name
    return {"old_name": old_name, "new_name": obj.name}


# --- Materials ---

def cmd_list_materials(params):
    return [{"name": m.name, "users": m.users} for m in bpy.data.materials]


def cmd_create_material(params):
    name = params["name"]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    return {"created": mat.name}


def cmd_assign_material(params):
    obj_name = params["object"]
    mat_name = params["material"]
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        raise ValueError(f"Object '{obj_name}' not found.")
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        raise ValueError(f"Material '{mat_name}' not found.")
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return {"object": obj.name, "material": mat.name}


def _get_principled_bsdf(mat):
    mat.use_nodes = True
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    raise ValueError(f"No Principled BSDF found in material '{mat.name}'.")


def cmd_set_material_color(params):
    mat_name = params["material"]
    color = params["color"]  # [R, G, B] or [R, G, B, A] 0-1 range
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        raise ValueError(f"Material '{mat_name}' not found.")
    bsdf = _get_principled_bsdf(mat)
    rgba = list(color) + [1.0] if len(color) == 3 else color
    bsdf.inputs["Base Color"].default_value = rgba
    return {"material": mat_name, "color": rgba}


def cmd_set_material_pbr(params):
    """Set PBR properties: metallic, roughness, emission, alpha."""
    mat_name = params["material"]
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        raise ValueError(f"Material '{mat_name}' not found.")
    bsdf = _get_principled_bsdf(mat)
    updated = {}
    for prop, input_name in [
        ("metallic", "Metallic"),
        ("roughness", "Roughness"),
        ("alpha", "Alpha"),
        ("ior", "IOR"),
    ]:
        if prop in params:
            bsdf.inputs[input_name].default_value = float(params[prop])
            updated[prop] = params[prop]
    if "emission" in params:
        color = params["emission"]
        rgba = list(color) + [1.0] if len(color) == 3 else color
        bsdf.inputs["Emission Color"].default_value = rgba
        updated["emission"] = rgba
    if "emission_strength" in params:
        bsdf.inputs["Emission Strength"].default_value = float(params["emission_strength"])
        updated["emission_strength"] = params["emission_strength"]
    return {"material": mat_name, "updated": updated}


# --- Rigging & Animation ---

def cmd_create_armature(params):
    name = params.get("name", "Armature")
    location = params.get("location", [0, 0, 0])
    bpy.ops.object.armature_add(location=location)
    arm_obj = bpy.context.active_object
    arm_obj.name = name
    return {"created": arm_obj.name, "type": "ARMATURE"}


def cmd_list_actions(params):
    return [{"name": a.name, "frame_range": list(a.frame_range)} for a in bpy.data.actions]


def cmd_set_keyframe(params):
    obj_name = params["object"]
    frame = params["frame"]
    data_path = params.get("data_path", "location")  # location, rotation_euler, scale, etc.
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        raise ValueError(f"Object '{obj_name}' not found.")
    bpy.context.scene.frame_set(frame)
    obj.keyframe_insert(data_path=data_path, frame=frame)
    return {"object": obj_name, "frame": frame, "data_path": data_path}


# --- Godot Export ---

def _godot_gltf_settings(params: dict) -> dict:
    """Build kwargs for bpy.ops.export_scene.gltf that suit Godot best."""
    export_path = params.get("path", "//export.glb")
    # Resolve relative paths
    if export_path.startswith("//"):
        export_path = bpy.path.abspath(export_path)

    return {
        "filepath": export_path,
        "export_format": params.get("format", "GLB"),          # GLB or GLTF_SEPARATE
        "export_apply": params.get("apply_modifiers", True),   # Apply modifiers
        "export_animations": params.get("animations", True),
        "export_skins": params.get("skins", True),
        "export_morph": params.get("shape_keys", True),
        "export_materials": "EXPORT",
        "export_yup": True,                                     # Godot uses Y-up
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": params.get("tangents", True),
        "export_colors": params.get("vertex_colors", True),
        "export_cameras": params.get("cameras", False),
        "export_lights": params.get("lights", False),
        "use_selection": False,
    }


def cmd_export_gltf(params):
    """Export entire scene as GLB/GLTF optimised for Godot."""
    kwargs = _godot_gltf_settings(params)
    filepath = kwargs["filepath"]
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    bpy.ops.export_scene.gltf(**kwargs)
    return {"exported": filepath, "format": kwargs["export_format"]}


def cmd_export_selected_gltf(params):
    """Export only selected objects as GLB/GLTF for Godot."""
    kwargs = _godot_gltf_settings(params)
    kwargs["use_selection"] = True
    filepath = kwargs["filepath"]
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    bpy.ops.export_scene.gltf(**kwargs)
    return {"exported": filepath, "selection_only": True}


def cmd_set_godot_custom_properties(params):
    """
    Set custom properties on an object that will be exported as Godot metadata.
    e.g. collision layer, node type hints, etc.
    """
    obj_name = params["object"]
    properties = params["properties"]  # dict of key: value
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        raise ValueError(f"Object '{obj_name}' not found.")
    for k, v in properties.items():
        obj[k] = v
    return {"object": obj_name, "properties_set": list(properties.keys())}


# --- Utilities ---

def cmd_execute_python(params):
    """Execute arbitrary Python (bpy) code. Use with caution — save first!"""
    code = params["code"]
    namespace = {"bpy": bpy, "mathutils": mathutils}
    exec(compile(code, "<mcp>", "exec"), namespace)  # noqa: S102
    return {"executed": True, "output": str(namespace.get("_result", ""))}


def cmd_set_render_settings(params):
    scene = bpy.context.scene
    updated = {}
    if "engine" in params:
        scene.render.engine = params["engine"].upper()
        updated["engine"] = scene.render.engine
    if "resolution_x" in params:
        scene.render.resolution_x = int(params["resolution_x"])
        updated["resolution_x"] = scene.render.resolution_x
    if "resolution_y" in params:
        scene.render.resolution_y = int(params["resolution_y"])
        updated["resolution_y"] = scene.render.resolution_y
    if "fps" in params:
        scene.render.fps = int(params["fps"])
        updated["fps"] = scene.render.fps
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Blender UI Panel & Operators
# ---------------------------------------------------------------------------

class GODOT_MCP_OT_start(bpy.types.Operator):
    bl_idname = "godot_mcp.start_server"
    bl_label = "Start MCP Server"

    def execute(self, context):
        global _server_thread, _server_running
        if _server_running:
            self.report({"WARNING"}, "Server already running.")
            return {"CANCELLED"}
        _server_running = True
        _server_thread = threading.Thread(target=server_loop, daemon=True)
        _server_thread.start()
        self.report({"INFO"}, f"Godot MCP server started on port {PORT}")
        return {"FINISHED"}


class GODOT_MCP_OT_stop(bpy.types.Operator):
    bl_idname = "godot_mcp.stop_server"
    bl_label = "Stop MCP Server"

    def execute(self, context):
        global _server_running
        _server_running = False
        self.report({"INFO"}, "Godot MCP server stopped.")
        return {"FINISHED"}


class GODOT_MCP_PT_panel(bpy.types.Panel):
    bl_label = "Godot MCP"
    bl_idname = "GODOT_MCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Godot MCP"

    def draw(self, context):
        layout = self.layout
        status = "Running" if _server_running else "Stopped"
        layout.label(text=f"Status: {status}", icon="CHECKMARK" if _server_running else "X")
        layout.label(text=f"Port: {PORT}")
        if not _server_running:
            layout.operator("godot_mcp.start_server", icon="PLAY")
        else:
            layout.operator("godot_mcp.stop_server", icon="PAUSE")


classes = [GODOT_MCP_OT_start, GODOT_MCP_OT_stop, GODOT_MCP_PT_panel]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    global _server_running
    _server_running = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
