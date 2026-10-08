class_name HarveyAvatar
extends Node3D
## Harvey — animated AI-assistant avatar.
##
## Quick use from your assistant code:
##   avatar.set_state("listening")          # idle | listening | thinking | talking | happy | sad
##   avatar.play_emote("wave")              # wave | nod | shake | surprised | celebrate
##   avatar.speak(audio_stream)             # plays TTS audio with automatic lip-sync
##   avatar.speak_text("Hello!", 1.4)       # lip-sync only (when TTS audio plays elsewhere)
##   avatar.set_lipsync(open, wide)         # drive the mouth yourself (visemes), see external_lipsync
##   avatar.look_at_point(world_pos)        # head + eyes track a point; clear_look() to release
##   avatar.set_expression("happy")         # override the face preset of the current state

signal state_changed(state: String)
signal emote_started(emote: String)
signal emote_finished(emote: String)
signal speech_started
signal speech_finished

const STATE_ANIM := {
	"idle": "idle", "listening": "listen", "thinking": "think",
	"talking": "talk", "happy": "happy", "sad": "sad",
}
const STATE_FACE := {
	"idle": "neutral", "listening": "listening", "thinking": "thinking",
	"talking": "talking", "happy": "happy", "sad": "sad",
}
const EMOTES := ["wave", "nod", "shake", "surprised", "celebrate"]
const EMOTE_FACE := {"wave": "happy", "nod": "", "shake": "", "surprised": "surprised", "celebrate": "joy"}

## Face presets → shader uniforms. "lid" = resting upper-lid closure, "mouth"/"mouth_wide" = resting mouth.
const EXPRESSIONS := {
	"neutral":   {"smile": 0.35, "brow_raise": 0.0, "brow_inner": 0.0, "brow_asym": 0.0, "happy_eyes": 0.0, "eye_wide": 0.0, "pupil_size": 1.0, "blush": 0.0, "lid": 0.0, "mouth": 0.0, "mouth_wide": 0.0},
	"listening": {"smile": 0.25, "brow_raise": 0.35, "brow_inner": 0.1, "brow_asym": 0.0, "happy_eyes": 0.0, "eye_wide": 0.25, "pupil_size": 1.1, "blush": 0.0, "lid": 0.0, "mouth": 0.0, "mouth_wide": 0.0},
	"thinking":  {"smile": 0.05, "brow_raise": 0.1, "brow_inner": -0.25, "brow_asym": 0.9, "happy_eyes": 0.0, "eye_wide": 0.0, "pupil_size": 0.95, "blush": 0.0, "lid": 0.18, "mouth": 0.0, "mouth_wide": -0.3},
	"talking":   {"smile": 0.45, "brow_raise": 0.15, "brow_inner": 0.0, "brow_asym": 0.0, "happy_eyes": 0.0, "eye_wide": 0.05, "pupil_size": 1.0, "blush": 0.0, "lid": 0.0, "mouth": 0.0, "mouth_wide": 0.0},
	"happy":     {"smile": 1.0, "brow_raise": 0.35, "brow_inner": 0.0, "brow_asym": 0.0, "happy_eyes": 0.0, "eye_wide": 0.1, "pupil_size": 1.12, "blush": 0.55, "lid": 0.0, "mouth": 0.12, "mouth_wide": 0.5},
	"joy":       {"smile": 1.0, "brow_raise": 0.55, "brow_inner": 0.0, "brow_asym": 0.0, "happy_eyes": 1.0, "eye_wide": 0.0, "pupil_size": 1.0, "blush": 0.75, "lid": 0.0, "mouth": 0.45, "mouth_wide": 0.4},
	"sad":       {"smile": -0.65, "brow_raise": 0.1, "brow_inner": 0.95, "brow_asym": 0.0, "happy_eyes": 0.0, "eye_wide": 0.0, "pupil_size": 1.18, "blush": 0.0, "lid": 0.32, "mouth": 0.0, "mouth_wide": -0.2},
	"surprised": {"smile": 0.0, "brow_raise": 1.0, "brow_inner": 0.2, "brow_asym": 0.0, "happy_eyes": 0.0, "eye_wide": 1.0, "pupil_size": 0.75, "blush": 0.0, "lid": 0.0, "mouth": 0.5, "mouth_wide": -0.85},
}

@export var start_state := "idle"
@export var auto_blink := true
@export var look_at_camera := true            ## eyes/head favour the active camera (the user)
@export var idle_look_around := true          ## occasional glances while idle
@export var external_lipsync := false         ## true → only set_lipsync() moves the mouth
@export_range(0.05, 1.0) var crossfade := 0.35
@export var voice_bus := "HarveyVoice"

var state := ""
var current_emote := ""

