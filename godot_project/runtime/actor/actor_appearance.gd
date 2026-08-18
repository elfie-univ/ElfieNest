class_name ActorAppearance
extends RefCounted

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")
const SOURCE_MID_LUMA := {
	"dog": 0.62,
	"fox": 0.56,
}
const BASE_COLLISION_RADIUS := 0.34
const BASE_COLLISION_HEIGHT := 1.72
const APPEARANCE_SHADER_CODE := """
shader_type spatial;
// The GLB's shaded texture already contains its lighting. Re-lighting it as
// albedo and adding emission double-counts the highlights, especially on
// silver/cream palettes. Keep the baked source response in one display path.
render_mode unshaded;

uniform sampler2D base_texture : source_color;
uniform bool use_base_texture = false;
uniform sampler2D source_fur_texture : source_color;
uniform bool use_source_fur_texture = false;
uniform sampler2D appearance_uv_mask : source_color;
uniform bool use_appearance_uv_mask = false;
uniform int appearance_species_id = 0;
uniform float source_detail_strength = 0.92;
uniform float source_mid_luma = 0.37;
uniform float source_emission_strength = 0.0;
uniform vec4 base_color : source_color = vec4(1.0);
uniform vec4 appearance_tint : source_color = vec4(1.0);
uniform bool use_color_slots = false;
uniform vec4 primary_color : source_color = vec4(1.0);
uniform vec4 secondary_color : source_color = vec4(1.0);
uniform vec4 accent_color : source_color = vec4(1.0);
uniform vec4 face_mask_color : source_color = vec4(1.0);
uniform vec4 marking_color : source_color = vec4(1.0);
uniform int appearance_pattern = 0;
uniform int appearance_layout = 0;
uniform int appearance_marking = 0;
uniform int appearance_marking_placement = 0;
uniform vec4 appearance_marking_zone = vec4(0.0);
uniform float appearance_marking_scale = 0.9;
uniform float appearance_marking_intensity = 0.9;
uniform int region_0_id = -1;
uniform int region_1_id = -1;
uniform int region_2_id = -1;
uniform vec4 region_0_color : source_color = vec4(1.0);
uniform vec4 region_1_color : source_color = vec4(1.0);
uniform vec4 region_2_color : source_color = vec4(1.0);
uniform float region_0_source_mid_luma = 0.5;
uniform float region_1_source_mid_luma = 0.5;
uniform float region_2_source_mid_luma = 0.5;
uniform float region_0_intensity = 0.0;
uniform float region_1_intensity = 0.0;
uniform float region_2_intensity = 0.0;
uniform int region_0_grade = 0;
uniform int region_1_grade = 0;
uniform int region_2_grade = 0;

varying vec3 appearance_local_position;
varying vec3 appearance_local_normal;
varying vec3 appearance_region_position;
varying vec3 appearance_region_normal;
varying vec2 appearance_region_uv;
varying float appearance_tail_bone;
varying float appearance_leg_bone;
varying float appearance_lower_leg_bone;
varying float appearance_arm_bone;
varying float appearance_forearm_bone;
varying float appearance_head_bone;
varying float appearance_head_top_bone;

float joint_weight(uvec4 indices, vec4 weights, uint joint_id) {
    return (indices.x == joint_id ? weights.x : 0.0)
        + (indices.y == joint_id ? weights.y : 0.0)
        + (indices.z == joint_id ? weights.z : 0.0)
        + (indices.w == joint_id ? weights.w : 0.0);
}

float joint_weight_range(uvec4 indices, vec4 weights, uint first_id, uint last_id) {
    float result = 0.0;
    result += (indices.x >= first_id && indices.x <= last_id) ? weights.x : 0.0;
    result += (indices.y >= first_id && indices.y <= last_id) ? weights.y : 0.0;
    result += (indices.z >= first_id && indices.z <= last_id) ? weights.z : 0.0;
    result += (indices.w >= first_id && indices.w <= last_id) ? weights.w : 0.0;
    return result;
}

void vertex() {
    // Region thresholds are authored in the evaluated scene-space used by the
    // approved V9 region experiment. This keeps them stable across the GLB's
    // centimetre armature scale and the actor's runtime transform.
    appearance_local_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    appearance_local_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
    appearance_region_position = appearance_local_position;
    appearance_region_normal = appearance_local_normal;
    appearance_region_uv = UV;
    uvec4 bone_indices = BONE_INDICES;
    vec4 bone_weights = BONE_WEIGHTS;
    appearance_leg_bone = joint_weight_range(bone_indices, bone_weights, 1u, 10u);
    appearance_lower_leg_bone = joint_weight_range(bone_indices, bone_weights, 2u, 5u)
        + joint_weight_range(bone_indices, bone_weights, 7u, 10u);
    if (appearance_species_id == 0) {
        appearance_tail_bone = joint_weight(bone_indices, bone_weights, 33u);
        appearance_arm_bone = joint_weight_range(bone_indices, bone_weights, 14u, 21u)
            + joint_weight_range(bone_indices, bone_weights, 25u, 32u);
        appearance_forearm_bone = joint_weight_range(bone_indices, bone_weights, 16u, 21u)
            + joint_weight_range(bone_indices, bone_weights, 27u, 32u);
        appearance_head_bone = joint_weight(bone_indices, bone_weights, 23u);
        appearance_head_top_bone = joint_weight(bone_indices, bone_weights, 24u);
    } else {
        appearance_tail_bone = joint_weight(bone_indices, bone_weights, 41u);
        appearance_arm_bone = joint_weight_range(bone_indices, bone_weights, 14u, 25u)
            + joint_weight_range(bone_indices, bone_weights, 29u, 40u);
        appearance_forearm_bone = joint_weight_range(bone_indices, bone_weights, 16u, 25u)
            + joint_weight_range(bone_indices, bone_weights, 31u, 40u);
        appearance_head_bone = joint_weight(bone_indices, bone_weights, 27u);
        appearance_head_top_bone = joint_weight(bone_indices, bone_weights, 28u);
    }
}

float soft_band(float value, float lower, float upper, float feather) {
    float rise = smoothstep(lower, lower + feather, value);
    float fall = 1.0 - smoothstep(upper - feather, upper, value);
    return rise * fall;
}

float soft_abs_band(float value, float radius, float feather) {
    return 1.0 - smoothstep(radius, radius + feather, abs(value));
}

float front_surface() {
    return smoothstep(-0.02, 0.22, appearance_region_position.z)
        * smoothstep(-0.02, 0.20, appearance_region_normal.z);
}

float front_face_region(vec3 position) {
    return step(1.18, position.y) * smoothstep(0.14, 0.28, position.z);
}

	float secondary_region(vec3 position) {
		if (appearance_pattern == 1) {
			if (appearance_layout == 1) {
				return 1.0 - step(0.42, position.y);
			}
			if (appearance_layout == 2) {
				return front_face_region(position);
			}
			if (appearance_layout == 3) {
				return step(0.0, position.z) * step(0.42, position.y);
			}
			if (appearance_layout == 4) {
				return step(0.0, position.x);
			}
			return 1.0 - step(0.42, position.y);
		}
		if (appearance_pattern == 2) {
			if (appearance_layout == 5) {
				return 1.0 - step(0.42, position.y);
			}
			if (appearance_layout == 6) {
				return front_face_region(position);
			}
        if (appearance_layout == 7) {
            return step(0.25, position.y);
        }
        return step(0.40, position.y);
		}
		if (appearance_pattern == 3) {
			if (appearance_layout == 10) {
				return front_face_region(position) * step(0.12, abs(position.x));
			}
			if (appearance_layout == 11) {
				return front_face_region(position) * (1.0 - step(0.10, abs(position.x)));
			}
			if (appearance_layout == 12) {
				return front_face_region(position) * step(0.18, abs(position.x)) * step(1.25, position.y);
			}
			return front_face_region(position);
		}
    return 0.0;
}

	float accent_region(vec3 position) {
		if (appearance_pattern != 2) {
			return 0.0;
		}
		if (appearance_layout == 5) {
			return step(0.18, abs(position.x)) * step(0.35, position.y);
		}
		if (appearance_layout == 6) {
			return front_face_region(position) * (1.0 - step(1.18, position.y));
		}
		if (appearance_layout == 7) {
			return 1.0 - step(0.42, position.y);
		}
		if (appearance_layout == 8) {
			return step(0.18, abs(position.x)) * step(0.35, position.y);
		}
	return front_face_region(position) * step(0.05, position.x);
}

float appearance_head_tuft() {
    // Only the small central tuft that protrudes above the crown. The rounded
    // footprint includes the rear half visible in a top view without taking
    // the surrounding crown or forehead with it.
    float crown = appearance_species_id == 1
        ? soft_band(appearance_region_position.y, 1.63, 1.76, 0.018)
        : soft_band(appearance_region_position.y, 1.80, 1.97, 0.020);
    float depth_center = appearance_species_id == 1 ? 0.45 : 0.25;
    float depth_radius = appearance_species_id == 1 ? 0.26 : 0.28;
    float width_radius = appearance_species_id == 1 ? 0.12 : 0.085;
    float ellipse_distance =
        pow(appearance_region_position.x / width_radius, 2.0)
        + pow((appearance_region_position.z - depth_center) / depth_radius, 2.0);
    float center = 1.0 - smoothstep(0.48, 1.0, ellipse_distance);
    float tuft_bone = max(appearance_head_top_bone, appearance_head_bone * 0.65);
    return crown * center * smoothstep(0.05, 0.22, tuft_bone);
}

float appearance_forehead_mark_zone() {
    float forehead = appearance_species_id == 1
        ? soft_band(appearance_region_position.y, 1.52, 1.68, 0.020)
        : soft_band(appearance_region_position.y, 1.62, 1.77, 0.020);
    float center = appearance_species_id == 1
        ? soft_abs_band(appearance_region_position.x, 0.14, 0.018)
        : soft_abs_band(appearance_region_position.x, 0.105, 0.018);
    float front = appearance_species_id == 1
        ? smoothstep(0.18, 0.30, appearance_region_position.z)
            * smoothstep(0.12, 0.24, appearance_region_normal.z)
        : smoothstep(0.22, 0.34, appearance_region_position.z)
            * smoothstep(0.16, 0.27, appearance_region_normal.z);
    float tuft_clear = 1.0 - smoothstep(0.10, 0.34, appearance_head_tuft());
    return forehead * center * front * tuft_clear;
}

float appearance_source_luminance() {
    if (!use_source_fur_texture) return 0.0;
    return dot(texture(source_fur_texture, appearance_region_uv).rgb, vec3(0.299, 0.587, 0.114));
}

float appearance_source_chroma() {
    if (!use_source_fur_texture) return 1.0;
    vec3 source = texture(source_fur_texture, appearance_region_uv).rgb;
    float high = max(max(source.r, source.g), source.b);
    float low = min(min(source.r, source.g), source.b);
    return high - low;
}

float appearance_fox_inner_white_ear() {
    float white = smoothstep(0.62, 0.80, appearance_source_luminance());
    float low_chroma = 1.0 - smoothstep(0.05, 0.16, appearance_source_chroma());
    return white * low_chroma;
}

float appearance_ear_pair() {
    float side = smoothstep(0.255, 0.34, abs(appearance_region_position.x));
    float height = soft_band(appearance_region_position.y, 1.36, 1.82, 0.035);
    float front = smoothstep(0.0, 0.16, appearance_region_position.z)
        * smoothstep(-0.04, 0.12, appearance_region_normal.z);
    float surface = appearance_species_id == 1
        ? (1.0 - appearance_fox_inner_white_ear())
        : front;
    return side * height * surface;
}

float appearance_ear_tip_pair() {
    float radius = abs(appearance_region_position.x);
    float side = appearance_species_id == 0
        ? smoothstep(0.31, 0.40, radius)
            * (1.0 - smoothstep(0.58, 0.64, radius))
        : smoothstep(0.27, 0.33, radius)
            * (1.0 - smoothstep(0.45, 0.51, radius));
    float height = appearance_species_id == 0
        ? soft_band(appearance_region_position.y, 1.10, 1.38, 0.030)
        : soft_band(appearance_region_position.y, 1.76, 2.00, 0.030);
    float surface = smoothstep(-0.04, 0.16, appearance_region_position.z);
    return side * height * surface;
}

float appearance_cheek_fluff() {
    float face = appearance_species_id == 0
        ? soft_band(appearance_region_position.y, 1.23, 1.44, 0.025)
        : soft_band(appearance_region_position.y, 1.18, 1.43, 0.025);
    float inner_radius = appearance_species_id == 1 ? 0.16 : 0.13;
    float outer_radius = appearance_species_id == 1 ? 0.36 : 0.30;
    float sides = smoothstep(inner_radius, inner_radius + 0.035, abs(appearance_region_position.x))
        * (1.0 - smoothstep(outer_radius - 0.035, outer_radius, abs(appearance_region_position.x)));
    float front = appearance_species_id == 0
        ? smoothstep(0.20, 0.38, appearance_region_position.z)
            * smoothstep(0.22, 0.42, appearance_region_normal.z)
        : smoothstep(0.12, 0.24, appearance_region_position.z)
            * smoothstep(0.10, 0.22, appearance_region_normal.z);
    return face * sides * front * smoothstep(0.05, 0.28, appearance_head_bone);
}

float appearance_chest_tuft() {
    float chest_y = appearance_region_position.y + (appearance_species_id == 1 ? 0.0 : -0.04);
    vec2 point = vec2(appearance_region_position.x, chest_y);
    float left_lobe = 1.0 - smoothstep(
        1.0, 1.06, length((point - vec2(-0.065, 0.98)) / vec2(0.085, 0.065))
    );
    float right_lobe = 1.0 - smoothstep(
        1.0, 1.06, length((point - vec2(0.065, 0.98)) / vec2(0.085, 0.065))
    );
    float point_progress = smoothstep(0.78, 0.91, chest_y);
    float point_width = mix(0.0, 0.065, point_progress);
    float point_tip = soft_band(chest_y, 0.76, 0.99, 0.020)
        * soft_abs_band(appearance_region_position.x, point_width, 0.016);
    float heart = max(max(left_lobe, right_lobe), point_tip);
    return heart * smoothstep(0.06, 0.20, appearance_region_position.z)
        * smoothstep(0.14, 0.28, appearance_region_normal.z);
}

float appearance_belly_center() {
    float center_y = appearance_species_id == 1 ? 0.70 : 0.69;
    float half_height = appearance_species_id == 1 ? 0.28 : 0.27;
    float vertical = abs((appearance_region_position.y - center_y) / half_height);
    float inside = 1.0 - smoothstep(0.78, 1.0, vertical);
    float bulge = sqrt(max(0.0, 1.0 - min(vertical * vertical, 1.0)));
    float max_width = appearance_species_id == 1 ? 0.17 : 0.16;
    float width = mix(0.045, max_width, bulge);
    float center = 1.0 - smoothstep(width, width + 0.025, abs(appearance_region_position.x));
    return inside * center
        * smoothstep(0.12, 0.28, appearance_region_position.z)
        * smoothstep(0.42, 0.56, appearance_region_normal.z)
        * (1.0 - smoothstep(0.14, 0.20, abs(appearance_region_position.x)));
}

float appearance_forearm_paw_pair() {
    return smoothstep(0.18, 0.52, appearance_forearm_bone);
}

float appearance_elbow_cuff_pair() {
    float elbow = soft_band(appearance_region_position.y, 0.66, 0.84, 0.035);
    return elbow * smoothstep(0.18, 0.52, appearance_arm_bone);
}

float appearance_lower_leg_foot_pair() {
    float leg = soft_band(appearance_region_position.y, -0.04, 0.38, 0.035);
    return leg * smoothstep(0.22, 0.58, appearance_lower_leg_bone);
}

float appearance_knee_cuff_pair() {
    float center_x = appearance_species_id == 1 ? 0.17 : 0.18;
    float dx = abs(abs(appearance_region_position.x) - center_x) / 0.12;
    float dy = abs(appearance_region_position.y - 0.36) / 0.085;
    float cap = 1.0 - smoothstep(0.72, 1.0, dx * dx + dy * dy);
    return cap * smoothstep(0.18, 0.52, appearance_leg_bone);
}

float appearance_tail_tip() {
    float tail_progress = length(vec2(appearance_region_position.x, appearance_region_position.z));
    float endpoint = appearance_species_id == 0
        ? smoothstep(0.56, 0.80, tail_progress)
        : smoothstep(0.64, 0.90, tail_progress);
    return endpoint * smoothstep(0.24, 0.66, appearance_tail_bone);
}

float appearance_tail_underside() {
    float tail_progress = length(vec2(appearance_region_position.x, appearance_region_position.z));
    float not_tip = 1.0 - smoothstep(0.74, 0.92, tail_progress);
    float underside = smoothstep(0.08, 0.32, -appearance_region_normal.y);
    return not_tip * underside * smoothstep(0.24, 0.66, appearance_tail_bone);
}

float appearance_region_alpha(int region_id) {
    if (region_id == 0) return appearance_head_tuft();
    if (region_id == 1) return appearance_forehead_mark_zone();
    if (region_id == 2) return appearance_ear_pair();
    if (region_id == 3) return appearance_ear_tip_pair();
    if (region_id == 4) return appearance_cheek_fluff();
    if (region_id == 5) return appearance_chest_tuft();
    if (region_id == 6) return appearance_belly_center();
    if (region_id == 7) return appearance_forearm_paw_pair();
    if (region_id == 8) return appearance_elbow_cuff_pair();
    if (region_id == 9) return appearance_lower_leg_foot_pair();
    if (region_id == 10) return appearance_knee_cuff_pair();
    if (region_id == 11) return appearance_tail_tip();
    if (region_id == 12) return appearance_tail_underside();
    return 0.0;
}

float stroke(vec2 point, vec2 start, vec2 finish, float width) {
    vec2 along = finish - start;
    float projection = clamp(dot(point - start, along) / max(dot(along, along), 0.0001), 0.0, 1.0);
    return 1.0 - smoothstep(width, width + 0.035, length(point - mix(start, finish, projection)));
}

float dot_mark(vec2 point, vec2 center, float radius) {
    return 1.0 - smoothstep(radius, radius + 0.035, length(point - center));
}

float marking_shape(vec2 point, int marking) {
    if (marking == 1) {
        float outer = 1.0 - smoothstep(0.48, 0.58, length(point));
        float cutout = 1.0 - smoothstep(0.43, 0.53, length(point - vec2(0.20, 0.03)));
        return outer * (1.0 - cutout);
    }
    if (marking == 2) {
        float upper = stroke(point, vec2(-0.35, 0.28), vec2(0.30, 0.28), 0.07);
        float middle = stroke(point, vec2(0.30, 0.28), vec2(-0.30, -0.04), 0.07);
        float lower = stroke(point, vec2(-0.30, -0.04), vec2(0.35, -0.28), 0.07);
        return max(max(upper, middle), lower);
    }
    if (marking == 3) {
        float first = abs(length(point) - 0.28);
        float second = abs(length(point - vec2(0.12, 0.0)) - 0.18);
        return max(1.0 - smoothstep(0.035, 0.075, first), 1.0 - smoothstep(0.035, 0.075, second));
    }
    if (marking == 4) {
        return max(max(dot_mark(point, vec2(-0.28, 0.20), 0.08), dot_mark(point, vec2(0.02, 0.32), 0.06)), max(dot_mark(point, vec2(0.25, 0.10), 0.075), dot_mark(point, vec2(-0.05, -0.20), 0.055)));
    }
    if (marking == 5) {
        return max(dot_mark(point, vec2(-0.25, 0.08), 0.12), stroke(point, vec2(-0.12, 0.02), vec2(0.40, -0.22), 0.06));
    }
    if (marking == 6) {
        return max(max(stroke(point, vec2(0.0, -0.38), vec2(0.0, 0.38), 0.06), stroke(point, vec2(-0.25, 0.24), vec2(0.25, 0.24), 0.05)), stroke(point, vec2(-0.20, -0.20), vec2(0.22, -0.20), 0.05));
    }
    if (marking == 7) {
        return 1.0 - smoothstep(0.55, 0.65, abs(point.x) + abs(point.y));
    }
    if (marking == 8) {
        return max(dot_mark(point, vec2(0.0), 0.16), max(stroke(point, vec2(-0.42, 0.0), vec2(0.42, 0.0), 0.045), stroke(point, vec2(0.0, -0.42), vec2(0.0, 0.42), 0.045)));
    }
    if (marking == 9) {
        return max(max(stroke(point, vec2(-0.28, 0.35), vec2(0.05, 0.05), 0.06), stroke(point, vec2(0.05, 0.05), vec2(-0.12, 0.05), 0.06)), stroke(point, vec2(-0.12, 0.05), vec2(0.25, -0.35), 0.06));
    }
    if (marking == 10) {
        return 1.0 - smoothstep(0.055, 0.10, abs(point.y - 0.20 * sin(point.x * 5.0)));
    }
    if (marking == 11) {
        return max(0.0, 1.0 - smoothstep(0.035, 0.075, abs(length(point) - 0.34)));
    }
    if (marking == 12) {
        return 1.0 - smoothstep(0.55, 0.65, length(point));
    }
    if (marking == 13) {
        return max(max(dot_mark(point, vec2(-0.24, 0.18), 0.06), dot_mark(point, vec2(0.0, 0.24), 0.05)), max(dot_mark(point, vec2(0.22, 0.13), 0.055), dot_mark(point, vec2(-0.05, -0.18), 0.045)));
    }
    if (marking == 14) {
        return max(dot_mark(point, vec2(-0.14, 0.16), 0.20), dot_mark(point, vec2(0.14, 0.16), 0.20)) * step(point.y, 0.22);
    }
    if (marking == 15) {
        return dot_mark(point, vec2(0.0, 0.0), 0.11);
    }
    return 0.0;
}

float marking_placement_region() {
    if (appearance_marking_placement == 1 || appearance_marking_placement == 2 || appearance_marking_placement == 3) {
        return appearance_region_alpha(1);
    }
    if (appearance_marking_placement == 4) {
        return appearance_region_alpha(4);
    }
    if (appearance_marking_placement == 5) {
        return appearance_region_alpha(5);
    }
    if (appearance_marking_placement == 6) {
        return appearance_region_alpha(6);
    }
    return 0.0;
}

float marking_region() {
    if (appearance_marking == 0 || appearance_marking_placement == 0) {
        return 0.0;
    }
    float allowed = marking_placement_region();
    if (allowed < 0.01 || appearance_local_position.z < appearance_marking_zone.z || appearance_local_normal.z < 0.08) {
        return 0.0;
    }
    vec2 point = (appearance_local_position.xy - appearance_marking_zone.xy) / max(appearance_marking_zone.w * appearance_marking_scale, 0.01);
    return marking_shape(point, appearance_marking) * allowed * appearance_marking_intensity;
}

float luminance(vec3 color) {
    return dot(color, vec3(0.299, 0.587, 0.114));
}

vec3 relative_tone_transfer_with_mid(vec3 source, vec3 target, float mid_luma) {
    float source_luma = max(luminance(source), 0.001);
    float target_luma = max(luminance(target), 0.001);
    float exponent = mix(1.0, 0.78, clamp(source_detail_strength, 0.0, 1.0));
    float relative_luma = pow(source_luma / max(mid_luma, 0.001), exponent);
    float target_luma_at_pixel = clamp(target_luma * relative_luma, 0.015, 0.985);
    vec3 target_chroma = target / target_luma;
    return clamp(target_chroma * target_luma_at_pixel, vec3(0.0), vec3(1.0));
}

vec3 relative_tone_transfer(vec3 source, vec3 target) {
    return relative_tone_transfer_with_mid(source, target, source_mid_luma);
}

float grade_scale(int grade) {
    if (grade == 1) return 1.08;
    if (grade == 2) return 0.92;
    if (grade == 3) return 0.82;
    return 1.0;
}

vec3 region_tone_transfer(vec3 source, vec3 target, float mid_luma, int grade) {
    return relative_tone_transfer_with_mid(
        source,
        clamp(target * grade_scale(grade), vec3(0.0), vec3(1.0)),
        mid_luma
    );
}

vec3 apply_region_slot(vec3 color, vec3 source, int region_id, vec3 target, float mid_luma, float intensity, int grade) {
    if (region_id < 0 || intensity <= 0.001 || !use_source_fur_texture) {
        return color;
    }
    float alpha = clamp(appearance_region_alpha(region_id), 0.0, 1.0);
    if (alpha <= 0.001) {
        return color;
    }
    vec3 recolored = region_tone_transfer(source, target, mid_luma, grade);
    float source_luma = luminance(source);
    float dark_feature = 1.0 - smoothstep(0.03, 0.20, source_luma);
    recolored = mix(recolored, source, dark_feature * 0.92);
    return mix(color, recolored, alpha * clamp(intensity, 0.0, 1.0));
}

void fragment() {
    vec4 base = base_color;
    if (use_base_texture) {
        base *= texture(base_texture, UV);
    }
    vec3 source_detail = vec3(1.0);
    float source_luma = 1.0;
    float dark_feature = 0.0;
    vec4 uv_mask = vec4(0.0);
    if (use_source_fur_texture) {
        source_detail = texture(source_fur_texture, UV).rgb;
        source_luma = luminance(source_detail);
        dark_feature = 1.0 - smoothstep(0.03, 0.20, source_luma);
    }
    if (use_appearance_uv_mask) {
        uv_mask = texture(appearance_uv_mask, UV);
    }
    vec3 target_color = appearance_tint.rgb;
    vec3 color = base.rgb * target_color;
    if (use_color_slots) {
        float secondary = secondary_region(appearance_local_position);
        float accent = accent_region(appearance_local_position);
        target_color = mix(primary_color.rgb, secondary_color.rgb, secondary);
        target_color = target_color * mix(vec3(1.0), accent_color.rgb, accent);
        if (appearance_pattern == 3) {
            target_color = mix(primary_color.rgb, face_mask_color.rgb, secondary);
        }
        color = base.rgb * target_color;
    } else {
        float accent = 0.0;
        if (appearance_pattern == 1) {
            accent = step(0.5, fract(UV.x * 7.0));
        } else if (appearance_pattern == 2) {
            accent = step(0.5, fract(UV.x * 4.0) + fract(UV.y * 4.0));
        } else if (appearance_pattern == 3) {
            accent = step(0.55, abs(fract(UV.x * 3.0) - 0.5));
        }
        color = mix(color, color * vec3(0.48, 0.64, 0.82), accent * 0.42);
    }
    if (use_source_fur_texture) {
        color = relative_tone_transfer(source_detail, target_color);
    }
    // Preserve source texture semantics instead of painting a translucent layer
    // over the GLB. Dark features protect eyes/nose/mouth; low-chroma highlights
    // protect the fox's white cheek/chest/ear fur and the dog's light fur.
    if (use_source_fur_texture) {
        float source_high = max(max(source_detail.r, source_detail.g), source_detail.b);
        float source_low = min(min(source_detail.r, source_detail.g), source_detail.b);
        float source_chroma = source_high - source_low;
        float light_region = smoothstep(0.50, 0.78, source_luma)
            * (1.0 - smoothstep(0.05, 0.16, source_chroma));
        if (use_appearance_uv_mask) {
            color = mix(color, source_detail, clamp(max(uv_mask.r, uv_mask.g), 0.0, 1.0));
        }
        color = mix(color, source_detail, max(dark_feature * 0.92, light_region * 0.94));
        color = apply_region_slot(
            color, source_detail, region_0_id, region_0_color.rgb,
            region_0_source_mid_luma, region_0_intensity, region_0_grade
        );
        color = apply_region_slot(
            color, source_detail, region_1_id, region_1_color.rgb,
            region_1_source_mid_luma, region_1_intensity, region_1_grade
        );
        color = apply_region_slot(
            color, source_detail, region_2_id, region_2_color.rgb,
            region_2_source_mid_luma, region_2_intensity, region_2_grade
        );
    }
    float marking = marking_region();
    if (use_source_fur_texture && marking > 0.001) {
        vec3 marking_tone = relative_tone_transfer(source_detail, marking_color.rgb);
        marking_tone = mix(marking_tone, source_detail, dark_feature * 0.92);
        color = mix(color, marking_tone, marking);
    } else {
        color = mix(color, marking_color.rgb, marking);
    }
    ALBEDO = color;
    // The source asset's baked highlights are already carried by the relative
    // tone transfer. Keep an opt-in emission channel for future materials,
    // but do not add a second highlight layer by default.
    if (use_source_fur_texture) {
        EMISSION = color * source_luma * source_emission_strength;
    }
    ALPHA = base.a;
}
"""


