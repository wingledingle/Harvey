extends SceneTree
## Scripted showcase for video capture:
## godot --path . --rendering-driver opengl3 --write-movie out.avi --fixed-fps 30 --script res://tools/demo_reel.gd

const STEPS := [
	# [caption, kind, arg, seconds, framing]
	["Idle", "state", "idle", 3.5, "full"],
	["Wave", "emote", "wave", 2.8, "full"],
	["Listening", "state", "listening", 3.0, "full"],
	["Thinking", "state", "thinking", 3.5, "full"],
	["Talking (lip-sync)", "speak", "Hi there! I'm Harvey, your assistant. How can I help you today?", 4.5, "full"],
	["Happy", "state", "happy", 3.0, "full"],
	["Nod", "emote", "nod", 1.6, "full"],
	["Shake", "emote", "shake", 1.8, "full"],
	["Surprised", "emote", "surprised", 2.0, "full"],
	["Sad", "state", "sad", 3.0, "full"],
	["Celebrate", "emote", "celebrate", 2.6, "full"],
	["Close-up: talking", "speak", "Sure! I can set a reminder for you. Anything else?", 3.8, "portrait"],
	["Close-up: joy", "expr", "joy", 2.0, "portrait"],
	["Close-up: thinking", "state", "thinking", 2.5, "portrait"],
]

var caption: Label


func _initialize() -> void:
	var demo: Node3D = (load("res://demo/demo.tscn") as PackedScene).instantiate()
	root.add_child(demo)
	_run.call_deferred(demo)


func _run(demo) -> void:
	await process_frame
	# hide the test-bench buttons, show a clean caption instead
	for c in demo.get_children():
		if c is CanvasLayer:
			c.visible = false
	var layer := CanvasLayer.new()
	demo.add_child(layer)
	caption = Label.new()
	caption.add_theme_font_size_override("font_size", 40)
	caption.add_theme_color_override("font_color", Color(0.22, 0.17, 0.32))
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	caption.set_anchors_preset(Control.PRESET_TOP_WIDE)
	caption.position.y = 30
	layer.add_child(caption)
	var av: HarveyAvatar = demo.avatar
	for s in STEPS:
		caption.text = s[0]
		if demo._framing != s[4]:
			demo._framing = s[4]
			demo._apply_framing()
		av.set_expression("")
		match s[1]:
			"state": av.set_state(s[2])
			"emote": av.play_emote(s[2])
			"expr": av.set_expression(s[2])
			"speak": av.speak_text(s[2], s[3] - 0.6)
		await create_timer(s[3]).timeout
	quit()