var _ap: AnimationPlayer
var _skel: Skeleton3D
var _body: MeshInstance3D
var _mat: ShaderMaterial
var _look: HarveyHeadLook
var _voice: AudioStreamPlayer
var _analyzer: AudioEffectSpectrumAnalyzerInstance

var _expr_override := ""
var _face := {}
var _face_target := {}
var _blink := 0.0
var _blink_t := 0.0
var _next_blink := 2.0
var _double_blink := false
var _gaze := Vector2.ZERO
var _gaze_target := Vector2.ZERO
var _next_saccade := 1.0
var _look_point_set := false
var _look_point := Vector3.ZERO
var _glance_t := 0.0
var _glance_point := Vector3.ZERO
var _mouth := 0.0
var _mouth_w := 0.0
var _ext_open := 0.0
var _ext_wide := 0.0
var _speaking_audio := false
var _syllables: Array = []   # [[t0, t1, open, wide], ...]
var _speech_t := -1.0
var _speech_len := 0.0
var _state_before_speech := "idle"
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.randomize()
	_ap = find_child("AnimationPlayer", true, false)
	_skel = find_child("Skeleton3D", true, false)
	_body = find_child("Body", true, false)
	assert(_ap and _skel and _body, "HarveyAvatar: model (harvey.glb) must be a child of this node")
	_mat = (load("res://avatar/harvey_material.tres") as ShaderMaterial).duplicate()
	_body.material_override = _mat
	for a in STATE_ANIM.values():
		_ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
	_ap.animation_finished.connect(_on_animation_finished)
	_look = HarveyHeadLook.new()
	_look.name = "HeadLook"
	_skel.add_child(_look)
	_setup_voice()
	for k in EXPRESSIONS["neutral"]:
		_face[k] = EXPRESSIONS["neutral"][k]
	set_state(start_state)
	_face = _face_target.duplicate()
	_apply_face()


# ------------------------------------------------------------------------------------------ API
func set_state(new_state: String) -> void:
	if not STATE_ANIM.has(new_state):
		push_warning("HarveyAvatar: unknown state '%s'" % new_state)
		return
	var changed := new_state != state
	state = new_state
	if current_emote == "":
		_ap.play(STATE_ANIM[state], crossfade)
	_refresh_face_target()
	_next_saccade = 0.0
	if changed:
		state_changed.emit(state)


func play_emote(emote: String) -> void:
	if not emote in EMOTES:
		push_warning("HarveyAvatar: unknown emote '%s'" % emote)
		return
	current_emote = emote
	_ap.play(emote, 0.2)
	_refresh_face_target()
	emote_started.emit(emote)


func set_expression(expr: String) -> void:
	## Force a face preset ("" returns to the state's own preset).
	if expr != "" and not EXPRESSIONS.has(expr):
		push_warning("HarveyAvatar: unknown expression '%s'" % expr)
		return
	_expr_override = expr
	_refresh_face_target()


func speak(stream: AudioStream, return_state := "idle") -> void:
	## Play TTS audio with amplitude/spectrum-driven lip-sync.
	_syllables.clear()
	_speech_t = -1.0
	_voice.stream = stream
	_voice.play()
	_speaking_audio = true
	_begin_speech(return_state)


func speak_text(text: String, duration := -1.0, return_state := "idle") -> void:
	## Procedural lip-sync from text (use when audio is played by another system, e.g. Android TTS).
	## duration < 0 → estimated from text at a natural speaking rate.
	_build_syllables(text, duration)
	_speech_t = 0.0
	_speaking_audio = false
	_begin_speech(return_state)


func stop_speaking() -> void:
	if _voice.playing:
		_voice.stop()
	_end_speech()


func is_speaking() -> bool:
	return _speaking_audio or _speech_t >= 0.0


func set_lipsync(open: float, wide := 0.0) -> void:
	## External viseme/amplitude input (0..1 open, -1 "oo" .. +1 "ee"). Enable external_lipsync.
	_ext_open = clamp(open, 0.0, 1.0)
	_ext_wide = clamp(wide, -1.0, 1.0)


func look_at_point(world_pos: Vector3) -> void:
	_look_point_set = true
	_look_point = world_pos


func clear_look() -> void:
	_look_point_set = false


func blink_now() -> void:
	## Trigger a blink immediately (e.g. on a UI event).
	_next_blink = 0.0


func set_face_param(param: String, value: float) -> void:
	## Low-level access to any shader uniform (see harvey_face.gdshader).
	_mat.set_shader_parameter(param, value)


# ------------------------------------------------------------------------------------ internals
func _begin_speech(return_state: String) -> void:
	_state_before_speech = return_state
	if state != "talking":
		set_state("talking")
	speech_started.emit()