static func apply(
	visual_root: Node3D,
	collision_shape: CollisionShape3D,
	appearance: Dictionary,
	species_id: String = "",
) -> void:
	var height_scale := _appearance_scale(
		appearance.get("height_scale", appearance.get("height", "standard")),
		{"short": 0.92, "standard": 1.0, "tall": 1.08},
	)
	var build_scale := _appearance_scale(
		appearance.get("build_scale", appearance.get("build", "standard")),
		{"slim": 0.92, "standard": 1.0, "plump": 1.08},
	)
	height_scale = clampf(height_scale, 0.85, 1.15)
	build_scale = clampf(build_scale, 0.85, 1.15)
	visual_root.scale = Vector3(build_scale, height_scale, build_scale)

	var capsule := collision_shape.shape.duplicate() as CapsuleShape3D
	capsule.radius = BASE_COLLISION_RADIUS * build_scale
	capsule.height = maxf(
		BASE_COLLISION_HEIGHT * height_scale,
		capsule.radius * 2.0,
	)
	collision_shape.shape = capsule
	collision_shape.position.y = capsule.height * 0.5
	var bindings: Dictionary = SPECIES_CATALOG.appearance_bindings(species_id)
	_apply_bone_scales(
		visual_root,
		appearance.get("bone_scales", {}),
		bindings.get("bone_scales", {}),
	)
	_apply_blend_shapes(
		visual_root,
		appearance.get("blend_shapes", {}),
		bindings.get("blend_shapes", {}),
	)
	_apply_material_parameters(
		visual_root,
		appearance.get("material_parameters", {}),
		bindings,
		species_id,
	)


