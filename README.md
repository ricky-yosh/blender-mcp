# Blender → Godot MCP

A custom MCP server connecting Claude Code to Blender, purpose-built for Godot indie game development.

## What it does

Claude Code can directly control Blender to:

- **Inspect & modify scenes** — query objects, transforms, hierarchy
- **Create & manipulate objects** — primitives, parenting, naming
- **PBR materials** — create, assign, set base color, metallic/roughness/emission
- **Rigging & animation** — create armatures, list actions, insert keyframes
- **Godot-specific export** — GLB/GLTF with Y-up, applied modifiers, custom metadata
- **Godot custom properties** — set collision layers, node type hints, LOD bias etc. that survive GLB export
- **Raw Python fallback** — execute any `bpy` code for things not covered by other tools

---

## Setup

### 1. Install the Blender addon

1. Open Blender
2. Go to **Edit → Preferences → Add-ons → Install from Disk**
3. Select `addon.py`
4. Enable the **Godot Pipeline MCP** addon
5. Open the **N panel** (press N in the 3D viewport) → **Godot MCP** tab
6. Click **Start MCP Server** — you should see "Status: Running on port 9877"

### 2. Install the MCP server dependencies

```bash
pip install mcp
```

### 3. Add to Claude Code

```bash
claude mcp add-json "blender-godot" '{"command":"python","args":["/absolute/path/to/server.py"]}'
```

Or add manually to your `.mcp.json`:

```json
{
  "mcpServers": {
    "blender-godot": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `blender_check_connection` | Verify Blender is reachable |
| `blender_get_scene_info` | Full scene overview |
| `blender_list_objects` | List objects, optionally filtered by type |
| `blender_get_object_info` | Detailed info on one object |
| `blender_create_object` | Add a primitive mesh |
| `blender_delete_object` | Remove an object |
| `blender_set_transform` | Move/rotate/scale an object |
| `blender_set_name` | Rename an object |
| `blender_list_materials` | List all materials |
| `blender_create_material` | Create a new material |
| `blender_assign_material` | Assign material to object |
| `blender_set_material_color` | Set base color |
| `blender_set_material_pbr` | Set metallic, roughness, emission, etc. |
| `blender_create_armature` | Add a skeleton |
| `blender_list_actions` | List animation actions |
| `blender_set_keyframe` | Insert a keyframe |
| `blender_export_gltf` | Export whole scene as GLB for Godot |
| `blender_export_selected_gltf` | Export selected objects only |
| `blender_set_godot_custom_properties` | Set Godot metadata on objects |
| `blender_set_render_settings` | Configure render engine, resolution, FPS |
| `blender_execute_python` | Run arbitrary bpy code (power user) |

---

## Example prompts for Claude Code

```
"Check what's in my current Blender scene"

"Create a low-poly rock mesh, name it Rock_01, and put it at (2, 0, 0)"

"Make a metal material called MetalPlate with roughness 0.3 and metallic 1.0, assign it to Rock_01"

"Export the whole scene to /home/me/godot_project/assets/level_01.glb"

"Set Rock_01's collision_layer to 2 and node_type to StaticBody3D so Godot picks it up correctly"

"Export just the selected character mesh and its armature to /assets/characters/hero.glb"
```

---

## Notes

- The addon runs on port **9877** (different from the generic blender-mcp to avoid conflicts)
- Always save your `.blend` file before using `blender_execute_python` — it can do anything
- Godot 4 prefers **GLB** format; GLTF_SEPARATE is available if you need editable JSON
- Custom properties set via `blender_set_godot_custom_properties` appear in Godot's scene tree as node metadata after import
- For complex armature work, use `blender_execute_python` with bpy edit-mode commands
