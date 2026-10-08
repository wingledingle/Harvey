extends SceneTree
## Verification renders: godot --path . --rendering-driver opengl3 --script res://tools/shots.gd -- <out_dir> [shot ...]
## Each shot = state/emote/expression + time to wait, captured from the real renderer.

const SHOTS := [
	["idle", "state", "idle", 1.6, "full"],
	["listening", "state", "listening", 1.6, "full"],
	["thinking", "state", "thinking", 2.0, "full"],
	["talking", "talk", "", 1.3, "full"],
	["happy", "state", "happy", 1.2, "full"],
	["sad", "state", "sad", 1.8, "full"],
	["wave", "emote", "wave", 1.0, "full"],
	["surprised", "emote", "surprised", 0.6, "full"],
	["celebrate", "emote", "celebrate", 1.0, "full"],
	["face_neutral", "state", "idle", 1.2, "portrait"],
	["face_talk", "talk", "", 1.0, "portrait"],
	["face_happy", "expr", "joy", 1.0, "portrait"],
	["face_sad", "state", "sad", 1.6, "portrait"],
	["face_surprised", "expr", "surprised", 1.0, "portrait"],
	["face_thinking", "state", "thinking", 1.6, "portrait"],
	["face_blink", "blink", "", 0.08, "portrait"],
	["back_view", "turn", "", 1.0, "full"],
]

var out_dir := ""


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	out_dir = args[0] if args.size() > 0 else "/tmp"
	var only := args.slice(1)
	var demo: Node3D = (load("res://demo/demo.tscn") as PackedScene).instantiate()
	root.add_child(demo)
	_run.call_deferred(demo, only)


func _run(demo, only: Array) -> void:
	await process_frame
	var av: HarveyAvatar = demo.avatar
	av.auto_blink = false
	av.idle_look_around = false
	for s in SHOTS:
		if only.size() > 0 and not s[0] in only:
			continue
		av.set_expression("")
		av.stop_speaking()
		av.rotation_degrees.y = 0
		av.set_state("idle")
		demo._framing = s[4]
		demo._apply_framing()
		for i in 20: await process_frame
		match s[1]:
			"state": av.set_state(s[2])
			"emote": av.play_emote(s[2])
			"expr": av.set_expression(s[2])
			"talk":
				av.external_lipsync = true
				av.set_lipsync(0.75, 0.2)
				av.set_state("talking")
			"blink":
				av.auto_blink = true
				av.blink_now()
			"turn": av.rotation_degrees.y = 160
		await create_timer(s[3]).timeout
		await RenderingServer.frame_post_draw
		var img := root.get_viewport().get_texture().get_image()
		img.save_png(out_dir.path_join(s[0] + ".png"))
		print("shot ", s[0])
		av.external_lipsync = false
		av.auto_blink = false
	quit()
