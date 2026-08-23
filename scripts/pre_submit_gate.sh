#!/usr/bin/env bash
# Run the repository's complete, CI-aligned pre-submit gate.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
BASE_SHA=""
STAGE="commit"
NO_CACHE=0
DIRECT_FULL=0
CURRENT_STEP="argument validation"
TEMP_ROOT=""
CANDIDATE_ROOT="$PROJECT_ROOT"

usage() {
    cat <<'EOF'
Usage: scripts/pre_submit_gate.sh [--base-sha COMMIT]
       [--stage commit|push|full]

The default commit stage is dispatched through the affected validation gate.
The internal --direct-full flag runs the asynchronous/release backstop directly
while still reusing valid test bundles. The legacy main and --direct-main names
remain temporary aliases for full during the ruleset transition.
EOF
}

fail() {
    echo "❌ pre-submit gate: $1" >&2
    exit 1
}

on_exit() {
    local status=$?
    if [[ "$status" -ne 0 ]]; then
        echo "❌ pre-submit gate stopped at: $CURRENT_STEP" >&2
    fi
    if [[ -n "$TEMP_ROOT" && -d "$TEMP_ROOT" ]]; then
        rm -rf -- "$TEMP_ROOT"
    fi
    exit "$status"
}

trap on_exit EXIT

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-sha)
            [[ $# -ge 2 ]] || fail "--base-sha requires a commit"
            BASE_SHA="$2"
            shift 2
            ;;
        --base-sha=*)
            BASE_SHA="${1#*=}"
            shift
            ;;
        --stage)
            [[ $# -ge 2 ]] || fail "--stage requires commit, push or full"
            STAGE="$2"
            shift 2
            ;;
        --stage=*)
            STAGE="${1#*=}"
            shift
            ;;
        --no-cache)
            NO_CACHE=1
            shift
            ;;
        --direct-main)
            DIRECT_FULL=1
            shift
            ;;
        --direct-full)
            DIRECT_FULL=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

case "$STAGE" in
    commit|push|full) ;;
    main)
        echo "warning: --stage main is deprecated; using --stage full" >&2
        STAGE="full"
        ;;
    *) fail "--stage must be commit, push or full" ;;
esac

