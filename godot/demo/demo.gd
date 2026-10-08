extends Node3D
## Demo / test bench for the Harvey avatar. Tap buttons to drive states and emotes,
## tap the character area to make Harvey look there.

const FRAMING := {
	"full": {"pos": Vector3(0, 0.72, 5.3), "fov": 30.0},
	"portrait": {"pos": Vector3(0, 1.3, 3.7), "fov": 30.0},
}

var avatar: HarveyAvatar
var cam: Camera3D
var fps_label: Label
var _framing := "full"


func _ready() -> void:
	_build_world()
	avatar = (load("res://avatar/harvey.tscn") as PackedScene).instantiate()
	add_child(avatar)
	_build_ui()
	avatar.emote_finished.connect(func(e): print("emote finished: ", e))


func _build_world() -> void:
	cam = Camera3D.new()
	cam.current = true
	add_child(cam)
	_apply_framing()
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-32, 28, 0)
	sun.light_energy = 0.7
	sun.light_color = Color(1.0, 0.97, 0.93)
	sun.shadow_enabled = false
	add_child(sun)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-10, -150, 0)
	fill.light_energy = 0.55
	fill.light_color = Color(0.8, 0.82, 1.0)
	add_child(fill)
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.86, 0.84, 0.93)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.96, 0.93, 0.97)
	env.ambient_light_energy = 0.6
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var back := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(14, 14)
	back.mesh = q
	var bm := ShaderMaterial.new()
	bm.shader = load("res://demo/backdrop.gdshader")
	back.material_override = bm
	back.position = Vector3(0, 1.0, -4.0)
	add_child(back)
	var blob := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(1.5, 1.0)
	blob.mesh = pm
	var sm := ShaderMaterial.new()
	sm.shader = load("res://demo/blob_shadow.gdshader")
	blob.material_override = sm
	blob.position = Vector3(0.05, 0.004, 0.0)
	add_child(blob)


func _apply_framing() -> void:
	var f: Dictionary = FRAMING[_framing]
	cam.position = f["pos"]
	cam.fov = f["fov"]


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var root := MarginContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "bottom", "top"]:
		root.add_theme_constant_override("margin_" + side, 16)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)
	var col := VBoxContainer.new()
	col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(col)
	fps_label = Label.new()
	fps_label.add_theme_font_size_override("font_size", 22)
	fps_label.add_theme_color_override("font_color", Color(0.25, 0.2, 0.35))
	col.add_child(fps_label)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	col.add_child(spacer)
	_add_row(col, ["idle", "listening", "thinking", "talking", "happy", "sad"], func(s): avatar.set_state(s))
	_add_row(col, ["wave", "nod", "shake", "surprised", "celebrate"], func(e): avatar.play_emote(e))
	_add_row(col, ["speak demo", "zoom"], func(a):
		if a == "speak demo":
			avatar.speak_text("Hi there! I'm Harvey, your assistant. How can I help you today?")
		else:
			_framing = "portrait" if _framing == "full" else "full"
			_apply_framing())


func _add_row(parent: Control, items: Array, cb: Callable) -> void:
	var flow := HFlowContainer.new()
	flow.add_theme_constant_override("h_separation", 8)
	flow.add_theme_constant_override("v_separation", 8)
	parent.add_child(flow)
	for it in items:
		var b := Button.new()
		b.text = String(it).capitalize()
		b.custom_minimum_size = Vector2(160, 64)
		b.add_theme_font_size_override("font_size", 24)
		b.pressed.connect(cb.bind(it))
		flow.add_child(b)


func _process(_delta: float) -> void:
	fps_label.text = "%d FPS  |  state: %s %s" % [Engine.get_frames_per_second(), avatar.state,
			("| " + avatar.current_emote) if avatar.current_emote != "" else ""]


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch and event.pressed or event is InputEventMouseButton and event.pressed:
		var pos: Vector2 = event.position
		var origin := cam.project_ray_origin(pos)
		var dir := cam.project_ray_normal(pos)
		var t := (1.5 - origin.z) / dir.z  # plane in front of Harvey
		avatar.look_at_point(origin + dir * t)
		get_tree().create_timer(2.5).timeout.connect(avatar.clear_look)
