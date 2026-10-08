// Harvey body + procedural face. One material, one draw call, GLES3/Compatibility-safe.
// Base colour = clean-plate texture (front projection) blended with baked vertex colours
// (COLOR.a = front-visibility weight). Eyes, brows, mouth and blush are drawn analytically in
// reference-image pixel space (UV * tex_size), so they stay crisp at any resolution and are
// fully animatable through the uniforms below (driven by avatar.gd).
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_lambert_wrap, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_disable;
uniform vec2 tex_size = vec2(512.0, 768.0);

group_uniforms eyes;
uniform float blink : hint_range(0.0, 1.0) = 0.0;
uniform float wink_l : hint_range(0.0, 1.0) = 0.0;   // character's left eye (screen right)
uniform float wink_r : hint_range(0.0, 1.0) = 0.0;
uniform float happy_eyes : hint_range(0.0, 1.0) = 0.0;
uniform float eye_wide : hint_range(0.0, 1.0) = 0.0;
uniform vec2 look = vec2(0.0);                        // -1..1, +x = screen right, +y = down
uniform float pupil_size : hint_range(0.6, 1.4) = 1.0;
group_uniforms brows;
uniform float brow_raise : hint_range(-1.0, 1.0) = 0.0;
uniform float brow_inner : hint_range(-1.0, 1.0) = 0.0; // + worried (inner ends up), - focused/cross
uniform float brow_asym : hint_range(-1.0, 1.0) = 0.0;  // + raises the screen-right brow
group_uniforms mouth;
uniform float mouth_open : hint_range(0.0, 1.0) = 0.0;
uniform float mouth_wide : hint_range(-1.0, 1.0) = 0.0; // -1 "oo" .. +1 "ee"
uniform float smile : hint_range(-1.0, 1.0) = 0.35;
uniform float blush : hint_range(0.0, 1.0) = 0.0;
group_uniforms look_and_feel;
uniform vec3 rim_color : source_color = vec3(1.0, 0.86, 0.72);
uniform float rim_strength : hint_range(0.0, 1.0) = 0.22;
uniform float brightness : hint_range(0.5, 1.5) = 1.0;
uniform float self_illum : hint_range(0.0, 1.0) = 0.22;  // lifts shadowed sides toward the soft reference look

const vec3 EYE_LINE = vec3(0.13, 0.07, 0.05);
const vec3 BROW_COL = vec3(0.24, 0.19, 0.20);

vec3 lin(vec3 c) { return c * c * (c * 0.305306011 + 0.682171111) + 0.012522878 * c; }  // ~sRGB->linear (cheap)

float seg_dist(vec2 p, vec2 a, vec2 b, out float t) {
	vec2 pa = p - a, ba = b - a;
	t = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
	return length(pa - ba * t);
}