static func visual_bounds(visual_root: Node3D) -> AABB:
	var bounds := AABB()
	var has_bounds := false
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		for bone_index in range(skeleton.get_bone_count()):
			var point := skeleton.to_global(
				skeleton.get_bone_global_pose(bone_index).origin
			)
			if has_bounds:
				bounds = bounds.expand(point)
			else:
				bounds = AABB(point, Vector3.ZERO)
				has_bounds = true
	if has_bounds:
		return bounds.grow(0.14)
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var mesh_bounds := mesh_instance.global_transform * mesh_instance.get_aabb()
		if has_bounds:
			bounds = bounds.merge(mesh_bounds)
		else:
			bounds = mesh_bounds
			has_bounds = true
	if has_bounds:
		return bounds.grow(0.14)
	return bounds


static func preview_focus_point(visual_root: Node3D, target: String) -> Vector3:
	var bounds := visual_bounds(visual_root)
	if bounds.size.is_zero_approx():
		return visual_root.global_position + Vector3(0.0, 0.9, 0.0)
	if target == "head":
		return Vector3(
			bounds.get_center().x,
			bounds.end.y - bounds.size.y * 0.12,
			bounds.get_center().z,
		)
	return bounds.get_center()


static func _apply_bone_scales(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	for node in visual_root.find_children("*", "Skeleton3D", true, false):
		var skeleton := node as Skeleton3D
		if skeleton == null:
			continue
		for control_name: String in bindings:
			if control_name == "HeadScale" or control_name == "NeckLength":
				continue
			if not (raw_values as Dictionary).has(control_name):
				continue
			var control: Variant = bindings[control_name]
			if not control is Dictionary:
				continue
			var factor := clampf(
				float((raw_values as Dictionary).get(control_name, 1.0)),
				0.5,
				1.5,
			)
			var pose_scale := (
				Vector3.ONE * factor
				if String((control as Dictionary).get("mode", "")) == "uniform"
				else Vector3(1.0, factor, 1.0)
			)
			for bone_name: String in _string_array((control as Dictionary).get("bones", [])):
				var bone_index := skeleton.find_bone(bone_name)
				if bone_index >= 0:
					skeleton.set_bone_pose_scale(bone_index, pose_scale)
		_apply_neck_and_head_scales(skeleton, raw_values as Dictionary, bindings)


static func _apply_neck_and_head_scales(
	skeleton: Skeleton3D,
	raw_values: Dictionary,
	bindings: Dictionary,
) -> void:
	if not raw_values.has("NeckLength") and not raw_values.has("HeadScale"):
		return
	var neck_factor := clampf(float(raw_values.get("NeckLength", 1.0)), 0.5, 1.5)
	var head_factor := clampf(float(raw_values.get("HeadScale", 1.0)), 0.5, 1.5)
	var neck_control: Variant = bindings.get("NeckLength", {})
	if neck_control is Dictionary and raw_values.has("NeckLength"):
		for bone_name: String in _string_array((neck_control as Dictionary).get("bones", [])):
			var neck_index := skeleton.find_bone(bone_name)
			if neck_index >= 0:
				skeleton.set_bone_pose_scale(neck_index, Vector3(1.0, neck_factor, 1.0))
	var head_control: Variant = bindings.get("HeadScale", {})
	if head_control is Dictionary and raw_values.has("HeadScale"):
		for bone_name: String in _string_array((head_control as Dictionary).get("bones", [])):
			var head_index := skeleton.find_bone(bone_name)
			if head_index >= 0:
				# Neck scale is inherited by Head; cancel it on the local length axis.
				skeleton.set_bone_pose_scale(
					head_index,
					Vector3(head_factor, head_factor / neck_factor, head_factor),
				)


static func _apply_blend_shapes(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var bindings := raw_bindings as Dictionary
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for semantic_name: Variant in (raw_values as Dictionary):
			var binding: Variant = bindings.get(String(semantic_name), {})
			var shape_names := [String(semantic_name)]
			if binding is Dictionary:
				var configured_names := _string_array((binding as Dictionary).get("shapes", []))
				if not configured_names.is_empty():
					shape_names = configured_names
			for shape_name: String in shape_names:
				if mesh_instance.find_blend_shape_by_name(StringName(shape_name)) < 0:
					continue
				mesh_instance.set(
					"blend_shapes/%s" % shape_name,
					clampf(float((raw_values as Dictionary)[semantic_name]), 0.0, 1.0),
				)


static func _apply_material_parameters(
	visual_root: Node3D,
	raw_values: Variant,
	raw_bindings: Variant,
	species_id: String,
) -> void:
	if not raw_values is Dictionary or not raw_bindings is Dictionary:
		return
	var appearance_bindings := raw_bindings as Dictionary
	var bindings: Variant = appearance_bindings.get("material_parameters", {})
	if not bindings is Dictionary:
		return
	bindings = bindings as Dictionary
	var tint := Color.WHITE
	var pattern_id := 0
	var pattern_layout := 0
	var marking_id := 0
	var marking_placement := 0
	var primary := Color.WHITE
	var secondary := Color.WHITE
	var accent := Color.WHITE
	var face_mask := Color.WHITE
	var marking := Color.WHITE
	var use_color_slots := false
	var has_material_binding := false
	var palette_values: Dictionary = {}
	var region_ids := [-1, -1, -1]
	var region_colors := [Color.WHITE, Color.WHITE, Color.WHITE]
	var region_mid_lumas := [0.5, 0.5, 0.5]
	var region_intensities := [0.0, 0.0, 0.0]
	var region_grades := [0, 0, 0]
	var palette_binding: Variant = bindings.get("palette_id", {})
	if palette_binding is Dictionary:
		var raw_palette_values: Variant = (palette_binding as Dictionary).get("values", {})
		if raw_palette_values is Dictionary:
			palette_values = raw_palette_values as Dictionary
	for semantic_name: String in bindings:
		var binding: Variant = bindings[semantic_name]
		if not binding is Dictionary:
			continue
		var value: Variant = (raw_values as Dictionary).get(semantic_name)
		var values: Variant = (binding as Dictionary).get("values", {})
		if not values is Dictionary:
			continue
		var mapped: Variant = (values as Dictionary).get(str(value))
		if mapped == null:
			continue
		var mode: String = String((binding as Dictionary).get("mode", ""))
		if mode == "albedo_tint":
			var color: Variant = _color_value(mapped)
			if color != null:
				tint = _multiply_color(tint, color)
				has_material_binding = true
		elif mode == "pattern_id" and (mapped is int or mapped is float):
			pattern_id = int(mapped)
			has_material_binding = true
		elif mode == "pattern_layout_id" and (mapped is int or mapped is float):
			pattern_layout = int(mapped)
			has_material_binding = true
		elif mode == "marking_id" and (mapped is int or mapped is float):
			marking_id = int(mapped)
			has_material_binding = true
		elif mode == "marking_placement" and (mapped is int or mapped is float):
			marking_placement = int(mapped)
			has_material_binding = true
		elif mode == "region_id" and (mapped is int or mapped is float):
			var region_slot := int((binding as Dictionary).get("slot", -1))
			if region_slot >= 0 and region_slot < 3:
				region_ids[region_slot] = int(mapped)
				region_mid_lumas[region_slot] = float(
					(raw_values as Dictionary).get("region_%d_source_mid_luma" % region_slot, 0.5)
				)
				region_intensities[region_slot] = clampf(float(
					(raw_values as Dictionary).get("region_%d_intensity" % region_slot, 0.0)
				), 0.0, 1.0)
				region_grades[region_slot] = _grade_value(
					String((raw_values as Dictionary).get("region_%d_grade_id" % region_slot, "L1"))
				)
				has_material_binding = true
	var slot_names := [
		{"name": "primary_color_id", "target": "primary"},
		{"name": "secondary_color_id", "target": "secondary"},
		{"name": "accent_color_id", "target": "accent"},
		{"name": "face_mask_color_id", "target": "face_mask"},
		{"name": "marking_color_id", "target": "marking"},
	]
	for slot: Dictionary in slot_names:
		var color_id := String((raw_values as Dictionary).get(slot["name"], ""))
		var mapped_color: Variant = palette_values.get(color_id)
		var slot_color: Variant = _color_value(mapped_color)
		if slot_color == null:
			continue
		use_color_slots = true
		has_material_binding = true
		match String(slot["target"]):
			"primary":
				primary = slot_color
			"secondary":
				secondary = slot_color
			"accent":
				accent = slot_color
			"face_mask":
				face_mask = slot_color
			"marking":
				marking = slot_color
	for region_slot in range(3):
		var region_color_id := String(
			(raw_values as Dictionary).get("region_%d_color_id" % region_slot, "")
		)
		var region_color_value: Variant = _color_value(palette_values.get(region_color_id))
		if region_color_value != null:
			region_colors[region_slot] = region_color_value
			use_color_slots = true
			has_material_binding = true
	var marking_zones: Variant = appearance_bindings.get("marking_zones", {})
	var zone_value: Variant = null
	if marking_zones is Dictionary:
		zone_value = (marking_zones as Dictionary).get(
			String((raw_values as Dictionary).get("marking_placement", "none")),
			[0.0, 0.0, 0.0, 0.0],
		)
	var marking_zone := _vector4_value(zone_value)
	var marking_scale := clampf(float((raw_values as Dictionary).get("marking_scale", 0.9)), 0.5, 1.25)
	var marking_intensity := clampf(float((raw_values as Dictionary).get("marking_intensity", 0.9)), 0.0, 1.0)
	if not has_material_binding:
		return
	var shader := Shader.new()
	shader.code = APPEARANCE_SHADER_CODE
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var source_material: Material = mesh_instance.get_active_material(surface_index)
			var material: ShaderMaterial = ShaderMaterial.new()
			material.shader = shader
			material.set_shader_parameter("appearance_tint", tint)
			material.set_shader_parameter("appearance_species_id", 0 if species_id == "dog" else 1)
			material.set_shader_parameter("use_color_slots", use_color_slots)
			material.set_shader_parameter("primary_color", primary)
			material.set_shader_parameter("secondary_color", secondary)
			material.set_shader_parameter("accent_color", accent)
			material.set_shader_parameter("face_mask_color", face_mask)
			material.set_shader_parameter("marking_color", marking)
			material.set_shader_parameter("appearance_pattern", pattern_id)
			material.set_shader_parameter("appearance_layout", pattern_layout)
			material.set_shader_parameter("appearance_marking", marking_id)
			material.set_shader_parameter("appearance_marking_placement", marking_placement)
			material.set_shader_parameter("appearance_marking_zone", marking_zone)
			material.set_shader_parameter("appearance_marking_scale", marking_scale)
			material.set_shader_parameter("appearance_marking_intensity", marking_intensity)
			for region_slot in range(3):
				material.set_shader_parameter("region_%d_id" % region_slot, region_ids[region_slot])
				material.set_shader_parameter("region_%d_color" % region_slot, region_colors[region_slot])
				material.set_shader_parameter(
					"region_%d_source_mid_luma" % region_slot,
					region_mid_lumas[region_slot],
				)
				material.set_shader_parameter(
					"region_%d_intensity" % region_slot,
					region_intensities[region_slot],
				)
				material.set_shader_parameter(
					"region_%d_grade" % region_slot,
					region_grades[region_slot],
				)
			if source_material is BaseMaterial3D:
				var source_fur_texture: Texture2D = null
				if source_material.emission_texture != null:
					source_fur_texture = source_material.emission_texture
				elif source_material.albedo_texture != null:
					source_fur_texture = source_material.albedo_texture
				if source_fur_texture != null:
					material.set_shader_parameter("source_fur_texture", source_fur_texture)
					material.set_shader_parameter("use_source_fur_texture", true)
					material.set_shader_parameter(
						"source_mid_luma",
						float(SOURCE_MID_LUMA.get(species_id, 0.37)),
					)
				# Imported GLB materials can carry a dark baked albedo.  Once the
				# appearance protocol supplies explicit color slots, that texture is
				# a mask for the old look rather than a useful base; multiplying by it
				# made every generated candidate appear nearly black.  Keep the source
				# material intact for legacy tint-only payloads, but let the explicit
				# palette drive the visible base for slot-based coats.
				material.set_shader_parameter(
					"base_color",
					Color.WHITE if use_color_slots else source_material.albedo_color,
				)
				if source_material.albedo_texture != null and not use_color_slots:
					material.set_shader_parameter("base_texture", source_material.albedo_texture)
					material.set_shader_parameter("use_base_texture", true)
			mesh_instance.set_surface_override_material(surface_index, material)


static func _color_value(value: Variant) -> Variant:
	if value is Array and (value as Array).size() >= 3:
		var values := value as Array
		return Color(
			float(values[0]),
			float(values[1]),
			float(values[2]),
			float(values[3]) if values.size() > 3 else 1.0,
		)
	return null


static func _vector4_value(value: Variant) -> Vector4:
	if value is Array and (value as Array).size() == 4:
		var values := value as Array
		return Vector4(
			float(values[0]),
			float(values[1]),
			float(values[2]),
			float(values[3]),
		)
	return Vector4.ZERO


static func _multiply_color(left: Color, right: Color) -> Color:
	return Color(left.r * right.r, left.g * right.g, left.b * right.b, left.a * right.a)


static func _grade_value(value: String) -> int:
	match value:
		"L2":
			return 1
		"D1":
			return 2
		"D2":
			return 3
		_:
			return 0


static func _string_array(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if not value is Array:
		return result
	for item: Variant in value as Array:
		if item is String:
			result.append(item as String)
	return result


static func _appearance_scale(value: Variant, named_values: Dictionary) -> float:
	if value is float or value is int:
		return float(value)
	return float(named_values.get(String(value), 1.0))
