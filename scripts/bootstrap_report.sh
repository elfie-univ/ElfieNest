#!/bin/bash
# Machine-readable report duties for the unified dependency orchestrator.

bootstrap_component_state() {
    local check_function="$1"

    if "$check_function"; then
        printf '%s\n' "ready"
    else
        printf '%s\n' "missing"
    fi
}

bootstrap_report_component() {
    local name="$1"
    local required="$2"
    local state="$3"

    printf '    "%s": {"required": %s, "state": "%s"}' \
        "$name" "$required" "$state"
}

emit_bootstrap_report() {
    local python_state
    local node_state
    local frontend_state
    local godot_toolchain_state
    local godot_state
    local ollama_state
    local elfie_home_state
    local electron_state
    local overall_state="ready"
    local exit_code=0

    python_state="$(bootstrap_component_state check_python)"
    frontend_state="$(bootstrap_component_state check_frontend)"
    godot_toolchain_state="$(bootstrap_component_state check_godot_toolchain)"
    godot_state="$(bootstrap_component_state check_godot_web)"
    ollama_state="$(ollama_capability_state)"
    elfie_home_state="$(bootstrap_component_state check_elfie_home)"
    node_state="$(bootstrap_component_state check_node)"
    electron_state="$(bootstrap_component_state check_electron)"

    if [[ "$python_state" == "missing" || "$frontend_state" == "missing" || "$godot_toolchain_state" == "missing" || "$godot_state" == "missing" ]]; then
        overall_state="failed"
        exit_code=1
    fi
    if [[ "$TIER" == "dev" && ( "$node_state" == "missing" || "$electron_state" == "missing" ) ]]; then
        overall_state="failed"
        exit_code=1
    fi
    if [[ "$overall_state" == "ready" && "$ollama_state" == "optional_missing" ]]; then
        overall_state="degraded"
    fi

    printf '{\n'
    printf '  "schema_version": 1,\n'
    printf '  "tier": "%s",\n' "$TIER"
    printf '  "overall_state": "%s",\n' "$overall_state"
    printf '  "components": {\n'
    bootstrap_report_component "python" true "$python_state"
    printf ',\n'
    bootstrap_report_component "node" "$([[ "$TIER" == "dev" ]] && printf true || printf false)" "$node_state"
    printf ',\n'
    bootstrap_report_component "frontend" true "$frontend_state"
    printf ',\n'
    bootstrap_report_component "godot_toolchain" true "$godot_toolchain_state"
    printf ',\n'
    bootstrap_report_component "godot_web" true "$godot_state"
    printf ',\n'
    bootstrap_report_component "ollama" false "$ollama_state"
    printf ',\n'
    bootstrap_report_component "elfie_home" false "$elfie_home_state"
    printf ',\n'
    bootstrap_report_component "electron" "$([[ "$TIER" == "dev" ]] && printf true || printf false)" "$electron_state"
    printf '\n  }\n'
    printf '}\n'

    return "$exit_code"
}
