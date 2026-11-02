shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;
uniform float level=0.0;
uniform float fill=0.0;
uniform float radius=3.5;
uniform vec3 center=vec3(0.0);
uniform float seconds=0.0;
uniform bool roof_only=false;
varying vec3 world_position;
varying vec3 world_normal;
void vertex(){
	if(roof_only){VERTEX.y-=0.008;}else{VERTEX-=NORMAL*0.004;}
	world_position=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
	world_normal=normalize(MODEL_NORMAL_MATRIX*NORMAL);
}
void fragment(){
	float r=length(world_position.xz-center.xz)/radius;
	float coverage=1.0-smoothstep(fill-0.08,fill+0.08,r);
	if(roof_only){coverage*=smoothstep(11.6,12.0,world_position.y)*smoothstep(0.15,0.6,abs(normalize(world_normal).y));}
	float front=exp(-pow((r-fill)*10.0,2.0));
	float rays=pow(0.5+0.5*cos(atan(world_position.z-center.z,world_position.x-center.x)*24.0-r*18.0+seconds*0.4),5.0);
	ALBEDO=mix(vec3(0.06,0.62,1.0),vec3(0.42,0.2,1.0),r);
	EMISSION=ALBEDO;
	ALPHA=level*coverage*(0.25+front*0.2+rays*0.08);
}
