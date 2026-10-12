extends SceneTree
## Close-up renders: godot --path . --script res://tools/closeup.gd -- <out_dir>
const VIEWS := {
	"nose_front": [Vector3(0, 1.3, 2.2), Vector3(0, 1.25, 0)],
	"nose_side": [Vector3(1.9, 1.35, 1.2), Vector3(0, 1.25, 0.4)],
	"nose_34": [Vector3(1.2, 1.5, 1.9), Vector3(0, 1.25, 0.3)],
	"hands_front": [Vector3(0, 0.5, 2.2), Vector3(0, 0.45, 0)],
	"hand_side": [Vector3(1.8, 0.5, 0.9), Vector3(0.3, 0.45, 0.2)],
	"body_34": [Vector3(2.6, 1.1, 3.6), Vector3(0, 0.95, 0)],
}
func _initialize() -> void:
	var demo: Node3D = (load("res://demo/demo.tscn") as PackedScene).instantiate()
	root.add_child(demo)
	_run.call_deferred(demo)
func _run(demo) -> void:
	for c in demo.get_children():
		if c is CanvasLayer: c.visible = false
	var av = demo.avatar
	av.auto_blink = false; av.idle_look_around = false
	await create_timer(0.5).timeout
	for k in VIEWS:
		demo.cam.position = VIEWS[k][0]; demo.cam.look_at(VIEWS[k][1]); demo.cam.fov = 35
		await create_timer(0.3).timeout
		await RenderingServer.frame_post_draw
		root.get_viewport().get_texture().get_image().save_png(OS.get_cmdline_user_args()[0].path_join(k + ".png"))
	quit()