// returns rgb + alpha (premultiplied-free) for one eye; also writes a highlight mask for emission
vec4 eye(vec2 p, vec2 c, vec2 r, vec2 iris_c, float closed, float aa, out float hl) {
	hl = 0.0;
	r *= 1.0 + 0.07 * eye_wide;
	vec2 q = (p - c) / r;
	float rmin = min(r.x, r.y);
	float d = length(q);
	float sd = (d - 1.0) * rmin;                       // ~signed px distance to eye outline
	float inside = 1.0 - smoothstep(-aa, aa, sd);
	if (sd > 3.0 + aa) { return vec4(0.0); }
	// lids (q-space): upper lid comes down to a smile-arc closed line; lower lid rises for happy eyes
	float yl = mix(-1.2, 0.18, closed) - 0.3 * closed * q.x * q.x;
	float ll = mix(1.2, 0.08, happy_eyes) - 0.75 * happy_eyes * (1.0 - q.x * q.x);
	float open_m = smoothstep(yl * r.y - aa, yl * r.y + aa, q.y * r.y) * (1.0 - smoothstep(ll * r.y - aa, ll * r.y + aa, q.y * r.y));
	// sclera with lid shadow
	vec3 col = lin(vec3(0.98, 0.96, 0.94)) * mix(0.72, 1.0, smoothstep(yl - 0.05, yl + 0.55, q.y));
	// iris
	float ri = 24.5 * (1.0 + 0.07 * eye_wide);
	float di = length(p - iris_c) / ri;
	vec3 iris = mix(lin(vec3(0.66, 0.41, 0.21)), lin(vec3(0.33, 0.17, 0.08)), smoothstep(0.35, 0.95, di));
	iris += lin(vec3(0.16, 0.09, 0.03)) * smoothstep(0.0, 0.9, (p.y - iris_c.y) / ri);
	iris *= mix(1.0, 0.45, smoothstep(0.84, 0.98, di));
	col = mix(col, iris, 1.0 - smoothstep(1.0 - aa / ri, 1.0 + aa / ri, di));
	float rp = 0.6 * pupil_size * (1.0 - 0.18 * eye_wide);
	col = mix(col, lin(vec3(0.05, 0.03, 0.03)), 1.0 - smoothstep(rp - aa / ri, rp + aa / ri, di));
	// specular highlights (reflections stay roughly put, follow the iris a little)
	vec2 hc = iris_c + vec2(-0.36, -0.40) * ri;
	float h1 = 1.0 - smoothstep(0.27 * ri - aa, 0.27 * ri + aa, length((p - hc) * vec2(1.0, 1.12)));
	float h2 = 1.0 - smoothstep(0.10 * ri - aa, 0.10 * ri + aa, length(p - (iris_c + vec2(0.4, 0.08) * ri)));
	hl = max(h1, h2 * 0.9) * open_m * inside;
	col = mix(col, vec3(1.0), max(h1, h2 * 0.9));
	// outline ring
	col = mix(col, lin(EYE_LINE), 1.0 - smoothstep(0.9, 0.9 + aa, abs(sd + 1.3) - 0.4));
	// happy eyes collapse to a dark arc
	col = mix(col, lin(EYE_LINE), smoothstep(0.45, 0.85, happy_eyes));
	float a = inside * open_m;
	// lash line along the upper lid when (partly) closed, and along the lower lid when happy
	float lash_w = 1.1 + 1.2 * closed;
	float on_ell = 1.0 - smoothstep(1.0, 1.06, abs(q.x));
	float lash = (1.0 - smoothstep(lash_w, lash_w + aa, abs((q.y - yl) * r.y))) * step(0.03, closed);
	lash = max(lash, (1.0 - smoothstep(1.4, 1.4 + aa, abs((q.y - ll) * r.y))) * step(0.03, happy_eyes) * step(yl, q.y));
	lash *= on_ell * (1.0 - smoothstep(-0.2, 0.2 + aa / rmin, d - 1.0));
	col = mix(col, lin(EYE_LINE), lash);
	a = max(a, lash);
	return vec4(col, a);
}

vec4 brow(vec2 p, vec2 p0, vec2 p1, vec2 p2, float aa) {
	// distance to a quadratic Bezier, sampled as a 10-segment polyline (p0 = outer end, p2 = inner end)
	float best = 1e5; float bt = 0.0;
	vec2 prev = p0;
	for (int i = 1; i <= 10; i++) {
		float t = float(i) / 10.0;
		vec2 cur = mix(mix(p0, p1, t), mix(p1, p2, t), t);
		float st;
		float dd = seg_dist(p, prev, cur, st);
		if (dd < best) { best = dd; bt = (float(i) - 1.0 + st) / 10.0; }
		prev = cur;
	}
	float th = 2.4 + 3.4 * sin(3.14159 * (0.1 + 0.8 * bt));
	float a = 1.0 - smoothstep(th - aa, th + aa, best);
	return vec4(lin(BROW_COL), a);
}

