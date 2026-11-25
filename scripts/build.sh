#!/usr/bin/env bash
# Builds the static site of the store into ./site: index.json (NOT signed),
# the catalogue page, the public key and the pictures.
#
# The index and the page are written by tools/addon-store of the Dunree
# repository. Nothing in here needs or reads the private key; signing is
# scripts/sign.sh.
#
#   DUNREE_REF      branch, tag or commit of Dunree whose tools are used (default: prod)
#   DUNREE_REPO     where Dunree is cloned from (default: https://github.com/TheTractorHacker/dunree.git)
#   DUNREE_SRC      a local checkout of Dunree, used as it is instead of cloning (offline use).
#                   Only tools/addon-store/main.go and tools/plugin-index/sign_plugin_index.go
#                   are read; nothing is written into it
#   STORE_URL       address the site is served at (default: https://thetractorhacker.github.io/dunree-addons)
#   SERIAL          serial number of the index (default: the UTC time, YYYYMMDDhhmmss)
#   PREVIOUS_INDEX  address or file of the published index.json the serial is compared
#                   with (default: $STORE_URL/index.json), or "none"
#   ADDONS_DIR      folder with the add-ons (default: ./addons)
#   SITE_DIR        output (default: ./site)       WORK_DIR  scratch (default: ./.work)
#   STORE_NAME, STORE_PUBLISHER                     shown on the page
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUNREE_REF="${DUNREE_REF:-prod}"
DUNREE_REPO="${DUNREE_REPO:-https://github.com/TheTractorHacker/dunree.git}"
STORE_URL="${STORE_URL:-https://thetractorhacker.github.io/dunree-addons}"
STORE_URL="${STORE_URL%/}"
STORE_NAME="${STORE_NAME:-Dunree add-on store}"
STORE_PUBLISHER="${STORE_PUBLISHER:-Foley IT}"
ADDONS_DIR="${ADDONS_DIR:-$ROOT/addons}"
SITE_DIR="${SITE_DIR:-$ROOT/site}"
WORK_DIR="${WORK_DIR:-$ROOT/.work}"
SERIAL="${SERIAL:-$(date -u +%Y%m%d%H%M%S)}"
PREVIOUS_INDEX="${PREVIOUS_INDEX:-$STORE_URL/index.json}"
PUB="$ROOT/keys/addon-index.pub"
TOOL="python3 $ROOT/scripts/storetool.py"
export ADDONS_DIR

fail() { echo "error: $*" >&2; exit 1; }

command -v go >/dev/null || fail "go is needed to build the Dunree store tools"
command -v python3 >/dev/null || fail "python3 is needed"
[[ "$SERIAL" =~ ^[1-9][0-9]{0,15}$ ]] || fail "SERIAL must be a positive whole number, got '$SERIAL'"
[ -f "$PUB" ] || fail "keys/addon-index.pub is missing"

# The output folder is replaced. Refuse to replace something that is not a site.
if [ -e "$SITE_DIR" ]; then
    if [ -n "$(ls -A "$SITE_DIR" 2>/dev/null)" ] && [ ! -f "$SITE_DIR/index.json" ] && [ ! -f "$SITE_DIR/index.html" ]; then
        fail "$SITE_DIR exists and is not a site that this script built; remove it yourself"
    fi
    rm -rf "$SITE_DIR"
fi
mkdir -p "$WORK_DIR"
rm -rf "$WORK_DIR/in" "$WORK_DIR/bin" "$WORK_DIR/src" "$WORK_DIR/dunree" "$WORK_DIR/tool-index.html" "$WORK_DIR/build-info.json"

echo "== 1. Manifests"
$TOOL validate

echo "== 2. Serial"
$TOOL check-previous --serial "$SERIAL" --source "$PREVIOUS_INDEX" --save "$WORK_DIR/previous-index.json"

echo "== 3. Dunree store tools"
if [ -n "${DUNREE_SRC:-}" ]; then
    SRC="$DUNREE_SRC"
    DUNREE_COMMIT="$(git -C "$SRC" rev-parse -q --verify HEAD 2>/dev/null || echo unknown)"
    DUNREE_REF="local"
    echo "using the local checkout $SRC ($DUNREE_COMMIT)"
else
    SRC="$WORK_DIR/dunree"
    git init -q "$SRC"
    git -C "$SRC" fetch -q --depth 1 "$DUNREE_REPO" "$DUNREE_REF" || fail "could not fetch $DUNREE_REF from $DUNREE_REPO"
    git -C "$SRC" -c advice.detachedHead=false checkout -q FETCH_HEAD
    DUNREE_COMMIT="$(git -C "$SRC" rev-parse HEAD)"
    echo "using $DUNREE_REPO at $DUNREE_REF ($DUNREE_COMMIT)"
fi
for f in tools/addon-store/main.go tools/plugin-index/sign_plugin_index.go; do
    [ -f "$SRC/$f" ] || fail "$SRC/$f not found: is this a Dunree checkout?"
done
# Built from a copy, so that nothing is ever written into the checkout
mkdir -p "$WORK_DIR/src/addon-store" "$WORK_DIR/src/plugin-index" "$WORK_DIR/bin"
cp "$SRC/tools/addon-store/main.go" "$WORK_DIR/src/addon-store/main.go"
cp "$SRC/tools/plugin-index/sign_plugin_index.go" "$WORK_DIR/src/plugin-index/main.go"
(cd "$WORK_DIR/src/addon-store" && GOFLAGS= GO111MODULE=off CGO_ENABLED=0 go build -trimpath -o "$WORK_DIR/bin/addon-store" main.go)
(cd "$WORK_DIR/src/plugin-index" && GOFLAGS= GO111MODULE=off CGO_ENABLED=0 go build -trimpath -o "$WORK_DIR/bin/sign_plugin_index" main.go)

echo "== 4. Artifacts: download, sha256 and size"
$TOOL stage --out "$WORK_DIR/in"

echo "== 5. Index and catalogue (tools/addon-store, without a key)"
"$WORK_DIR/bin/addon-store" -in "$WORK_DIR/in" -out "$SITE_DIR" -unsigned -serial "$SERIAL" \
    -store-name "$STORE_NAME" -publisher "$STORE_PUBLISHER" -store-url "$STORE_URL/"

echo "== 6. Release addresses, published versions, page"
STORE_COMMIT="$(git -C "$ROOT" rev-parse -q --verify HEAD 2>/dev/null || echo unknown)"
$TOOL finish --site "$SITE_DIR" --work "$WORK_DIR" --pub "$PUB" --store-url "$STORE_URL" \
    --dunree-ref "$DUNREE_REF" --dunree-commit "$DUNREE_COMMIT" --store-commit "$STORE_COMMIT"

rm -rf "$WORK_DIR/in" "$WORK_DIR/src" "$WORK_DIR/dunree"
echo "built $SITE_DIR (serial $SERIAL). It is a draft until scripts/sign.sh has signed it."
