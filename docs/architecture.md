# Architecture

The store has three parts. None of them is a server of ours.

```
   add-on author                    this repository                        a Dunree proxy
 ------------------              ----------------------                 --------------------
 own GitHub repo                  addons/<id>/addon.json                 System > Add-ons
   releases/v1.2.0/   <--pins--     url + sha256 + size
     geo_linux_amd64                       |
     geo_windows_amd64.exe                 | build (scripts/build.sh)
            ^                              | sign  (the add-on index key)
            |                              v
            |                    GitHub Pages: index.json        --1-->  fetches index.json + .sig,
            |                                  index.json.sig            checks signature and serial
            |                                  index.pub, index.html
            |
            +----------------------------2---------------------------    downloads the one file it
                                                                         installs, checks sha256 + size
```

## 1. The catalogue (this repository, branch `main`)

One folder per add-on, `addons/<id>/addon.json`, plus an optional icon and screenshots. A manifest is the entry
of the add-on in the index ([format](https://github.com/TheTractorHacker/dunree/blob/prod/docs/plugins/addon-store.md)):
who publishes it, the version, the Dunree API endpoints it asks for, and for every platform the address, SHA-256
and size of the program file.

Everything that reaches the index goes through a pull request and the review of a maintainer. The catalogue is
plain text in git: its history is the record of who listed what and when.

## 2. The signed index (GitHub Pages)

`scripts/build.sh` turns the catalogue into a folder of static files:

| File | |
|---|---|
| `index.json` | the Dunree add-on index, format version 1 |
| `index.json.sig` | the raw 64 bytes of an ed25519 signature over the exact bytes of `index.json` |
| `index.pub` | the public key (the same file as `keys/addon-index.pub`) |
| `index.html` | the catalogue page: searchable, one file, loads nothing from another host, light and dark |
| `addons/<id>/icon.*`, `screenshots/` | pictures |
| `build.json` | serial, checksum of the index, and the commits of this repository and of Dunree it was built from |

The build, step by step:

1. **Manifests** are checked (`scripts/storetool.py validate`): fields, addresses, names.
2. **The serial** is chosen (the UTC time, `YYYYMMDDhhmmss`) and compared with the index that is published now.
   It must be higher, or nothing is built.
3. **The Dunree tools** are fetched at `DUNREE_REF` and built: `tools/addon-store` (index and page) and
   `tools/plugin-index/sign_plugin_index.go` (signature).
4. **Every artifact is downloaded** and its SHA-256 and size compared with the manifest.
5. **`tools/addon-store`** checks that each file is a program for its platform and writes the index and the page.
   It runs without a key.
6. **The index is pointed at the release addresses.** The tool expects to host the files it reads; this store
   does not host binaries, so `storetool.py finish` puts the address of each release asset back into the index
   and the page, and removes the copies. It also refuses a published version whose files changed, and adds the
   Dunree mark and the signature state to the page.
7. **Signing** (`scripts/sign.sh`) is a separate step, the only one that touches the private key. The signature
   is verified with the public key of the repository straight away.

A folder in `addons/` whose name starts with `_` or `.` is skipped in step 1, which is how `addons/_example`
stays out of the index.

There are two ways to run steps 1 to 7 and publish, described in [key-handling.md](key-handling.md):

* **In GitHub Actions** (`publish.yml`, on every push to `main`), with the key in a secret of the environment `addon-signing`, deployed
  with `actions/deploy-pages`.
* **On the maintainer's machine** (`scripts/sign-and-publish.sh --push`), with the key offline; only the signed
  result is pushed, to the `gh-pages` branch.

## 3. The program files (the releases of each add-on)

The binaries are release assets in the add-on's own GitHub repository. The store never copies, rebuilds or
serves them. It pins them: the signed index names the SHA-256 and size of each file, so a release asset that is
replaced later no longer installs on a Dunree in enforce mode, and the next build of the store fails until a
maintainer has looked.

## What a Dunree does with it

Dunree fetches `index.json` and `index.json.sig` from the source address, verifies the signature with the public
key the administrator configured, and compares the serial with the highest one it has seen from that source.
When an administrator installs an add-on, Dunree downloads the artifact for exactly its own platform, compares
SHA-256 and size, runs the file once with `-introspect`, and only then moves it into place. See
[using-with-dunree.md](using-with-dunree.md).

## Workflows

| Workflow | Runs on | Token | Does |
|---|---|---|---|
| `validate.yml` | pull requests | read-only, no secrets | all checks, run with the tooling of the pull request and again with the scripts, policy and key of `main` (those decide); the unsigned draft index as an artifact, the catalogue diff |
| `comment.yml` | after `validate.yml`, from `main` | may comment on pull requests | posts the diff as a comment. Runs no code of the pull request; the diff is treated as text |
| `publish.yml` | push to `main` | read; Pages rights in the deploy job only | build, sign if `ADDON_INDEX_KEY` is set (environment `addon-signing`), deploy. Unsigned: deploys the draft and fails |

Repository variables (all optional): `DUNREE_REPO`, `DUNREE_REF` (default `prod`; a commit SHA pins the tools
exactly), `STORE_URL`, `PUBLISH_MODE` (`ci` or `offline`).
