#!/usr/bin/env bash
# The higher-assurance way to publish: build, sign and verify on the machine of
# the maintainer, with the offline key, and push only the signed result to the
# gh-pages branch. The private key never reaches GitHub.
#
#   scripts/sign-and-publish.sh            build, sign, verify, show what would be published
#   scripts/sign-and-publish.sh --push     ... and push it to the gh-pages branch
#
#   ADDON_INDEX_KEY_FILE   private key (default: ~/.dunree-addon-index/addon-index.pem)
#   REMOTE                 git remote to publish to (default: origin)
#   PAGES_BRANCH           branch GitHub Pages serves (default: gh-pages)
#   ALLOW_UNREVIEWED=1     build from a tree that is not exactly $REMOTE/main (tests only)
#   plus everything scripts/build.sh reads (DUNREE_REF, DUNREE_SRC, STORE_URL, SERIAL, ...)
#
# For this flow set the repository variable PUBLISH_MODE to "offline" and let
# GitHub Pages serve the gh-pages branch; see docs/key-handling.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${SITE_DIR:-$ROOT/site}"
WORK_DIR="${WORK_DIR:-$ROOT/.work}"
REMOTE="${REMOTE:-origin}"
PAGES_BRANCH="${PAGES_BRANCH:-gh-pages}"
export SITE_DIR WORK_DIR

fail() { echo "error: $*" >&2; exit 1; }

PUSH=0
for arg in "$@"; do
    case "$arg" in
        --push) PUSH=1 ;;
        -h|--help) sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "unknown argument $arg" ;;
    esac
done

# What is signed must be what was reviewed and merged: a clean tree at $REMOTE/main
if [ "${ALLOW_UNREVIEWED:-0}" != 1 ]; then
    git -C "$ROOT" fetch -q "$REMOTE" main || fail "could not fetch $REMOTE main"
    [ -z "$(git -C "$ROOT" status --porcelain)" ] || fail "the working tree has changes. Sign only what is merged"
    [ "$(git -C "$ROOT" rev-parse HEAD)" = "$(git -C "$ROOT" rev-parse FETCH_HEAD)" ] || fail "HEAD is not $REMOTE/main. Sign only what is merged"
fi

"$ROOT/scripts/build.sh"
"$ROOT/scripts/sign.sh"

serial="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["serial"])' "$SITE_DIR/index.json")"
echo
echo "== What this publishes (compared with the published index)"
python3 "$ROOT/scripts/storetool.py" diff --old "$WORK_DIR/previous-index.json" --new "$SITE_DIR/index.json"
echo

if [ "$PUSH" != 1 ]; then
    echo "Signed and verified: $SITE_DIR (serial $serial). Nothing was pushed; run again with --push to publish."
    exit 0
fi

url="$(git -C "$ROOT" remote get-url "$REMOTE")" || fail "no git remote $REMOTE"
commit="$(git -C "$ROOT" rev-parse --short HEAD)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
git init -q -b "$PAGES_BRANCH" "$stage"
# Keep the history of the branch when it exists; the content is replaced
if git -C "$stage" fetch -q --depth 1 "$url" "$PAGES_BRANCH" 2>/dev/null; then
    git -C "$stage" reset -q --soft FETCH_HEAD
fi
cp -R "$SITE_DIR/." "$stage/"
git -C "$stage" add -A
for name in user.name user.email; do
    git -C "$stage" config "$name" "$(git -C "$ROOT" config "$name")" || fail "git $name is not set"
done
git -C "$stage" commit -q -m "Publish add-on index, serial $serial (store $commit)"
# The last look before it is public: the committed files verify with the public key
"$WORK_DIR/bin/sign_plugin_index" -verify -index "$stage/index.json" -pub "$ROOT/keys/addon-index.pub"
git -C "$stage" push -q "$url" "HEAD:refs/heads/$PAGES_BRANCH"
echo "Published serial $serial to $REMOTE $PAGES_BRANCH."
