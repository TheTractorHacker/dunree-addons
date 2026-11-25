#!/usr/bin/env bash
# Signs the index scripts/build.sh wrote, verifies the signature with the public
# key of this repository, and renders the catalogue page as signed.
#
#   ADDON_INDEX_KEY_FILE   path of the private add-on index key (PKCS#8 PEM).
#                          Default: ~/.dunree-addon-index/addon-index.pem
#   SITE_DIR, WORK_DIR     as for scripts/build.sh
#
# The key is only ever named by its path. It is read by the Dunree signer
# (tools/plugin-index/sign_plugin_index.go, built by scripts/build.sh), which
# never prints it. It must match keys/addon-index.pub or nothing is written.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${SITE_DIR:-$ROOT/site}"
WORK_DIR="${WORK_DIR:-$ROOT/.work}"
KEY="${ADDON_INDEX_KEY_FILE:-$HOME/.dunree-addon-index/addon-index.pem}"
PUB="$ROOT/keys/addon-index.pub"
SIGNER="$WORK_DIR/bin/sign_plugin_index"

fail() { echo "error: $*" >&2; exit 1; }

[ -x "$SIGNER" ] && [ -f "$SITE_DIR/index.json" ] || fail "run scripts/build.sh first"
[ -f "$KEY" ] || fail "the private key $KEY does not exist (set ADDON_INDEX_KEY_FILE)"
key_real="$(cd "$(dirname "$KEY")" && pwd -P)/$(basename "$KEY")"
case "$key_real" in
    "$(cd "$ROOT" && pwd -P)"/*) fail "the private key is inside the repository folder. Move it out before anything else" ;;
esac
rm -f "$SITE_DIR/index.json.sig"

out="$("$SIGNER" -sign-raw -index "$SITE_DIR/index.json" -key "$KEY" -pub "$PUB" 2>&1)" || { echo "$out" >&2; rm -f "$SITE_DIR/index.json.sig"; fail "signing failed; the site is still an unsigned draft"; }
echo "$out"
fingerprint="$(printf '%s\n' "$out" | sed -n 's/^public key fingerprint: \([0-9a-f]\{16\}\)$/\1/p')"

# Verified again from the files, with the public key only
"$SIGNER" -verify -index "$SITE_DIR/index.json" -pub "$PUB" || { rm -f "$SITE_DIR/index.json.sig"; fail "the signature does not verify with keys/addon-index.pub"; }
cmp -s "$PUB" "$SITE_DIR/index.pub" || fail "site/index.pub is not keys/addon-index.pub"

python3 "$ROOT/scripts/storetool.py" mark-signed --site "$SITE_DIR" --work "$WORK_DIR" --fingerprint "$fingerprint"
echo "signed $SITE_DIR/index.json"
