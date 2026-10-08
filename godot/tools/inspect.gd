extends SceneTree
# Prints the imported scene tree + animation list. Usage: godot --headless --script res://tools/inspect.gd
func _init():
	var s: PackedScene = load("res://avatar/harvey.glb")
	var n := s.instantiate()
	_dump(n, 0)
	var ap: AnimationPlayer = n.find_child("AnimationPlayer", true, false)
	print("animations: ", ap.get_animation_list())
	var sk: Skeleton3D = n.find_child("Skeleton3D", true, false)
	print("bones: ", sk.get_bone_count())
	var mi: MeshInstance3D = n.find_child("Body", true, false)
	var arr = mi.mesh.surface_get_arrays(0)
	print("verts: ", arr[Mesh.ARRAY_VERTEX].size(), " colors: ", arr[Mesh.ARRAY_COLOR].size() if arr[Mesh.ARRAY_COLOR] else 0, " uv: ", arr[Mesh.ARRAY_TEX_UV].size())
	print("color sample: ", arr[Mesh.ARRAY_COLOR][100] if arr[Mesh.ARRAY_COLOR] else "none")
	quit()
func _dump(n: Node, d: int):
	print("  ".repeat(d), n.name, " (", n.get_class(), ")")
	for c in n.get_children(): _dump(c, d + 1)
