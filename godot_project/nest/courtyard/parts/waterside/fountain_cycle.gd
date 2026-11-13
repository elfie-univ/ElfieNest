extends RefCounted
## A full fixed score, a full random round, and two four-second handoffs.
const FIXED=preload("res://nest/courtyard/parts/waterside/fountain_score.gd")
const RANDOM=preload("res://nest/courtyard/parts/waterside/fountain_random.gd")
const PERIOD:=472.0
var random=RANDOM.new()

func sample(seconds:float,seed_value:int)->Array[Dictionary]:
 var time:=maxf(seconds,0.0)
 var round_index:=floori(time/PERIOD)
 var local:=fposmod(time,PERIOD)
 var offset:=float(round_index)*384.0
 if local<80.0: return FIXED.sample(local)
 if local<84.0: return blend(FIXED.sample(80.0),random.sample(offset,seed_value),smoothstep(80.0,84.0,local))
 if local<468.0: return random.sample(offset+local-84.0,seed_value)
 return blend(random.sample(offset+384.0,seed_value),FIXED.sample(0.0),smoothstep(468.0,472.0,local))

static func blend(a:Array[Dictionary],b:Array[Dictionary],weight:float)->Array[Dictionary]:
 var result:Array[Dictionary]=[]
 for i in range(9):
  var entry:Dictionary=a[i].duplicate(true)
  for key:String in ["height","energy","level"]:
   entry[key]=lerpf(float(a[i][key]),float(b[i][key]),weight)
  entry.color=(a[i].color as Color).lerp(b[i].color,weight)
  if i>0:
   entry.inward=lerpf(float(a[i].inward),float(b[i].inward),weight)
  else:
   for key:String in ["flower_height","flower_reach","flower_energy","climax"]:
    entry[key]=lerpf(float(a[i][key]),float(b[i][key]),weight)
   entry.light_color=(a[i].light_color as Color).lerp(b[i].light_color,weight)
   var heights:=PackedFloat32Array();var reaches:=PackedFloat32Array();var colors:=PackedColorArray()
   for j in range(8):
    heights.append(lerpf(a[i].flower_heights[j],b[i].flower_heights[j],weight))
    reaches.append(lerpf(a[i].flower_reaches[j],b[i].flower_reaches[j],weight))
    colors.append(a[i].flower_colors[j].lerp(b[i].flower_colors[j],weight))
   entry.flower_heights=heights;entry.flower_reaches=reaches;entry.flower_colors=colors
  result.append(entry)
 return result
