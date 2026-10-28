shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;
uniform float seconds = 0.0;
uniform float level = 0.0;
uniform float formation = 1.0;
varying vec3 local_position;
void vertex(){local_position=VERTEX;}
void fragment(){
	float angle=atan(local_position.z,local_position.x);
	float spiral=pow(0.5+0.5*cos(angle-seconds*1.3-local_position.y*2.7),8.0);
	float end_fade=1.0-smoothstep(1.15,1.45,abs(local_position.y));
	float from_core=(local_position.y+1.45)/2.9;
	float formed=1.0-smoothstep(formation-0.08,formation,from_core);
	ALBEDO=mix(vec3(0.14,0.62,0.88),vec3(0.55,0.4,1.0),spiral);
	ALPHA=level*formed*end_fade*(0.025+spiral*0.20);
}
