#!/usr/bin/env bash
# Experimental 50.5 -> 51.1 AnLand patch rebase, with deterministic base trees.
# Usage: bash port-mutter-51.sh /path/to/output.patch
# If the merge conflicts, exits nonzero with filenames/markers for further porting.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
old_patch="$here/mutter.patch"
output="${1:?Specify destination for rebased Mutter 51.1 patch}"
[ -s "$old_patch" ] || { echo "Cannot find original Mutter patch: $old_patch" >&2; exit 1; }
command -v git >/dev/null || { echo "git is required" >&2; exit 1; }

work="$(mktemp -d -t anland-mutter51-rebase.XXXXXXXX)"
trap 'rm -rf -- "$work"' EXIT
repo="$work/mutter"
git init -q "$repo"
git -C "$repo" remote add upstream https://github.com/GNOME/mutter.git
git -C "$repo" -c protocol.version=2 fetch --no-tags --filter=blob:none --depth=1 upstream \
  '+refs/tags/50.5:refs/tags/50.5' '+refs/tags/51.1:refs/tags/51.1'

base50="$(git -C "$repo" rev-parse 'refs/tags/50.5^{commit}')"
base51="$(git -C "$repo" rev-parse 'refs/tags/51.1^{commit}')"
# The 51.1 GNOME upstream GitHub tag was verified when creating this experiment.
expected51=9134e3a5869ce232bf95b77519005865747ba603
if [[ "$base51" != "$expected51" ]]; then
  echo "Mutter 51.1 tag moved: expected $expected51, found $base51" >&2
  exit 1
fi

export GIT_AUTHOR_NAME='AnLand compatibility experiment'
export GIT_AUTHOR_EMAIL='anland-port@example.invalid'
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

# Make a branch consisting only of the legacy patch applied to Mutter 50.5.
git -C "$repo" checkout -q --detach "$base50"
if ! git -C "$repo" apply --check "$old_patch"; then
  echo "The legacy patch no longer applies cleanly to Mutter 50.5." >&2
  exit 1
fi
git -C "$repo" apply "$old_patch"
git -C "$repo" add -A
git -C "$repo" commit -q -m 'AnLand legacy patch applied to Mutter 50.5'
patched50="$(git -C "$repo" rev-parse HEAD)"

# The shallow tag fetches do not contain the intervening GNOME history.
# Construct a synthetic *local* 51.1 commit with the 50.5 tag as parent:
# the three-way merge then sees exactly upstream 50.5->51.1 versus the
# AnLand patch, rather than treating the unrelated shallow tips as roots.
tree51="$(git -C "$repo" rev-parse "$base51^{tree}")"
synthetic51="$(printf 'Mutter 51.1 snapshot for AnLand rebase\n' | git -C "$repo" commit-tree "$tree51" -p "$base50")"
git -C "$repo" checkout -q --detach "$synthetic51"

echo "Rebasing AnLand from Mutter 50.5 to Mutter 51.1..."
if ! git -C "$repo" merge --no-ff --no-edit "$patched50"; then
  echo "The first merge found conflicts; resolving the five reviewed Mutter 51.1 API transitions..."
  if python3 "$here/resolve-mutter-51.py" "$repo" && \
     python3 "$here/port-cogl51.py" "$repo"; then
    git -C "$repo" add -- config.h.meson meson.build meson.options \
      src/backends/native/meta-renderer-native.c src/core/meta-context-main.c
    if [ -z "$(git -C "$repo" ls-files -u)" ]; then
      git -C "$repo" commit -q -m 'Port AnLand Meson and native backend integration to Mutter 51.1'
      echo "All five known conflicts resolved. Compiling the port is still required."
    else
      echo "Unknown Git merge conflicts remain."
      exit 2
    fi
  else
    echo "::error::Automatic resolution failed: see conflict report and source changes."
    git -C "$repo" diff --name-only --diff-filter=U || true
  echo "Conflict count: $(git -C "$repo" ls-files -u | cut -f2 | sort -u | wc -l)"
  git -C "$repo" diff --stat || true
  if [[ -n "${PORT_REPORT_DIR:-}" ]]; then
    mkdir -p "$PORT_REPORT_DIR"
    git -C "$repo" diff --name-only --diff-filter=U > "$PORT_REPORT_DIR/conflict-files.txt"
    git -C "$repo" diff > "$PORT_REPORT_DIR/rebase-conflicts.diff" || true
    git -C "$repo" status --short > "$PORT_REPORT_DIR/rebase-status.txt"
  fi
    exit 2
  fi
fi

mkdir -p "$(dirname -- "$output")"
git -C "$repo" diff --binary "$synthetic51" HEAD > "$output"
if [[ ! -s "$output" ]]; then
  echo "Unexpected empty AnLand rebase patch" >&2
  exit 1
fi
# Verify generated patch against a clean Mutter 51.1 source tree.
git -C "$repo" checkout -q --detach "$synthetic51"
git -C "$repo" apply --check "$output"
echo "Generated a conflict-free rebased patch: $output"
echo "Note: conflict-free rebasing does NOT mean the C sources compile or work."
