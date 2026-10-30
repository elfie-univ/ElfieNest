shader_type sky;

// The same environment color drives the visible background and distant
// reflections. Nearby fixture highlights still come from the actual lights.
// Compatibility's sky pass decodes these canvas sRGB values itself.
uniform vec4 environment_color = vec4(0.72, 0.78, 0.81, 1.0);

void sky() {
	COLOR = environment_color.rgb;
}
