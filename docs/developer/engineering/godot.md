# Godot

Godot is the single source of truth for houses, geometry, world coordinates,
motion, collision, characters and rendering.

## What belongs in Godot

- Scenes, nodes, rooms and furniture assets;
- Character models, animations, collision and navigation;
- Rendering and spatial interaction of the Web Runtime;
- The adapter layer that exchanges events with the Python Core.

## What does not belong in Godot

- An Elfie's complete identity, memory and personality;
- The Nest's product accounts, adoption and chat rules;
- House blueprints or coordinate facts duplicated on the Python side.

Before opening, running or screenshotting, first check the Godot version in
`project.godot` and any existing processes, then follow the flow in the
[Godot README](https://github.com/elfie-univ/ElfieNest/blob/main/godot_project/README.md)
and `godot_project/WEB_EXPORT.md`.

## Resident lifecycle integration

The authority Gateway uses protocol 4. Environment commands carry `life_phase`
independently of lighting overrides: day/dawn holds every door open; dusk/night
uses the existing proximity and obstruction controls. All residents may enter
all rooms.

Live Nest sessions select Brain embodied input. Hosting requires an authoritative
sleeping pose at the resident's own bed; the virtual body remains under its cover
while the external body is selected. Committed admission identity and time drive
the one-way fourth-floor arrival presentation; reconnecting does not restart its
clock. There is no departure teleport or audio presentation.

Focused scene verification: `bash scripts/quality/checks/godot_host.sh
res://scripts/test/test_resident_lifecycle.gd`. Real-device hosting and final visual
acceptance remain separate checks.
