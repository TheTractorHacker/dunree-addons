# Publish an add-on in the store

For add-on authors. You publish a release in your own repository, and a manifest here that points at it.

How to write an add-on is in the Dunree repository (`docs/plugins/`). This page starts when it works.

## 1. Build one static binary per platform

Dunree installs the file whose platform is exactly its own `GOOS_GOARCH`; there is no fallback to another
architecture. Build static binaries (no libc dependency), and name them `<name>_<os>_<arch>`, with `.exe` for
Windows:

```sh
for target in linux/amd64 linux/arm64 windows/amd64 darwin/arm64; do
  os=${target%/*}; arch=${target#*/}; ext=""; [ "$os" = windows ] && ext=".exe"
  CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build -trimpath -o "dist/geo-block_${os}_${arch}${ext}" .
done
```

File names may have letters, digits, dot, dash and underscore.

## 2. Publish a release in your repository

Create a release under a tag that contains the version (`v1.2.0`, or `geo-block-v1.2.0` in a repository with
several add-ons) and attach the binaries:

```sh
gh release create v1.2.0 dist/* --title "1.2.0" --notes "IPv6 ranges"
```

The address of each file is then
`https://github.com/<owner>/<repo>/releases/download/v1.2.0/geo-block_linux_amd64`. That is the form the store
accepts. `.../releases/latest/download/...` is refused: it points at something else after your next release.

**Do not replace or delete the assets of a release that is listed in the store.** The store pins each file by
its SHA-256. A replaced file makes every install fail on a Dunree in enforce mode, and makes the next build of
the store fail. To change anything, publish a new version.

## 3. Checksums and sizes

```sh
cd dist && sha256sum * && stat -c '%s %n' *        # macOS: shasum -a 256 *; stat -f '%z %N' *
```

Take them from the files you uploaded.

## 4. The manifest

```sh
cp -r addons/_example addons/org.example.geo-block
rm addons/org.example.geo-block/README.md
```

`addons/org.example.geo-block/addon.json`:

```json
{
  "id": "org.example.geo-block",
  "name": "Geo block",
  "publisher": "Example Org",
  "description": "Blocks or allows visitors by country.",
  "homepage": "https://github.com/example-org/geo-block",
  "licence": "MIT",
  "version": "1.2.0",
  "api_version": 1,
  "min_host_version": "1.0.0",
  "type": "router",
  "categories": ["Security"],
  "permissions": [
    { "method": "GET", "endpoint": "/plugin/api/access/list", "reason": "Reads the access rules to apply them" }
  ],
  "changelog": [
    { "version": "1.2.0", "date": "2026-11-20", "notes": "IPv6 ranges" },
    { "version": "1.1.0", "date": "2026-10-02", "notes": "First public release" }
  ],
  "icon": "icon.png",
  "screenshots": ["screenshots/rules.png"],
  "artifacts": {
    "linux_amd64": {
      "url": "https://github.com/example-org/geo-block/releases/download/v1.2.0/geo-block_linux_amd64",
      "sha256": "…64 hex digits, lower case…",
      "size": 9412608
    },
    "windows_amd64": {
      "url": "https://github.com/example-org/geo-block/releases/download/v1.2.0/geo-block_windows_amd64.exe",
      "sha256": "…",
      "size": 9632256
    }
  }
}
```

| Field | Required | Rule |
|---|---|---|
| `id` | yes | lower-case letters, digits, `.`, `-`, `_`; your domain in reverse plus a name. **The folder has the same name.** It must be the id the program prints with `-introspect` |
| `name` | yes | at most 100 characters. Also the name of the folder Dunree installs into. Not "Dunree ...", and not the name of another add-on |
| `publisher` | yes | you or your organisation |
| `description` | yes | what it does, at most 4000 characters. Mention every network connection it makes on its own |
| `homepage` | yes | `https`, where the source is |
| `licence` | yes | SPDX identifier of the licence of the add-on (`license` is accepted as a spelling) |
| `version` | yes | `major.minor.patch`, what the program prints with `-introspect`. The release tag contains it |
| `artifacts` | yes | per platform (`linux_amd64`, `linux_arm64`, `windows_amd64`, `darwin_arm64`, ...): `url`, `sha256`, `size`. All from one repository |
| `api_version` | no | the plugin contract the add-on was built for |
| `min_host_version` | no | the oldest Dunree that can run it. An older Dunree lists the add-on and refuses to install it |
| `type` | no | `router` (handles requests of the sites it is assigned to) or `utility` (default) |
| `categories` | no | at most 5; the first one is where the Add-ons page files it |
| `permissions` | no | every Dunree API endpoint the add-on calls: `method`, `endpoint`, and a `reason`. What is missing here is not granted silently by Dunree |
| `changelog` | no | newest first; the first entry is for `version` |
| `icon`, `screenshots` | no | files in your add-on folder: png, jpg, webp or gif, at most 4 MB each, at most 8 screenshots. No svg |
| `featured` | no | set by maintainers |

A field that is not in this table is an error, so that a typo cannot silently drop something.

## 5. Check and open the pull request

```sh
python3 scripts/storetool.py validate          # fields, addresses, names; no network
PREVIOUS_INDEX=none scripts/build.sh           # everything the pull request check does; needs Go and git
```

Open a pull request with only your add-on folder in it and fill in the template. The check downloads your files,
compares the checksums, builds an unsigned draft of the index, and a comment shows what your pull request changes
in the catalogue. A maintainer reviews it against the [review rules](../README.md#review-rules).

After the merge the index is built, signed and published. Dunree installations see the add-on the next time
they fetch the index.

## A new version

1. Release it in your repository under a new tag.
2. In the manifest: `version`, every `url`, `sha256` and `size`, and a new first entry in `changelog`. New
   permissions need a reason and will be looked at closely.
3. Pull request.

The index lists one version per add-on, the current one. Installations update from the source they installed
from, and Dunree keeps the previous program file for a rollback.

## Withdraw

A pull request that deletes your folder. The add-on leaves the index with the next publish. Copies that are
installed keep running and get no more updates.

## Common failures of the check

| Message | Cause |
|---|---|
| `has sha256 ..., the manifest says ...` | the checksum is of another file, or the asset was replaced |
| `the release tag ... does not name the version ...` | `version` is `1.2.0` but the address is under `v1.1.0` |
| `/latest/ moves; name the release tag` | use `/releases/download/<tag>/` |
| `not an ELF program file` / `for another CPU` | the file is listed under the wrong platform |
| `uses a name reserved for Dunree and Foley IT` | take "Dunree" out of `name` and `publisher` |
| `is published already and its artifacts changed` | raise `version` |
