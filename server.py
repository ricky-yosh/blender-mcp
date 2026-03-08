"""
Godot Pipeline MCP Server
Connects Claude Code (or any MCP client) to a running Blender instance
via the Godot MCP addon's TCP socket.

Usage:
    pip install mcp
    python server.py

Or add to Claude Code:
    claude mcp add-json "blender-godot" '{"command":"python","args":["/path/to/server.py"]}'
"""

import asyncio
import json
import socket
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BLENDER_HOST = "localhost"
BLENDER_PORT = 9877


# ---------------------------------------------------------------------------
# Blender socket communication
# ---------------------------------------------------------------------------

def send_command(command: str, params: Optional[dict] = None) -> Any:
    """Send a command to the Blender addon and return the parsed result."""
    payload = json.dumps({"command": command, "params": params or {}}) + "\n"

    with socket.create_connection((BLENDER_HOST, BLENDER_PORT), timeout=30) as sock:
        sock.sendall(payload.encode("utf-8"))
        raw = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
            if raw.endswith(b"\n"):
                break

    response = json.loads(raw.decode("utf-8").strip())

    if response.get("status") == "error":
        msg = response.get("message", "Unknown error from Blender")
        tb = response.get("traceback", "")
        raise RuntimeError(f"Blender error: {msg}\n{tb}" if tb else f"Blender error: {msg}")

    return response.get("result")


def blender_available() -> bool:
    try:
        with socket.create_connection((BLENDER_HOST, BLENDER_PORT), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "blender_godot_mcp",
    instructions=(
        "You are connected to a running Blender instance configured for Godot game development. "
        "You can inspect and modify the 3D scene, manage materials with PBR workflows, "
        "rig and animate characters, set Godot-specific custom properties, and export assets "
        "as GLB/GLTF files optimised for the Godot engine. "
        "Always check the scene first with blender_get_scene_info before making changes. "
        "When exporting, prefer GLB format for Godot 4. "
        "For rigged characters, ensure the armature is parented to the mesh before exporting."
    ),
)


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class ObjectNameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Name of the Blender object")


class CreateObjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Name for the new object")
    type: str = Field(
        default="CUBE",
        description="Primitive type: CUBE, SPHERE, CYLINDER, PLANE, CONE, TORUS, EMPTY",
    )
    location: list[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] world position")
    scale: list[float] = Field(default=[1.0, 1.0, 1.0], description="[X, Y, Z] scale")


class SetTransformInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Object name")
    location: Optional[list[float]] = Field(None, description="[X, Y, Z] world position")
    rotation_euler: Optional[list[float]] = Field(None, description="[X, Y, Z] rotation in radians")
    scale: Optional[list[float]] = Field(None, description="[X, Y, Z] scale")


class SetNameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Current object name")
    new_name: str = Field(..., description="New name to assign")


class ListObjectsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Optional[str] = Field(
        None,
        description="Filter by type: MESH, ARMATURE, LIGHT, CAMERA, EMPTY. Leave empty for all.",
    )


class CreateMaterialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Name for the new material")


class AssignMaterialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object: str = Field(..., description="Object to assign material to")
    material: str = Field(..., description="Material name to assign")


class SetMaterialColorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material: str = Field(..., description="Material name")
    color: list[float] = Field(
        ...,
        description="RGB or RGBA color values in 0.0–1.0 range, e.g. [0.8, 0.2, 0.1] for red",
    )


class SetMaterialPBRInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material: str = Field(..., description="Material name")
    metallic: Optional[float] = Field(None, ge=0.0, le=1.0, description="Metallic value 0.0–1.0")
    roughness: Optional[float] = Field(None, ge=0.0, le=1.0, description="Roughness value 0.0–1.0")
    alpha: Optional[float] = Field(None, ge=0.0, le=1.0, description="Alpha/opacity 0.0–1.0")
    ior: Optional[float] = Field(None, ge=0.0, description="Index of refraction (default 1.45)")
    emission: Optional[list[float]] = Field(None, description="Emission color [R, G, B]")
    emission_strength: Optional[float] = Field(None, ge=0.0, description="Emission strength multiplier")


class CreateArmatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Armature", description="Name for the armature object")
    location: list[float] = Field(default=[0.0, 0.0, 0.0], description="[X, Y, Z] world position")


class SetKeyframeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object: str = Field(..., description="Object name to keyframe")
    frame: int = Field(..., description="Frame number to insert keyframe at")
    data_path: str = Field(
        default="location",
        description="Property to keyframe: location, rotation_euler, scale, etc.",
    )


class ExportGLTFInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(..., description="Export path, e.g. /absolute/path/asset.glb or //relative.glb")
    format: str = Field(default="GLB", description="GLB (single file, recommended) or GLTF_SEPARATE")
    apply_modifiers: bool = Field(default=True, description="Apply modifiers before export")
    animations: bool = Field(default=True, description="Include animations")
    skins: bool = Field(default=True, description="Include armature skins")
    shape_keys: bool = Field(default=True, description="Include shape keys / morph targets")
    tangents: bool = Field(default=True, description="Export tangents (needed for normal maps)")
    vertex_colors: bool = Field(default=True, description="Export vertex color data")
    cameras: bool = Field(default=False, description="Export cameras")
    lights: bool = Field(default=False, description="Export lights")


class ExportSelectedGLTFInput(ExportGLTFInput):
    pass  # Same fields, but only exports selected objects


class GodotCustomPropertiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object: str = Field(..., description="Object name to set properties on")
    properties: dict[str, Any] = Field(
        ...,
        description=(
            "Dict of custom properties that will appear as Godot node metadata after export. "
            "Common uses: collision_layer, collision_mask, node_type, lod_bias, etc."
        ),
    )


class ExecutePythonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(
        ...,
        description=(
            "Python code to execute inside Blender. Has access to bpy and mathutils. "
            "Set _result to return a value. ALWAYS save your work first."
        ),
    )


class RenderSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Optional[str] = Field(
        None, description="Render engine: CYCLES, BLENDER_EEVEE_NEXT, BLENDER_WORKBENCH"
    )
    resolution_x: Optional[int] = Field(None, ge=1, description="Render width in pixels")
    resolution_y: Optional[int] = Field(None, ge=1, description="Render height in pixels")
    fps: Optional[int] = Field(None, ge=1, le=240, description="Frames per second")


# ---------------------------------------------------------------------------
# Tools — Scene Inspection
# ---------------------------------------------------------------------------

