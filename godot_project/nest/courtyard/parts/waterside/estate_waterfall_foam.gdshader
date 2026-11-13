shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;

uniform vec3 landing_origin;
uniform float landing_width = 2.0;
uniform float presentation_time = 0.0;
uniform float night_visibility = 0.0;
uniform vec3 accent_color = vec3(0.0);
uniform float accent_strength = 0.0;
varying vec3 world_position;

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise2(vec2 p) {
    vec2 cell = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(cell), hash21(cell + vec2(1.0, 0.0)), f.x),
               mix(hash21(cell + vec2(0.0, 1.0)), hash21(cell + vec2(1.0)), f.x), f.y);
}

void vertex() {
    world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
    vec2 p = world_position.xz - landing_origin.xz;
    vec2 flow = vec2(p.x * 13.0 - presentation_time * 2.4, p.y * 10.0);
    float cells = noise2(flow) * 0.65 + noise2(flow * 2.1 + 7.3) * 0.35;
    float white_cells = smoothstep(0.27, 0.62, cells);
    float impact = exp(-pow(p.x / 0.14, 2.0));
    float downstream = exp(-max(p.x, 0.0) * 3.6);
    float spread = 1.0 - smoothstep(landing_width * 0.43, landing_width * 0.5 + 0.05, abs(p.y));
    float edge = smoothstep(-0.21, -0.11, p.x) * (1.0 - smoothstep(0.43, 0.57, p.x));
    ALPHA = clamp(impact * 0.8 + white_cells * downstream * 0.8, 0.0, 0.94) * spread * edge;
    ALBEDO = mix(vec3(0.72, 0.87, 0.90), vec3(0.96, 0.99, 1.0), white_cells);
    NORMAL = normalize(NORMAL + vec3((cells - 0.5) * 0.25, 0.0, (white_cells - 0.5) * 0.16));
    vec3 night_foam = mix(vec3(0.24, 0.30, 0.31), vec3(0.78, 0.88, 0.92), white_cells);
    EMISSION = vec3(0.06) + night_visibility * night_foam * (0.65 + 0.35 * impact);
    ROUGHNESS = 0.72;
    SPECULAR = 0.22;
}
