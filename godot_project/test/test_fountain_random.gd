extends SceneTree
var failures: Array[String]=[]
func check(ok:bool,message:String)->void:
 if not ok and not failures.has(message): failures.append(message);push_error(message)
func _initialize()->void:
 var programme=load("res://nest/courtyard/parts/waterside/fountain_random.gd").new()
 var replay=load("res://nest/courtyard/parts/waterside/fountain_random.gd").new()
 var seen:Dictionary={}
 for slot in range(32):
  var plan:Dictionary=programme.phrase(slot,42)
  seen[plan.action]=true
  check(plan==replay.phrase(slot,42),"Same seed replays the phrase")
  if slot>0:
   check(plan.action!=programme.phrase(slot-1,42).action,"No immediate action repetition")
  var central_min:=6.0
  var central_max:=0.0
  for step in range(121):
   var t:=float(slot)*24.0+float(step)*0.2
   var state:Array=programme.sample(t,42)
   check(state==replay.sample(t,42),"Samples are deterministic, including backward seeks")
   check(state.size()==9,"Nine nozzle positions")
   var centre:float=maxf(state[0].height,state[0].flower_height)
   central_min=minf(central_min,centre);central_max=maxf(central_max,centre)
   check(centre>=1.5 and centre<=6.001,"Central participates throughout, within six metres")
   var active:=0
   for i in range(1,9):
    check(state[i].height>=0.0 and state[i].height<=4.001,"Outer height stays within four metres")
    check(state[i].height>0.001 or state[i].energy<0.001,"Inactive water has no nozzle light")
    if state[i].height>=0.45: active+=1
   check(active>=4,"Transitions and chases retain a full supporting ensemble")
  check(central_max-central_min>1.0,"Every phrase gives the centre a substantial action")
  var left:Array=programme.sample(float(slot+1)*24.0-0.001,42)
  var right:Array=programme.sample(float(slot+1)*24.0+0.001,42)
  for i in range(9):
   check(absf(left[i].height-right[i].height)<0.02,"Phrase handoffs keep pressure continuous")
 check(seen.size()==16,"All sixteen outer actions occur")
 check(programme.phrase(0,42)!=programme.phrase(0,13579),"Seed changes choreography")
 var stairs:Array=programme.action_sample(6,16.0,1,4.0,0)
 for i in range(1,9):
  check(absf(stairs[i].height-float(i)*0.5)<0.01,"Staircase retains all eight progressively taller columns")
 for action in range(12,mini(16,programme.ACTIONS.size())):
  var state:Array=programme.action_sample(action,10.0,1,4.0,0)
  var vertical:=0
  var inward:=0
  for i in range(1,9):
   if state[i].inward<0.01: vertical+=1
   if state[i].inward>0.99: inward+=1
  check(vertical>0 and inward>0,"Mixed phrases independently aim the outer nozzles")
 var petals:Array=programme.action_sample(1,8.0,1,4.0,0)
 if petals[0].has("flower_heights"):
  check(absf(petals[0].flower_heights[0]-petals[0].flower_heights[1])>0.1,"Alternating flower petals have independent heights")
 else: check(false,"Flower petals need independent pressure")
 print("FOUNTAIN_RANDOM failures=",failures.size()," actions=",seen.size())
 quit(0 if failures.is_empty() else 1)
