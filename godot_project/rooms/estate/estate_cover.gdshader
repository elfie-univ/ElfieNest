shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, unshaded;

uniform vec4 cover_tint : source_color;
uniform float cover_level = 0.0;
uniform float face_opacity;
uniform float edge_opacity;
uniform float face_glow;
uniform float edge_glow;
uniform float edge_pulse = 0.0;

void fragment() {
	// Reuse the fitted surface normals. Absolute facing keeps both sides and
	// the authored mirrored bed frame symmetric without changing geometry.
	float facing = abs(dot(normalize(NORMAL), normalize(VIEW)));
	float arc = pow(1.0 - clamp(facing, 0.0, 1.0), 2.0);
	ALBEDO = cover_tint.rgb;
	EMISSION = cover_tint.rgb * mix(face_glow, edge_glow, arc) * cover_level;
	// External-body embodiment signal: brighten the existing curved edge only.
	// Keep the approved tint/opacity and avoid an extra floating scanning ring.
	vec3 signal_tint = mix(cover_tint.rgb, vec3(0.42, 0.90, 1.0), 0.65);
	float rim_signal = pow(arc, 0.55) * edge_pulse * 0.85;
	ALBEDO = mix(cover_tint.rgb, vec3(0.48, 0.95, 1.0), rim_signal);
	EMISSION += signal_tint * arc * edge_pulse * 0.9 * cover_level;
	ALPHA = mix(face_opacity, edge_opacity, arc) * cover_level;
}
