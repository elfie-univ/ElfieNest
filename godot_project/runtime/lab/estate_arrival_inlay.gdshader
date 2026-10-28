shader_type spatial;
render_mode diffuse_lambert, cull_disabled;
uniform vec4 ceramic: source_color=vec4(0.9,0.86,0.79,1.0);
uniform float level=0.1;
uniform float fill=0.0;
varying vec3 world_position;
varying vec3 world_normal;
void vertex(){
	world_position=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
	world_normal=normalize(MODEL_NORMAL_MATRIX*NORMAL);
}
void fragment(){
	vec3 radial=normalize(vec3(world_position.x,0.0,world_position.z));
	float facing=-dot(normalize(world_normal),radial);
	float front=smoothstep(0.08,0.45,facing);
	float panel=(1.0-smoothstep(0.92,0.99,abs(UV2.x)))*smoothstep(0.0,0.025,UV2.y)*(1.0-smoothstep(0.975,1.0,UV2.y))*front;
	float center=1.0-smoothstep(0.38,0.46,abs(UV2.x));
	float side_fill=clamp((fill-0.2)/0.8,0.0,1.0);
	float charged=1.0-smoothstep(mix(side_fill,fill,center)-0.035,mix(side_fill,fill,center)+0.035,UV2.y);
	vec3 color=mix(vec3(0.035,0.28,0.8),vec3(0.06,0.8,1.0),center);
	float active=panel*charged*smoothstep(0.0,0.12,fill);
	ALBEDO=mix(ceramic.rgb,color*0.38,active);
	METALLIC=0.06;
	ROUGHNESS=0.28;
	EMISSION=color*active*level*mix(0.5,0.8,center);
}
