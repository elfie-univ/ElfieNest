shader_type sky;
uniform vec4 sky_color : source_color = vec4(0.843137, 0.921569, 1.0, 1.0);
uniform vec4 ground_color : source_color = vec4(0.352941, 0.407843, 0.364706, 1.0);
void sky() {
	COLOR = mix(ground_color.rgb, sky_color.rgb, EYEDIR.y * 0.5 + 0.5);
}