if [[ "$DIRECT_FULL" -eq 0 ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
    [[ -x "$PYTHON_BIN" ]] || fail "missing repository interpreter: $PYTHON_BIN"
    VALIDATION_ARGS=(
        --stage "$STAGE" --base-sha "$BASE_SHA"
    )
    if (( NO_CACHE )); then
        VALIDATION_ARGS+=(--no-cache)
    fi
    exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/quality/validation/gate.py" \
        "${VALIDATION_ARGS[@]}"
fi
[[ "$STAGE" == "full" ]] || fail "--direct-full is only valid with --stage full"

CURRENT_STEP="resolving the immutable base commit"
if [[ -z "$BASE_SHA" ]]; then
    BASE_SHA="$(git -C "$PROJECT_ROOT" rev-parse 'origin/main^{commit}' 2>/dev/null || true)"
fi
[[ -n "$BASE_SHA" ]] || fail "cannot resolve origin/main; fetch the remote base first"
git -C "$PROJECT_ROOT" cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || \
    fail "base commit is not present locally: $BASE_SHA"

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
UV_BIN="$(command -v uv 2>/dev/null || true)"
PNPM_BIN="$(command -v pnpm 2>/dev/null || true)"

CURRENT_STEP="checking required local tools"
[[ -x "$PYTHON_BIN" ]] || fail "missing repository interpreter: $PYTHON_BIN"
[[ -n "$UV_BIN" ]] || fail "uv is unavailable"
[[ -n "$PNPM_BIN" ]] || fail "pnpm is unavailable"
command -v git >/dev/null 2>&1 || fail "git is unavailable"
command -v node >/dev/null 2>&1 || fail "Node.js is unavailable"
node_version="$(node --version)"
node_major="${node_version#v}"
node_major="${node_major%%.*}"
(( node_major >= 20 )) || fail "Node.js 20+ is required, found $node_version"
[[ "$(pnpm --version)" == "10.12.1" ]] || \
    fail "pnpm 10.12.1 is required, found $(pnpm --version)"

UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/elfienest-uv-cache}"
PRE_COMMIT_HOME="${PRE_COMMIT_HOME:-/tmp/elfienest-precommit}"
VALIDATION_CACHE_ROOT="${ELFIENEST_VALIDATION_CACHE_ROOT:-$PROJECT_ROOT/build/validation-cache}"
export UV_CACHE_DIR PRE_COMMIT_HOME

run_step() {
    CURRENT_STEP="$1"
    shift
    echo
    echo "==> $CURRENT_STEP"
    "$@"
}

run_in_dir() {
    local directory="$1"
    shift
    (cd "$directory" && "$@")
}

copy_base_file() {
    local relative_path="$1"
    local destination_root="$2"
    local destination="$destination_root/$relative_path"
    mkdir -p "$(dirname "$destination")"
    git -C "$CANDIDATE_ROOT" show "$BASE_SHA:$relative_path" > "$destination"
}

run_candidate_python() {
    (cd "$CANDIDATE_ROOT" && \
        PYTHONPATH="$CANDIDATE_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        "$PYTHON_BIN" "$@")
}

run_immutable_base_python() {
    local base_root="$1"
    shift
    (cd "$CANDIDATE_ROOT" && \
        PYTHONPATH="$base_root" \
        "$PYTHON_BIN" "$@")
}

prepare_candidate_tree() {
    local tracked_changes
    local untracked_changes
    local patch_file
    local relative_path
    local source_path
    local destination_path

    tracked_changes="$(git -C "$PROJECT_ROOT" diff --name-only "$BASE_SHA" --)"
    untracked_changes="$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard)"
    if [[ -z "$tracked_changes" && -z "$untracked_changes" ]]; then
        CANDIDATE_ROOT="$PROJECT_ROOT"
        return
    fi

    [[ -n "$TEMP_ROOT" ]] || \
        TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-submit-gate.XXXXXX")"
    CANDIDATE_ROOT="$TEMP_ROOT/repository"
    git clone --quiet --local --no-hardlinks "$PROJECT_ROOT" "$CANDIDATE_ROOT"
    git -C "$CANDIDATE_ROOT" checkout --quiet --detach "$BASE_SHA"

    patch_file="$TEMP_ROOT/worktree.patch"
    git -C "$PROJECT_ROOT" diff --binary "$BASE_SHA" -- . > "$patch_file"
    if [[ -s "$patch_file" ]]; then
        git -C "$CANDIDATE_ROOT" apply --index --whitespace=nowarn "$patch_file"
    fi

    while IFS= read -r relative_path; do
        [[ -n "$relative_path" ]] || continue
        source_path="$PROJECT_ROOT/$relative_path"
        destination_path="$CANDIDATE_ROOT/$relative_path"
        mkdir -p "$(dirname "$destination_path")"
        cp -R -P -- "$source_path" "$destination_path"
    done <<< "$untracked_changes"

    git -C "$CANDIDATE_ROOT" add --all
    git -C "$CANDIDATE_ROOT" \
        -c user.name="ElfieNest pre-submit gate" \
        -c user.email="pre-submit-gate@localhost" \
        commit --quiet -m "temporary pre-submit candidate"
}

run_candidate_architecture_gate() {
    local ratchet_root
    local scanner_root
    local scanner_dir
    local classifier_root
    local classifier
    local classifier_path
    local structural_path
    local app_scanner_path
    local system_scanner_path
    local file

    if [[ -f "$CANDIDATE_ROOT/test/architecture/baselines/app_layer.py" ]]; then
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/governance/boundaries/app_layers.py" \
            --project-root "$CANDIDATE_ROOT" \
            --baseline "$CANDIDATE_ROOT/test/architecture/baselines/app_layer.py" \
            --mode exact
    else
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/governance/boundaries/app_layers.py" \
            --project-root "$CANDIDATE_ROOT" --mode deny-all
    fi

    if [[ -f "$CANDIDATE_ROOT/test/architecture/baselines/system_layer.py" ]]; then
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/governance/boundaries/system_layers.py" \
            --project-root "$CANDIDATE_ROOT" \
            --baseline "$CANDIDATE_ROOT/test/architecture/baselines/system_layer.py" \
            --mode exact
    else
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/governance/boundaries/system_layers.py" \
            --project-root "$CANDIDATE_ROOT" --mode deny-all
    fi

    run_candidate_python \
        "$CANDIDATE_ROOT/scripts/governance/boundaries/effective_dependencies/scan.py" \
        --project-root "$CANDIDATE_ROOT"
    run_candidate_python \
        "$CANDIDATE_ROOT/scripts/governance/boundaries/structural_scope.py" \
        --project-root "$CANDIDATE_ROOT"
    run_candidate_python \
        "$CANDIDATE_ROOT/scripts/governance/persistence/scan.py" \
        --project-root "$CANDIDATE_ROOT" --base-sha "$BASE_SHA" --check

    classifier_root="$TEMP_ROOT/base-governance"
    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/governance/change_policy.py" 2>/dev/null; then
        classifier_path="scripts/governance/change_policy.py"
        structural_path="scripts/governance/boundaries/structural_scope.py"
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/check_governance_change.py" 2>/dev/null; then
        classifier_path="scripts/architecture/check_governance_change.py"
        structural_path="scripts/architecture/structural_scope_scan.py"
    else
        fail "base branch has governance contract but no change classifier"
    fi
    copy_base_file "$classifier_path" "$classifier_root"
    copy_base_file "$structural_path" "$classifier_root"
    classifier="$classifier_root/$classifier_path"
    run_immutable_base_python "$classifier_root" \
        "$classifier" --base-sha "$BASE_SHA"

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/governance/boundaries/app_layers.py" 2>/dev/null; then
        app_scanner_path="scripts/governance/boundaries/app_layers.py"
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/app_layer_scan.py" 2>/dev/null; then
        app_scanner_path="scripts/architecture/app_layer_scan.py"
    else
        app_scanner_path=""
    fi
    if [[ -n "$app_scanner_path" ]]; then
        ratchet_root="$TEMP_ROOT/app-ratchet"
        copy_base_file "$app_scanner_path" "$ratchet_root"
        if git -C "$CANDIDATE_ROOT" cat-file -e \
            "$BASE_SHA:test/architecture/baselines/app_layer.py" 2>/dev/null; then
            copy_base_file "test/architecture/baselines/app_layer.py" "$ratchet_root"
            run_immutable_base_python "$ratchet_root" \
                "$ratchet_root/$app_scanner_path" \
                --project-root "$CANDIDATE_ROOT" \
                --baseline "$ratchet_root/test/architecture/baselines/app_layer.py" \
                --mode subset
        else
            run_immutable_base_python "$ratchet_root" \
                "$ratchet_root/$app_scanner_path" \
                --project-root "$CANDIDATE_ROOT" --mode deny-all
        fi
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:docs/developer/contracts/repository-governance.md" 2>/dev/null; then
        fail "base branch has governance contract but no App scanner"
    fi

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/governance/boundaries/system_layers.py" 2>/dev/null; then
        system_scanner_path="scripts/governance/boundaries/system_layers.py"
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/system_layer_scan.py" 2>/dev/null; then
        system_scanner_path="scripts/architecture/system_layer_scan.py"
    else
        system_scanner_path=""
    fi
    if [[ -n "$system_scanner_path" ]]; then
        ratchet_root="$TEMP_ROOT/system-ratchet"
        copy_base_file "$system_scanner_path" "$ratchet_root"
        if git -C "$CANDIDATE_ROOT" cat-file -e \
            "$BASE_SHA:test/architecture/baselines/system_layer.py" 2>/dev/null; then
            copy_base_file "test/architecture/baselines/system_layer.py" "$ratchet_root"
            run_immutable_base_python "$ratchet_root" \
                "$ratchet_root/$system_scanner_path" \
                --project-root "$CANDIDATE_ROOT" \
                --baseline "$ratchet_root/test/architecture/baselines/system_layer.py" \
                --mode subset
        else
            run_immutable_base_python "$ratchet_root" \
                "$ratchet_root/$system_scanner_path" \
                --project-root "$CANDIDATE_ROOT" --mode deny-all
        fi
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:docs/developer/contracts/system.md" 2>/dev/null; then
        fail "base branch has system contract but no system scanner"
    fi

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/governance/boundaries/effective_dependencies/scan.py" 2>/dev/null; then
        scanner_root="$TEMP_ROOT/effective-ratchet"
        for file in python.py scan.py targets.py text.py; do
            copy_base_file \
                "scripts/governance/boundaries/effective_dependencies/$file" \
                "$scanner_root"
        done
        run_immutable_base_python "$scanner_root" \
            "$scanner_root/scripts/governance/boundaries/effective_dependencies/scan.py" \
            --project-root "$CANDIDATE_ROOT"
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/effective_dependency_scan.py" 2>/dev/null; then
        scanner_root="$TEMP_ROOT/effective-ratchet"
        for file in effective_dependency_python.py effective_dependency_scan.py \
            effective_dependency_targets.py effective_dependency_text.py; do
            copy_base_file "scripts/architecture/$file" "$scanner_root"
        done
        run_immutable_base_python "$scanner_root" \
            "$scanner_root/scripts/architecture/effective_dependency_scan.py" \
            --project-root "$CANDIDATE_ROOT"
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:docs/developer/decisions/0012-effective-dependency-targets.md" 2>/dev/null; then
        fail "base branch has ADR-0012 but no effective dependency scanner"
    fi
}

CURRENT_STEP="building a candidate tree that includes unstaged changes"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-submit-gate.XXXXXX")"
prepare_candidate_tree

CURRENT_STEP="running immutable-base architecture governance checks"
run_candidate_architecture_gate

run_step "checking the dependency lock" \
    "$UV_BIN" lock --check
run_step "checking Node and pnpm manifests" \
    bash "$PROJECT_ROOT/scripts/quality/checks/node_toolchain.sh"
run_step "checking the Python quality baseline" \
    "$UV_BIN" run --no-sync python "$PROJECT_ROOT/scripts/quality/checks/python_baseline.py"
run_step "running pre-commit hooks and the secret scanner" \
    env PRE_COMMIT_HOME="$PRE_COMMIT_HOME" \
    "$UV_BIN" run --no-sync pre-commit run --all-files
run_step "installing Developer Tools frontend dependencies" \
    run_in_dir "$PROJECT_ROOT/devtools/web" "$PNPM_BIN" install --frozen-lockfile
run_step "running the exact environment capability preflight" \
    "$UV_BIN" run --no-sync python "$PROJECT_ROOT/scripts/quality/checks/environment.py"
BUNDLE_ARGS=(
    --all --base-sha "$BASE_SHA" --cache-root "$VALIDATION_CACHE_ROOT"
)
if (( NO_CACHE )); then
    BUNDLE_ARGS+=(--no-cache)
fi
run_step "running missing CI test bundles and combining coverage evidence" \
    "$PYTHON_BIN" "$PROJECT_ROOT/scripts/quality/validation/test_bundles.py" \
    "${BUNDLE_ARGS[@]}"
run_step "checking the pinned CPython runtime" \
    "$PYTHON_BIN" -c \
    'import platform,sys; raise SystemExit(0 if sys.implementation.name == "cpython" and platform.python_version() == "3.9.25" else 1)'
run_step "running the CLI version smoke test" \
    "$PYTHON_BIN" "$PROJECT_ROOT/scripts/elfienest.py" version
run_step "installing documentation dependencies" \
    run_in_dir "$PROJECT_ROOT/docs" "$PNPM_BIN" install --frozen-lockfile
run_step "building the documentation site" \
    run_in_dir "$PROJECT_ROOT/docs" "$PNPM_BIN" build
run_step "checking the final diff format" \
    git -C "$PROJECT_ROOT" diff --check
run_step "checking the final staged diff format" \
    git -C "$PROJECT_ROOT" diff --cached --check

echo
echo "✅ full backstop passed for candidate against base $BASE_SHA"
