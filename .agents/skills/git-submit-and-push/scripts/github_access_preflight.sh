#!/usr/bin/env bash

set -u

probe_token_names=(
  GH_TOKEN
  GITHUB_TOKEN
  GH_ENTERPRISE_TOKEN
  GITHUB_ENTERPRISE_TOKEN
  GH_CONFIG_DIR
)

probe_git_ok=0
probe_gh_ok=0
probe_has_token_override=0
probe_has_config_override=0

if probe_git_path="$(command -v git 2>/dev/null)"; then
  printf 'git_path=%s\n' "$probe_git_path"
  git --version
else
  printf 'git_path=missing\n'
fi

if probe_gh_path="$(command -v gh 2>/dev/null)"; then
  printf 'gh_path=%s\n' "$probe_gh_path"
  gh --version | sed -n '1p'
else
  printf 'gh_path=missing\n'
fi

for probe_token_name in "${probe_token_names[@]}"; do
  if printenv "$probe_token_name" >/dev/null 2>&1; then
    printf 'environment_override=%s\n' "$probe_token_name"
    case "$probe_token_name" in
      GH_TOKEN|GITHUB_TOKEN|GH_ENTERPRISE_TOKEN|GITHUB_ENTERPRISE_TOKEN)
        probe_has_token_override=1
        ;;
      GH_CONFIG_DIR)
        probe_has_config_override=1
        ;;
    esac
  fi
done

if probe_origin="$(git remote get-url origin 2>/dev/null)"; then
  case "$probe_origin" in
    git@*|ssh://*) printf 'git_remote_protocol=ssh\n' ;;
    https://*) printf 'git_remote_protocol=https\n' ;;
    *) printf 'git_remote_protocol=other\n' ;;
  esac
else
  printf 'git_remote_protocol=unavailable\n'
fi

if probe_git_protocol="$(gh config get git_protocol --host github.com 2>/dev/null)"; then
  printf 'gh_git_protocol=%s\n' "$probe_git_protocol"
else
  printf 'gh_git_protocol=unavailable\n'
fi

if env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
  -u GITHUB_ENTERPRISE_TOKEN gh auth token --hostname github.com >/dev/null 2>&1; then
  printf 'gh_stored_credential=available\n'
else
  printf 'gh_stored_credential=unavailable\n'
fi

if (( probe_has_config_override == 1 )); then
  if env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN -u GH_CONFIG_DIR \
    gh auth token --hostname github.com >/dev/null 2>&1; then
    printf 'gh_default_config_credential=available\n'
  else
    printf 'gh_default_config_credential=unavailable\n'
  fi
fi

if probe_login="$(gh api user --jq .login)"; then
  printf 'gh_api_identity=%s\n' "$probe_login"
  probe_gh_ok=1
elif (( probe_has_token_override == 1 || probe_has_config_override == 1 )); then
  printf 'gh_api_default=failed_with_environment_override\n'
  if probe_login="$(env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN -u GH_CONFIG_DIR gh api user --jq .login)"; then
    printf 'gh_api_identity_without_environment_override=%s\n' "$probe_login"
    printf 'gh_environment_override_conflict=confirmed\n'
    probe_gh_ok=1
  else
    printf 'gh_api_without_environment_override=failed\n'
  fi
fi

if probe_remote_line="$(git ls-remote origin refs/heads/main)"; then
  read -r probe_main_sha probe_main_ref <<<"$probe_remote_line"
  printf 'git_remote_main_sha=%s\n' "$probe_main_sha"
  probe_git_ok=1
else
  printf 'git_remote_main_sha=unavailable\n'
fi

if (( probe_git_ok == 1 && probe_gh_ok == 1 )); then
  exit 0
fi
if (( probe_git_ok == 0 && probe_gh_ok == 1 )); then
  exit 10
fi
if (( probe_git_ok == 1 && probe_gh_ok == 0 )); then
  exit 20
fi
exit 30
