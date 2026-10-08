shader_type spatial;
render_mode unshaded, depth_draw_never, shadows_disabled, blend_mix;
uniform float strength = 0.35;
void fragment() {
	float d = length((UV - 0.5) * 2.0);
	ALBEDO = vec3(0.25, 0.18, 0.3);
	ALPHA = strength * (1.0 - smoothstep(0.2, 1.0, d));
}