func _end_speech() -> void:
	var was := is_speaking()
	_speaking_audio = false
	_speech_t = -1.0
	_syllables.clear()
	if state == "talking":
		set_state(_state_before_speech)
	if was:
		speech_finished.emit()


func _on_animation_finished(anim: StringName) -> void:
	if current_emote != "" and String(anim) == current_emote:
		var e := current_emote
		current_emote = ""
		_ap.play(STATE_ANIM[state], crossfade)
		_refresh_face_target()
		emote_finished.emit(e)


func _refresh_face_target() -> void:
	var name: String = STATE_FACE[state] if state != "" else "neutral"
	if current_emote != "" and EMOTE_FACE.get(current_emote, "") != "":
		name = String(EMOTE_FACE[current_emote])
	if _expr_override != "":
		name = _expr_override
	_face_target = EXPRESSIONS[name].duplicate()


func _setup_voice() -> void:
	var idx := AudioServer.get_bus_index(voice_bus)
	if idx == -1:
		AudioServer.add_bus()
		idx = AudioServer.bus_count - 1
		AudioServer.set_bus_name(idx, voice_bus)
		AudioServer.set_bus_send(idx, "Master")
	var has := false
	for i in AudioServer.get_bus_effect_count(idx):
		if AudioServer.get_bus_effect(idx, i) is AudioEffectSpectrumAnalyzer:
			_analyzer = AudioServer.get_bus_effect_instance(idx, i)
			has = true
	if not has:
		var fx := AudioEffectSpectrumAnalyzer.new()
		fx.buffer_length = 0.1
		fx.fft_size = AudioEffectSpectrumAnalyzer.FFT_SIZE_512
		AudioServer.add_bus_effect(idx, fx)
		_analyzer = AudioServer.get_bus_effect_instance(idx, AudioServer.get_bus_effect_count(idx) - 1)
	_voice = AudioStreamPlayer.new()
	_voice.name = "Voice"
	_voice.bus = voice_bus
	add_child(_voice)
	_voice.finished.connect(func(): if _speaking_audio: _end_speech())


func _build_syllables(text: String, duration: float) -> void:
	_syllables.clear()
	var re := RegEx.new()
	re.compile("[aeiouy]+")
	var t := 0.0
	var syl_len := 0.2
	var units: Array = []  # [kind, vowel] kind: 0 syllable, 1 short pause, 2 long pause
	for raw in text.to_lower().split(" ", false):
		var w: String = raw
		var vowels := re.search_all(w)
		if vowels.is_empty() and w.strip_edges(true, true).length() > 0:
			units.append([0, "a"])
		for v in vowels:
			units.append([0, v.get_string()])
		if w.ends_with(",") or w.ends_with(";") or w.ends_with(":"):
			units.append([1, ""])
		elif w.ends_with(".") or w.ends_with("!") or w.ends_with("?"):
			units.append([2, ""])
	var n_syl := 0.0
	var pause := 0.0
	for u in units:
		if u[0] == 0: n_syl += 1.0
		elif u[0] == 1: pause += 0.22
		else: pause += 0.4
	if duration > 0.0 and n_syl > 0.0:
		syl_len = max((duration - pause * 0.7) / n_syl, 0.08)
		pause *= 0.7
	for u in units:
		if u[0] == 0:
			var v: String = u[1]
			var wide := 0.1
			if v.begins_with("o") or v.begins_with("u"): wide = -0.75
			elif v.begins_with("e") or v.begins_with("i") or v.begins_with("y"): wide = 0.6
			var d := syl_len * _rng.randf_range(0.8, 1.2)
			_syllables.append([t, t + d, _rng.randf_range(0.45, 0.95), wide])
			t += d
		else:
			t += 0.22 if u[0] == 1 else 0.4
	_speech_len = t


func _process(delta: float) -> void:
	_update_speech(delta)
	_update_blink(delta)
	_update_gaze(delta)
	# ease face toward its target (expressions blend in ~0.25 s)
	var k := 1.0 - exp(-delta * 9.0)
	for key in _face_target:
		_face[key] = lerp(float(_face[key]), float(_face_target[key]), k)
	_apply_face()


