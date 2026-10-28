shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;
uniform float bottom=10.0;
uniform float height=2.0;
uniform float fill=0.0;
uniform float level=0.0;
uniform bool rear_line=false;
varying vec3 world_position;
varying vec3 world_normal;
void vertex(){
	VERTEX+=NORMAL*0.002;
	world_position=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
	world_normal=normalize(MODEL_NORMAL_MATRIX*NORMAL);
}
void fragment(){
	float from_base=clamp((world_position.y-bottom)/height,0.0,1.0);
	float side_fill=rear_line?fill:clamp((fill-0.2)/0.8,0.0,1.0);
	float charged=(1.0-smoothstep(side_fill-0.035,side_fill+0.035,from_base))*smoothstep(0.0,0.12,side_fill);
	vec3 radial=normalize(vec3(world_position.x,0.0,world_position.z));
	float side_face=smoothstep(0.6,0.86,1.0-abs(dot(normalize(world_normal),radial)));
	float rear_mask=1.0-smoothstep(0.055,0.09,abs(UV2.x));
	ALBEDO=rear_line?vec3(0.06,0.8,1.0):vec3(0.035,0.28,0.8);
	EMISSION=ALBEDO*0.65;
	ALPHA=level*charged*(rear_line?rear_mask*0.55:side_face*0.5);
}