void fragment() {
	vec3 tex = texture(albedo_tex, UV).rgb;
	vec3 base = mix(COLOR.rgb, tex, COLOR.a);
	vec3 col = base;
	float rough = 0.78;
	float glow = 0.0;
	vec2 p = UV * tex_size;
	if (UV2.x > 0.5 && p.x > 135.0 && p.x < 375.0 && p.y > 145.0 && p.y < 345.0) {
		float aa = max(fwidth(p.x), fwidth(p.y)) * 0.75 + 0.15;
		// --- blush
		float b1 = length((p - vec2(168.0, 290.0)) / vec2(26.0, 14.0));
		float b2 = length((p - vec2(338.0, 284.0)) / vec2(26.0, 14.0));
		col = mix(col, lin(vec3(1.0, 0.48, 0.52)), blush * 0.42 * (1.0 - smoothstep(0.2, 1.0, min(b1, b2))));
		// --- eyes (screen-left = character's right)
		vec2 lk = clamp(look, vec2(-1.0), vec2(1.0)) * vec2(6.5, 4.5);
		float h;
		vec4 e = eye(p, vec2(190.0, 237.0), vec2(30.0, 29.0), vec2(193.0, 240.0) + lk, clamp(max(blink, wink_r), 0.0, 1.0), aa, h);
		col = mix(col, e.rgb, e.a); glow = max(glow, h); rough = mix(rough, 0.25, e.a);
		e = eye(p, vec2(315.0, 232.0), vec2(31.0, 28.0), vec2(311.0, 234.0) + lk, clamp(max(blink, wink_l), 0.0, 1.0), aa, h);
		col = mix(col, e.rgb, e.a); glow = max(glow, h); rough = mix(rough, 0.25, e.a);
		// --- brows
		float br = brow_raise * 9.0, bi = brow_inner * 8.0;
		vec4 bw = brow(p, vec2(165.0, 196.0 - br + 3.0 * bi * 0.4 + 3.0 * brow_asym),
				vec2(187.0, 168.0 - br - 0.3 * bi + 3.0 * brow_asym),
				vec2(207.0, 174.0 - br - bi + 3.0 * brow_asym), aa);
		col = mix(col, bw.rgb, bw.a);
		bw = brow(p, vec2(337.0, 189.0 - br + 3.0 * bi * 0.4 - 7.0 * brow_asym),
				vec2(310.0, 164.0 - br - 0.3 * bi - 7.0 * brow_asym),
				vec2(289.0, 170.0 - br - bi - 7.0 * brow_asym), aa);
		col = mix(col, bw.rgb, bw.a);
		// --- mouth
		vec2 mc = vec2(256.0, 306.0);
		float hw = 44.0 * (1.0 + 0.16 * mouth_wide);
		float x = (p.x - mc.x) / hw;
		if (abs(x) < 1.15 && abs(p.y - mc.y) < 40.0) {
			float yup = mc.y + smile * (2.5 - 10.0 * x * x);
			float xo = mix(0.6, 0.34, max(-mouth_wide, 0.0)) * (1.0 + 0.2 * max(mouth_wide, 0.0));
			float u = clamp(x / xo, -1.0, 1.0);
			float shape = max(1.0 - u * u, 0.0);
			float open_amt = mouth_open * step(abs(x), xo);
			float y_top = yup - mouth_open * 3.0 * shape;
			float y_bot = yup + mouth_open * (24.0 - 6.0 * max(mouth_wide, 0.0)) * pow(shape, 0.6);
			// interior + tongue
			float inside = smoothstep(y_top - aa, y_top + aa, p.y) * (1.0 - smoothstep(y_bot - aa, y_bot + aa, p.y)) * step(0.02, open_amt);
			vec3 mcol = lin(vec3(0.30, 0.07, 0.09));
			float tg = length((p - vec2(mc.x, y_bot - 2.0)) / vec2(xo * hw * 0.62, max(9.0 * mouth_open, 0.01)));
			mcol = mix(mcol, lin(vec3(0.90, 0.43, 0.46)), (1.0 - smoothstep(0.85, 1.0, tg)) * smoothstep(0.15, 0.4, mouth_open));
			col = mix(col, mcol, inside);
			// smile line (always) with tapered ends, plus outline of the opening
			float slope = smile * (-20.0 * x) / hw;
			float dl = abs(p.y - yup) / sqrt(1.0 + slope * slope);
			float th = 0.55 + 1.15 * (1.0 - smoothstep(0.7, 1.08, abs(x)));
			float line_a = (1.0 - smoothstep(th - aa, th + aa, dl)) * (1.0 - smoothstep(1.0, 1.1, abs(x)));
			float edge = (1.0 - smoothstep(0.9, 0.9 + aa, abs(p.y - y_bot))) * step(0.02, open_amt) * step(abs(x), xo * 0.98);
			col = mix(col, lin(EYE_LINE * 1.3), max(line_a * (1.0 - inside * 0.6), edge * 0.8));
		}
	}
	ALBEDO = col * brightness;
	ROUGHNESS = rough;
	SPECULAR = mix(0.12, 0.5, glow);
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	EMISSION = rim_color * rim_strength * fres * base + vec3(0.35) * glow + col * brightness * self_illum;
}
