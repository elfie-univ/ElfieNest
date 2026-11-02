shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_lambert;
uniform vec4 source_albedo : source_color = vec4(0.2,0.65,0.8,1.0);
uniform vec3 light_tint : source_color = vec3(0.25,0.8,1.0);
uniform float light_level = 0.0;
uniform float seconds = 0.0;
uniform float turn_seconds = 2.4;
uniform float sequence_amount = 0.0;
uniform float spin_angle=0.0;
uniform float converge=0.0;
uniform bool guide_enabled=false;
uniform float guide_progress=0.0;
uniform vec3 guide_axis=vec3(0.0,0.0,1.0);
uniform vec3 guide_origin=vec3(0.0);
uniform float guide_min=0.0;
uniform float guide_span=1.0;
uniform bool platform_ring=false;
uniform float platform_top=10.25;
uniform bool chases = false;
uniform float root_height = 10.0;
uniform bool petal = false;
uniform float petal_bottom = 10.0;
uniform float petal_height = 2.0;
uniform bool use_source_texture = false;
uniform bool use_emission_texture = false;
uniform sampler2D source_texture : source_color, filter_linear_mipmap;
uniform sampler2D emission_texture : source_color, filter_linear_mipmap;
varying vec3 world_position;
void vertex(){world_position=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;}
void fragment(){
	// Looking down +Y, increasing XZ angle is clockwise.
	float angle=atan(world_position.z,world_position.x);
	float behind=fract((spin_angle-angle)/6.2831853);
	float head=1.0-smoothstep(0.025,0.09,behind);
	float tail=pow(1.0-clamp(behind/0.45,0.0,1.0),2.0);
	float spin_mask=platform_ring ? smoothstep(platform_top-0.1,platform_top-0.02,world_position.y) : 1.0;
	float pattern=chases ? mix(1.0,0.08+head+tail*0.55,sequence_amount*spin_mask) : 1.0;
	if(petal){
		float height=(world_position.y-petal_bottom)/petal_height;
		float flow=pow(0.5+0.5*cos(6.2831853*(height+seconds*0.85)),4.0);
		pattern=mix(1.0,0.55+flow*1.25,sequence_amount);
	}
	if(converge>0.0){
		float r=length(world_position.xz-guide_origin.xz);
		pattern*=mix(1.0,0.35+0.65*pow(0.5+0.5*cos(r*14.0+seconds*9.0),4.0),converge);
	}
	if(guide_enabled){
		float along=(dot(world_position-guide_origin,guide_axis)-guide_min)/guide_span;
		pattern*=0.1+0.9*(1.0-smoothstep(guide_progress-0.08,guide_progress+0.08,along));
	}
	vec4 original=source_albedo;
	if(use_source_texture){original*=texture(source_texture,UV);}
	ALBEDO=original.rgb;
	ALPHA=original.a;
	ROUGHNESS=0.22;
	EMISSION=light_tint*light_level*pattern;
	if(use_emission_texture){EMISSION*=texture(emission_texture,UV).rgb;}
}
