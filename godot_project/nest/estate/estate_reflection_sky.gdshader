shader_type sky;

// Retain the reviewed reflection input independently of the visible night sky.
// Compatibility's sky pass decodes these canvas sRGB values itself.
uniform vec4 environment_color = vec4(0.72, 0.78, 0.81, 1.0);
uniform float night_amount : hint_range(0.0, 1.0) = 0.0;

#include "res://nest/estate/estate_night_sky.gdshaderinc"

void sky() {
	COLOR = environment_color.rgb;
	// The visible night sky is independent of the approved room illumination
	// and reflection cubemap. Daytime keeps its existing sky geometry.
	if (night_amount > 0.5 && !AT_CUBEMAP_PASS) {
		COLOR = night_sky(normalize(EYEDIR));
	}
}
