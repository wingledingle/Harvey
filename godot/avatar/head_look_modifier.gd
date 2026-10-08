@tool
class_name HarveyHeadLook
extends SkeletonModifier3D
## Procedural look-at layered on top of whatever animation is playing.
## Splits the turn between neck and head, clamps it, and eases in/out smoothly.

@export var target_position := Vector3.ZERO   ## World-space point to look at.
@export_range(0.0, 1.0) var amount := 0.0      ## 0 = animation only, 1 = fully tracking.
@export var max_yaw_deg := 38.0
@export var max_pitch_up_deg := 22.0
@export var max_pitch_down_deg := 16.0
@export_range(0.0, 1.0) var neck_share := 0.3

var _head := -1
var _neck := -1
var _yaw := 0.0
var _pitch := 0.0


func _ready() -> void:
	_cache()


func _cache() -> void:
	var sk := get_skeleton()
	if sk:
		_head = sk.find_bone("head")
		_neck = sk.find_bone("neck")


func _process_modification() -> void:
	var sk := get_skeleton()
	if sk == null:
		return
	if _head < 0:
		_cache()
		if _head < 0:
			return
	var want_yaw := 0.0
	var want_pitch := 0.0
	if amount > 0.001:
		var head_pos := sk.get_bone_global_pose(_head).origin + Vector3(0, 0.25, 0)  # roughly the eyes
		var local_target := sk.global_transform.affine_inverse() * target_position
		var d := (local_target - head_pos).normalized()
		want_yaw = clamp(atan2(d.x, d.z), deg_to_rad(-max_yaw_deg), deg_to_rad(max_yaw_deg)) * amount
		want_pitch = clamp(-asin(clamp(d.y, -1.0, 1.0)), deg_to_rad(-max_pitch_up_deg), deg_to_rad(max_pitch_down_deg)) * amount
	# critically damped-ish smoothing, frame-rate independent
	var dt := get_process_delta_time() if is_inside_tree() else 0.016
	var k := 1.0 - exp(-dt * 7.0)
	_yaw = lerp(_yaw, want_yaw, k)
	_pitch = lerp(_pitch, want_pitch, k)
	if abs(_yaw) < 1e-4 and abs(_pitch) < 1e-4:
		return
	var parts := [[_neck, neck_share], [_head, 1.0 - neck_share]]
	for p in parts:
		var idx: int = p[0]
		if idx < 0:
			continue
		var w: float = p[1]
		var extra := Quaternion(Vector3.UP, _yaw * w) * Quaternion(Vector3.RIGHT, _pitch * w)
		sk.set_bone_pose_rotation(idx, extra * sk.get_bone_pose_rotation(idx))