func _update_speech(delta: float) -> void:
	var open := 0.0
	var wide := 0.0
	if external_lipsync:
		open = _ext_open
		wide = _ext_wide
	elif _speaking_audio and _analyzer:
		var lo := _analyzer.get_magnitude_for_frequency_range(120.0, 900.0).length()
		var mid := _analyzer.get_magnitude_for_frequency_range(900.0, 2500.0).length()
		var hi := _analyzer.get_magnitude_for_frequency_range(2500.0, 6000.0).length()
		var energy := lo + mid + hi
		open = clamp((linear_to_db(energy + 1e-6) + 50.0) / 32.0, 0.0, 1.0)
		wide = clamp((mid + 1.6 * hi - 1.1 * lo) / (energy + 1e-5), -1.0, 1.0) * 0.8
	elif _speech_t >= 0.0:
		_speech_t += delta
		for s in _syllables:
			if _speech_t >= s[0] and _speech_t < s[1]:
				var ph: float = (_speech_t - s[0]) / (s[1] - s[0])
				open = s[2] * sin(PI * ph)
				wide = s[3]
				break
		if _speech_t > _speech_len + 0.1:
			_end_speech()
	# fast attack, slower release reads as natural speech
	var rate := 28.0 if open > _mouth else 14.0
	_mouth = lerp(_mouth, open, 1.0 - exp(-delta * rate))
	_mouth_w = lerp(_mouth_w, wide, 1.0 - exp(-delta * 12.0))


func _update_blink(delta: float) -> void:
	if not auto_blink:
		_blink = 0.0
		return
	_next_blink -= delta
	if _next_blink <= 0.0 and _blink_t <= 0.0:
		_blink_t = 0.001
	if _blink_t > 0.0:
		_blink_t += delta
		var close_t := 0.06
		var open_t := 0.1
		if _blink_t < close_t:
			_blink = _blink_t / close_t
		elif _blink_t < close_t + 0.03:
			_blink = 1.0
		elif _blink_t < close_t + 0.03 + open_t:
			_blink = 1.0 - (_blink_t - close_t - 0.03) / open_t
		else:
			_blink = 0.0
			_blink_t = 0.0
			if not _double_blink and _rng.randf() < 0.18:
				_double_blink = true
				_next_blink = 0.12
			else:
				_double_blink = false
				_next_blink = _rng.randf_range(2.0, 5.5)


func _update_gaze(delta: float) -> void:
	var cam := get_viewport().get_camera_3d()
	# head target
	var head_amt := 0.0
	var target := Vector3.ZERO
	if _look_point_set:
		target = _look_point
		head_amt = 1.0
	elif current_emote == "" and cam and look_at_camera and state in ["listening", "talking"]:
		target = cam.global_position
		head_amt = 0.55
	elif idle_look_around and state == "idle" and current_emote == "":
		_glance_t -= delta
		if _glance_t <= 0.0:
			if _rng.randf() < 0.45:
				_glance_point = global_transform * Vector3(_rng.randf_range(-1.6, 1.6), _rng.randf_range(0.2, 1.4), 2.0)
			else:
				_glance_point = Vector3.INF
			_glance_t = _rng.randf_range(2.5, 6.0)
		if _glance_point != Vector3.INF:
			target = _glance_point
			head_amt = 0.6
	_look.amount = lerp(_look.amount, head_amt, 1.0 - exp(-delta * 3.0))
	if head_amt > 0.0:
		_look.target_position = target
	# eye saccades: small jumps, eyes lead the head
	_next_saccade -= delta
	if _next_saccade <= 0.0:
		var base := Vector2.ZERO
		if state == "thinking" and current_emote == "":
			base = Vector2(0.55, -0.75)
		elif head_amt > 0.0 and target != Vector3.INF:
			var local := global_transform.affine_inverse() * target
			base = Vector2(clamp(local.x * 0.9, -1.0, 1.0), clamp(-(local.y - 0.3) * 0.6, -1.0, 1.0))
		var jitter := 0.25 if state in ["idle", "thinking"] else 0.12
		_gaze_target = base + Vector2(_rng.randf_range(-jitter, jitter), _rng.randf_range(-jitter, jitter) * 0.6)
		_next_saccade = _rng.randf_range(0.6, 2.4)
	_gaze = _gaze.lerp(_gaze_target, 1.0 - exp(-delta * 22.0))


func _apply_face() -> void:
	var m := _mat
	m.set_shader_parameter("smile", _face["smile"])
	m.set_shader_parameter("brow_raise", _face["brow_raise"])
	m.set_shader_parameter("brow_inner", _face["brow_inner"])
	m.set_shader_parameter("brow_asym", _face["brow_asym"])
	m.set_shader_parameter("happy_eyes", _face["happy_eyes"])
	m.set_shader_parameter("eye_wide", _face["eye_wide"])
	m.set_shader_parameter("pupil_size", _face["pupil_size"])
	m.set_shader_parameter("blush", _face["blush"])
	m.set_shader_parameter("blink", clamp(max(_blink, _face["lid"]), 0.0, 1.0))
	m.set_shader_parameter("look", _gaze)
	var talking := _mouth > 0.01
	m.set_shader_parameter("mouth_open", clamp(max(_mouth, _face["mouth"]), 0.0, 1.0))
	m.set_shader_parameter("mouth_wide", _mouth_w if talking else _face["mouth_wide"])
