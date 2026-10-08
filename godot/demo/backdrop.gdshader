shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled;
uniform vec3 top_color : source_color = vec3(0.80, 0.78, 0.92);
uniform vec3 bottom_color : source_color = vec3(0.93, 0.85, 0.90);
void fragment() {
	float t = smoothstep(0.0, 1.0, UV.y);
	ALBEDO = mix(top_color, bottom_color, t);
}