@mcp.tool(
    name="blender_get_scene_info",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
def blender_get_scene_info() -> str:
    """Get a full overview of the current Blender scene.

    Returns scene name, frame range, FPS, object count, and a list of all
    objects with their type, location, rotation, scale, visibility, and parent.

    Returns:
        str: JSON with keys scene_name, frame_start, frame_end, fps, object_count, objects[]
    """
    result = send_command("get_scene_info")
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_list_objects",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
def blender_list_objects(params: ListObjectsInput) -> str:
    """List objects in the scene, optionally filtered by type.

    Args:
        params.type: Optional filter — MESH, ARMATURE, LIGHT, CAMERA, EMPTY

    Returns:
        str: JSON array of {name, type, location}
    """
    result = send_command("list_objects", params.model_dump(exclude_none=True))
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_get_object_info",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
def blender_get_object_info(params: ObjectNameInput) -> str:
    """Get detailed information about a specific object.

    Returns location, rotation, scale, dimensions, materials, custom properties,
    children, parent, and for meshes: vertex/polygon count. For armatures: bone list.

    Args:
        params.name: Object name

    Returns:
        str: JSON with full object details
    """
    result = send_command("get_object_info", params.model_dump())
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tools — Object Manipulation
# ---------------------------------------------------------------------------

@mcp.tool(
    name="blender_create_object",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
def blender_create_object(params: CreateObjectInput) -> str:
    """Create a primitive mesh object in the scene.

    Args:
        params.name: Name for the new object
        params.type: CUBE, SPHERE, CYLINDER, PLANE, CONE, TORUS, or EMPTY
        params.location: [X, Y, Z] world position
        params.scale: [X, Y, Z] scale

    Returns:
        str: JSON with {created, type}
    """
    result = send_command("create_object", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_delete_object",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
)
def blender_delete_object(params: ObjectNameInput) -> str:
    """Delete an object from the scene permanently.

    Args:
        params.name: Name of the object to delete

    Returns:
        str: JSON with {deleted}
    """
    result = send_command("delete_object", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_transform",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_set_transform(params: SetTransformInput) -> str:
    """Set the location, rotation, and/or scale of an object.

    Provide only the properties you want to change — omitted ones are left unchanged.

    Args:
        params.name: Object name
        params.location: [X, Y, Z] world position (optional)
        params.rotation_euler: [X, Y, Z] rotation in radians (optional)
        params.scale: [X, Y, Z] scale (optional)

    Returns:
        str: JSON with updated transform values
    """
    result = send_command("set_transform", params.model_dump(exclude_none=True))
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_name",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_set_name(params: SetNameInput) -> str:
    """Rename an object.

    Args:
        params.name: Current object name
        params.new_name: New name to assign

    Returns:
        str: JSON with {old_name, new_name}
    """
    result = send_command("set_name", params.model_dump())
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tools — Materials & Texturing
# ---------------------------------------------------------------------------

@mcp.tool(
    name="blender_list_materials",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
def blender_list_materials() -> str:
    """List all materials in the Blender file.

    Returns:
        str: JSON array of {name, users}
    """
    result = send_command("list_materials")
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_create_material",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
def blender_create_material(params: CreateMaterialInput) -> str:
    """Create a new material with nodes enabled.

    Args:
        params.name: Name for the new material

    Returns:
        str: JSON with {created}
    """
    result = send_command("create_material", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_assign_material",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_assign_material(params: AssignMaterialInput) -> str:
    """Assign a material to an object's first material slot.

    Args:
        params.object: Object name
        params.material: Material name

    Returns:
        str: JSON with {object, material}
    """
    result = send_command("assign_material", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_material_color",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_set_material_color(params: SetMaterialColorInput) -> str:
    """Set the base color of a material's Principled BSDF node.

    Args:
        params.material: Material name
        params.color: [R, G, B] or [R, G, B, A] in 0.0–1.0 range

    Returns:
        str: JSON with {material, color}
    """
    result = send_command("set_material_color", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_material_pbr",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_set_material_pbr(params: SetMaterialPBRInput) -> str:
    """Set PBR properties on a material's Principled BSDF node.

    Provide only the properties you want to change.

    Args:
        params.material: Material name
        params.metallic: 0.0 (dielectric) to 1.0 (metal)
        params.roughness: 0.0 (mirror) to 1.0 (fully rough)
        params.alpha: 0.0 (transparent) to 1.0 (opaque)
        params.ior: Index of refraction (default 1.45)
        params.emission: [R, G, B] emission color
        params.emission_strength: Emission strength multiplier

    Returns:
        str: JSON with {material, updated}
    """
    result = send_command("set_material_pbr", params.model_dump(exclude_none=True))
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tools — Rigging & Animation
# ---------------------------------------------------------------------------

@mcp.tool(
    name="blender_create_armature",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
def blender_create_armature(params: CreateArmatureInput) -> str:
    """Create a new armature object (skeleton) in the scene.

    After creation, use execute_python to enter edit mode and add bones.

    Args:
        params.name: Armature name
        params.location: [X, Y, Z] world position

    Returns:
        str: JSON with {created, type}
    """
    result = send_command("create_armature", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_list_actions",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
def blender_list_actions() -> str:
    """List all animation actions in the file.

    Returns:
        str: JSON array of {name, frame_range}
    """
    result = send_command("list_actions")
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_keyframe",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
def blender_set_keyframe(params: SetKeyframeInput) -> str:
    """Insert a keyframe on an object at a specific frame.

    Args:
        params.object: Object name
        params.frame: Frame number
        params.data_path: Property to keyframe (location, rotation_euler, scale, etc.)

    Returns:
        str: JSON with {object, frame, data_path}
    """
    result = send_command("set_keyframe", params.model_dump())
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tools — Godot Export
# ---------------------------------------------------------------------------

@mcp.tool(
    name="blender_export_gltf",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
def blender_export_gltf(params: ExportGLTFInput) -> str:
    """Export the entire scene as GLB/GLTF optimised for Godot 4.

    Exports with Y-up convention (Godot standard), applies modifiers,
    and includes animations, skins, and shape keys by default.

    Args:
        params.path: Absolute export path ending in .glb or .gltf
        params.format: GLB (recommended for Godot) or GLTF_SEPARATE
        params.apply_modifiers: Apply modifiers before export (default True)
        params.animations: Include animations (default True)
        params.skins: Include armature skin weights (default True)
        params.shape_keys: Include shape keys / morph targets (default True)
        params.tangents: Export tangents for normal mapping (default True)
        params.vertex_colors: Export vertex color layers (default True)
        params.cameras: Export camera objects (default False)
        params.lights: Export light objects (default False)

    Returns:
        str: JSON with {exported, format}
    """
    result = send_command("export_gltf", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_export_selected_gltf",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
def blender_export_selected_gltf(params: ExportSelectedGLTFInput) -> str:
    """Export only the currently selected objects as GLB/GLTF for Godot.

    Useful for exporting individual characters, props, or environment pieces.
    Same options as blender_export_gltf but scoped to selection.

    Args:
        params.path: Absolute export path
        (all other args same as blender_export_gltf)

    Returns:
        str: JSON with {exported, selection_only}
    """
    result = send_command("export_selected_gltf", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_godot_custom_properties",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_set_godot_custom_properties(params: GodotCustomPropertiesInput) -> str:
    """Set custom properties on an object that become Godot node metadata on export.

    These properties transfer through GLB export and appear as metadata in Godot's
    import pipeline. Useful for collision layers, physics body hints, LOD settings, etc.

    Args:
        params.object: Object name
        params.properties: Dict of property name → value, e.g.:
            {"collision_layer": 2, "node_type": "StaticBody3D", "lod_bias": 0.5}

    Returns:
        str: JSON with {object, properties_set}
    """
    result = send_command("set_godot_custom_properties", params.model_dump())
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tools — Utilities
# ---------------------------------------------------------------------------

@mcp.tool(
    name="blender_execute_python",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
)
def blender_execute_python(params: ExecutePythonInput) -> str:
    """Execute arbitrary Python code inside Blender (via bpy).

    For complex operations not covered by other tools. Has full access to
    bpy and mathutils. Set the variable _result to return a value.

    WARNING: This can modify or destroy your scene. Always save before using.

    Args:
        params.code: Python code string

    Returns:
        str: JSON with {executed, output} where output is the value of _result if set
    """
    result = send_command("execute_python", params.model_dump())
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_set_render_settings",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
def blender_set_render_settings(params: RenderSettingsInput) -> str:
    """Configure scene render settings.

    Args:
        params.engine: CYCLES, BLENDER_EEVEE_NEXT, or BLENDER_WORKBENCH
        params.resolution_x: Render width in pixels
        params.resolution_y: Render height in pixels
        params.fps: Frames per second

    Returns:
        str: JSON with {updated} dict of changed settings
    """
    result = send_command("set_render_settings", params.model_dump(exclude_none=True))
    return json.dumps(result, indent=2)


@mcp.tool(
    name="blender_check_connection",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
def blender_check_connection() -> str:
    """Check if the Blender addon is running and reachable.

    Call this first if you're unsure whether Blender is connected.

    Returns:
        str: JSON with {connected: bool, host, port}
    """
    connected = blender_available()
    return json.dumps({"connected": connected, "host": BLENDER_HOST, "port": BLENDER_PORT})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
