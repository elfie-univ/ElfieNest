#!/usr/bin/env bash
# Run the repository's complete, CI-aligned pre-submit gate.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
BASE_SHA=""
STAGE="main"
NO_CACHE=0
DIRECT_MAIN=0
FIX_FORMAT=0
CURRENT_STEP="argument validation"
TEMP_ROOT=""
CANDIDATE_ROOT="$PROJECT_ROOT"

usage() {
    cat <<'EOF'
Usage: scripts/pre_submit_gate.sh [--base-sha COMMIT]
       [--stage commit|push|main] [--fix-format] [--no-cache]

The default main stage is dispatched through the reusable tiered gate. The
internal --direct-main flag runs the CI-aligned main backstop directly while
still reusing valid test bundles. --fix-format safely formats selected dirty
or untracked Python files before checks. --no-cache disables evidence reuse
without changing the selected validation tier.
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
            [[ $# -ge 2 ]] || fail "--stage requires commit, push or main"
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
        --fix-format)
            FIX_FORMAT=1
            shift
            ;;
        --direct-main)
            DIRECT_MAIN=1
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
    commit|push|main) ;;
    *) fail "--stage must be commit, push or main" ;;
esac

if [[ "$DIRECT_MAIN" -eq 0 ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
    [[ -x "$PYTHON_BIN" ]] || fail "missing repository interpreter: $PYTHON_BIN"
    VALIDATION_ARGS=(
        --stage "$STAGE" --base-sha "$BASE_SHA"
    )
    if (( NO_CACHE )); then
        VALIDATION_ARGS+=(--no-cache)
    fi
    if (( FIX_FORMAT )); then
        VALIDATION_ARGS+=(--fix-format)
    fi
    exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/architecture/validation_gate.py" \
        "${VALIDATION_ARGS[@]}"
fi

(( FIX_FORMAT == 0 )) || fail "--fix-format is unavailable with internal --direct-main"

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

ensure_pnpm_dependencies() {
    local directory="$1"
    local relative_root="$2"
    local modules_metadata="$directory/node_modules/.modules.yaml"
    local reusable_modules="$PROJECT_ROOT/$relative_root/node_modules"

    if [[ -f "$modules_metadata" ]] && \
        git -C "$CANDIDATE_ROOT" diff --quiet "$BASE_SHA" -- \
            "$relative_root/package.json" "$relative_root/pnpm-lock.yaml"; then
        echo "✅ reusing installed pnpm dependencies: $relative_root"
        return 0
    fi

    if [[ "$directory" != "$PROJECT_ROOT/$relative_root" ]] && \
        [[ -f "$reusable_modules/.modules.yaml" ]] && \
        git -C "$PROJECT_ROOT" diff --quiet "$BASE_SHA" -- \
            "$relative_root/package.json" "$relative_root/pnpm-lock.yaml"; then
        # Keep the candidate's node_modules root writable.  VitePress and
        # similar tools create package links during a build; linking the whole
        # directory would mutate another worktree (and can fail with EPERM).
        # Reuse the immutable pnpm package store and copy only the small root
        # link/metadata layer into the candidate.
        mkdir -p "$directory/node_modules"
        ln -s "$reusable_modules/.pnpm" "$directory/node_modules/.pnpm"
        local entry name
        for entry in "$reusable_modules"/* "$reusable_modules"/.[!.]*; do
            name="${entry##*/}"
            [[ "$name" == ".pnpm" ]] && continue
            [[ -e "$entry" || -L "$entry" ]] || continue
            if [[ -d "$entry" && ! -L "$entry" ]]; then
                cp -R -P "$entry" "$directory/node_modules/$name"
            else
                cp -P "$entry" "$directory/node_modules/$name"
            fi
        done
        echo "✅ reusing installed pnpm dependencies: $relative_root"
        return 0
    fi

    run_in_dir "$directory" "$PNPM_BIN" install --frozen-lockfile \
        --config.fetch-retries=0 --config.fetch-timeout=10000
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

    if [[ -d "$PROJECT_ROOT/.venv" ]]; then
        ln -s "$PROJECT_ROOT/.venv" "$CANDIDATE_ROOT/.venv"
    fi
}

run_candidate_architecture_gate() {
    local ratchet_root
    local scanner_root
    local scanner_dir
    local classifier_root
    local classifier
    local file

    if [[ -f "$CANDIDATE_ROOT/test/architecture/baselines/app_layer.py" ]]; then
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/architecture/app_layer_scan.py" \
            --project-root "$CANDIDATE_ROOT" \
            --baseline "$CANDIDATE_ROOT/test/architecture/baselines/app_layer.py" \
            --mode exact
    else
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/architecture/app_layer_scan.py" \
            --project-root "$CANDIDATE_ROOT" --mode deny-all
    fi

    if [[ -f "$CANDIDATE_ROOT/test/architecture/baselines/system_layer.py" ]]; then
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/architecture/system_layer_scan.py" \
            --project-root "$CANDIDATE_ROOT" \
            --baseline "$CANDIDATE_ROOT/test/architecture/baselines/system_layer.py" \
            --mode exact
    else
        run_candidate_python \
            "$CANDIDATE_ROOT/scripts/architecture/system_layer_scan.py" \
            --project-root "$CANDIDATE_ROOT" --mode deny-all
    fi

    run_candidate_python \
        "$CANDIDATE_ROOT/scripts/architecture/effective_dependency_scan.py" \
        --project-root "$CANDIDATE_ROOT"
    run_candidate_python \
        "$CANDIDATE_ROOT/scripts/architecture/structural_scope_scan.py" \
        --project-root "$CANDIDATE_ROOT"
    run_candidate_python \
        "$CANDIDATE_ROOT/scripts/architecture/database_change_scan.py" \
        --project-root "$CANDIDATE_ROOT" --base-sha "$BASE_SHA" --check

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/check_governance_change.py" 2>/dev/null; then
        classifier_root="$TEMP_ROOT/base-governance"
        classifier="${classifier_root}/scripts/architecture/check_governance_change.py"
        copy_base_file "scripts/architecture/check_governance_change.py" "$TEMP_ROOT/base-governance"
        if git -C "$CANDIDATE_ROOT" cat-file -e \
            "$BASE_SHA:scripts/architecture/structural_scope_scan.py" 2>/dev/null; then
            copy_base_file "scripts/architecture/structural_scope_scan.py" "$TEMP_ROOT/base-governance"
        fi
    else
        classifier_root="$CANDIDATE_ROOT"
        classifier="$CANDIDATE_ROOT/scripts/architecture/check_governance_change.py"
    fi
    run_candidate_python "$classifier" --base-sha "$BASE_SHA"

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/app_layer_scan.py" 2>/dev/null; then
        ratchet_root="$TEMP_ROOT/app-ratchet"
        copy_base_file "scripts/architecture/app_layer_scan.py" "$ratchet_root"
        if git -C "$CANDIDATE_ROOT" cat-file -e \
            "$BASE_SHA:test/architecture/baselines/app_layer.py" 2>/dev/null; then
            copy_base_file "test/architecture/baselines/app_layer.py" "$ratchet_root"
            run_candidate_python "$ratchet_root/scripts/architecture/app_layer_scan.py" \
                --project-root "$CANDIDATE_ROOT" \
                --baseline "$ratchet_root/test/architecture/baselines/app_layer.py" \
                --mode subset
        else
            run_candidate_python "$ratchet_root/scripts/architecture/app_layer_scan.py" \
                --project-root "$CANDIDATE_ROOT" --mode deny-all
        fi
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:docs/developer/contracts/repository-governance.md" 2>/dev/null; then
        fail "base branch has governance contract but no App scanner"
    fi

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/system_layer_scan.py" 2>/dev/null; then
        ratchet_root="$TEMP_ROOT/system-ratchet"
        copy_base_file "scripts/architecture/system_layer_scan.py" "$ratchet_root"
        if git -C "$CANDIDATE_ROOT" cat-file -e \
            "$BASE_SHA:test/architecture/baselines/system_layer.py" 2>/dev/null; then
            copy_base_file "test/architecture/baselines/system_layer.py" "$ratchet_root"
            run_candidate_python "$ratchet_root/scripts/architecture/system_layer_scan.py" \
                --project-root "$CANDIDATE_ROOT" \
                --baseline "$ratchet_root/test/architecture/baselines/system_layer.py" \
                --mode subset
        else
            run_candidate_python "$ratchet_root/scripts/architecture/system_layer_scan.py" \
                --project-root "$CANDIDATE_ROOT" --mode deny-all
        fi
    elif git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:docs/developer/contracts/system.md" 2>/dev/null; then
        fail "base branch has system contract but no system scanner"
    fi

    if git -C "$CANDIDATE_ROOT" cat-file -e \
        "$BASE_SHA:scripts/architecture/effective_dependency_scan.py" 2>/dev/null; then
        scanner_root="$TEMP_ROOT/effective-ratchet"
        for file in effective_dependency_python.py effective_dependency_scan.py \
            effective_dependency_targets.py effective_dependency_text.py; do
            copy_base_file "scripts/architecture/$file" "$scanner_root"
        done
        run_candidate_python "$scanner_root/scripts/architecture/effective_dependency_scan.py" \
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
    run_in_dir "$CANDIDATE_ROOT" "$UV_BIN" lock --check
run_step "checking Node and pnpm manifests" \
    bash "$CANDIDATE_ROOT/scripts/check_node_toolchain.sh" "$CANDIDATE_ROOT"
run_step "checking the Python quality baseline" \
    run_candidate_python "$CANDIDATE_ROOT/scripts/check_quality_baseline.py"
run_step "running the repository-wide secret scanner" \
    run_in_dir "$CANDIDATE_ROOT" env PRE_COMMIT_HOME="$PRE_COMMIT_HOME" \
    "$PYTHON_BIN" -m pre_commit run gitleaks --all-files
run_step "ensuring Developer Tools frontend dependencies" \
    ensure_pnpm_dependencies "$CANDIDATE_ROOT/devtools/web" "devtools/web"
run_step "running the exact environment capability preflight" \
    run_candidate_python "$CANDIDATE_ROOT/scripts/check_quality_environment.py"
BUNDLE_ARGS=(
    --all --base-sha "$BASE_SHA" --cache-root "$VALIDATION_CACHE_ROOT"
)
if (( NO_CACHE )); then
    BUNDLE_ARGS+=(--no-cache)
fi
run_step "running missing CI test bundles and combining coverage evidence" \
    run_candidate_python "$CANDIDATE_ROOT/scripts/architecture/validation_test_bundles.py" \
    "${BUNDLE_ARGS[@]}"
run_step "checking the pinned CPython runtime" \
    run_candidate_python -c \
    'import platform,sys; raise SystemExit(0 if sys.implementation.name == "cpython" and platform.python_version() == "3.9.25" else 1)'
run_step "running the CLI version smoke test" \
    run_candidate_python "$CANDIDATE_ROOT/scripts/elfienest.py" version
run_step "ensuring documentation dependencies" \
    ensure_pnpm_dependencies "$CANDIDATE_ROOT/docs" "docs"
run_step "building the documentation site" \
    run_in_dir "$CANDIDATE_ROOT/docs" "$PNPM_BIN" build
run_step "checking the final diff format" \
    git -C "$CANDIDATE_ROOT" diff --check "$BASE_SHA" --
run_step "checking the final staged diff format" \
    git -C "$CANDIDATE_ROOT" diff --cached --check "$BASE_SHA" --

echo
echo "✅ pre-submit gate passed for candidate against base $BASE_SHA"
