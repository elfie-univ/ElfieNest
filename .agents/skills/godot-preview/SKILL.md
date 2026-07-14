---
name: godot-preview
description: Automates running a Godot GDScript and capturing a screenshot of the resulting scene in the Godot Editor so the agent can see the visual output.
---

# Godot Preview Skill

This skill allows you to automatically execute a Godot script (like a procedural room generation script), and then capture a screenshot of the currently open Godot Editor to verify the results visually.

## When to use this skill
Use this skill when:
- The user asks you to "preview", "screenshot", or "view" a Godot scene or script output.
- You have written a Godot script that modifies or generates a `.tscn` scene, and you want to see if your code worked correctly without asking the user to manually take a screenshot for you.

## How to use this skill
1. Run the bash script located at `scripts/preview.sh` in this skill's folder using the `run_command` tool.
   - You can pass an **optional** argument to the script: the absolute path to the GDScript you want to run before taking the screenshot.
   - Example: `bash /Users/zhenli/git-code/ElfieNest/.agents/skills/godot-preview/scripts/preview.sh /Users/zhenli/git-code/ElfieNest/scripts/rebuild_rooms.gd`
   - Or simply: `bash /Users/zhenli/git-code/ElfieNest/.agents/skills/godot-preview/scripts/preview.sh` to just take a screenshot of whatever is currently on the screen.
2. The script will:
   - Run your GDScript (if provided) in headless mode.
   - Activate the Godot Editor window to bring it to the foreground.
   - Wait a few seconds for any "File was modified outside Godot" popup to appear or for the scene to refresh.
   - Take a screenshot and save it to `/tmp/godot_preview.png`.
3. After the script finishes successfully, use the `view_file` tool to open `/tmp/godot_preview.png` and analyze the visual result!
