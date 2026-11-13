extends SceneTree
const CYCLE=preload("res://nest/courtyard/parts/waterside/fountain_cycle.gd")
const FIXED=preload("res://nest/courtyard/parts/waterside/fountain_score.gd")
const RANDOM=preload("res://nest/courtyard/parts/waterside/fountain_random.gd")
func _initialize()->void:
 var cycle=CYCLE.new()
 var random=RANDOM.new()
 var failures:=0
 for t:float in [0.0,10.0,40.0,79.0]:
  if absf(cycle.sample(t,42)[0].height-FIXED.sample(t)[0].height)>0.001: failures+=1
 for t:float in [1.0,80.0,200.0,383.0]:
  if absf(cycle.sample(84.0+t,42)[1].height-random.sample(t,42)[1].height)>0.001: failures+=1
 for t:float in [80.0,84.0,468.0,472.0]:
  var a:Array=cycle.sample(t-0.001,42)
  var b:Array=cycle.sample(t+0.001,42)
  for i in range(9):
   if absf(a[i].height-b[i].height)>0.05: failures+=1
   if i>0 and absf(a[i].inward-b[i].inward)>0.05: failures+=1
 print("FOUNTAIN_CYCLE failures=",failures)
 quit(0 if failures==0 else 1)
