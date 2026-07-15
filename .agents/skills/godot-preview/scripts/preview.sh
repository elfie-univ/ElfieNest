#!/bin/bash

# Arguments
SCRIPT_TO_RUN=$1

if [ -n "$SCRIPT_TO_RUN" ]; then
    echo "Running Godot script: $SCRIPT_TO_RUN"
    # Assuming Godot project is in the assets folder or we run it from the script's directory
    # Godot requires running from the project root or specifying it.
    # Let's search upward from the script for project.godot
    SCRIPT_DIR=$(dirname "$SCRIPT_TO_RUN")
    PROJECT_DIR=$SCRIPT_DIR
    while [ "$PROJECT_DIR" != "/" ]; do
        if [ -f "$PROJECT_DIR/project.godot" ]; then
            break
        fi
        PROJECT_DIR=$(dirname "$PROJECT_DIR")
    done

    if [ "$PROJECT_DIR" == "/" ]; then
        echo "Could not find project.godot automatically. Attempting to run from ElfieNest/godot directory."
        PROJECT_DIR="/Users/zhenli/git-code/ElfieNest/godot"
    fi

    cd "$PROJECT_DIR" || exit 1
    echo "Executing in project directory: $PROJECT_DIR"
    godot --headless -s "$SCRIPT_TO_RUN"

    if [ $? -ne 0 ]; then
        echo "Error: Godot script execution failed!"
        exit 1
    fi
    echo "Godot script execution finished."
fi

echo "Activating Godot Editor..."
osascript -e 'tell application "Godot" to activate'

# Give the editor a moment to come to the foreground and potentially show the reload popup
sleep 2

SCREENSHOT_PATH="/tmp/godot_preview.png"
echo "Taking screenshot..."
screencapture -x "$SCREENSHOT_PATH"

echo "Screenshot successfully saved to $SCREENSHOT_PATH."
echo "You can now use the 'view_file' tool to inspect it!"
