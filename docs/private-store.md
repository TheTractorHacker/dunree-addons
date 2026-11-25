# Run a private store

Anyone can run a store the way Foley IT runs this one. Nothing in the format or in Dunree is specific to the
official store except the address and the key. Reasons to run your own: add-ons that are not public, an approved
list for your organisation, proxies without internet access.

## The simplest private store: a folder

You do not need this repository for that. The Dunree repository has the generator, and it can host the program
files itself:

```sh
# in a checkout of Dunree
go run tools/plugin-index/sign_plugin_index.go -genkey /secure/my-store.pem my-store.pub     # once
go run tools/addon-store/main.go -in addons -out site -key /secure/my-store.pem -pub my-store.pub \
    -store-name "Example Org add-ons" -publisher "Example Org"
```

`addons/<name>/addon.json` with the binaries in `addons/<name>/artifacts/` is described in
`docs/plugins/publishing-addons.md` of Dunree. The result, `site/`, holds the index, its signature, a catalogue
page and the program files, with addresses relative to `index.json`. Then either:

* serve `site/` from any static web server over https and add it in Dunree as **Custom index URL**, or
* copy `site/` to the server and add it as **Local folder** (no network at all; in Docker, mount the folder).

Keep `site/` between runs: the generator takes the next serial from the index that is already there.

## A private store with review: copy this repository

Use this repository as a template when you want what it adds: manifests reviewed by pull request, program files
that stay in the releases of each add-on, checks in CI, and a published serial that is verified.

1. Create your repository from a copy of this one. Remove `addons/*` except `_example`.
2. **Make your own key** ([key-handling.md](key-handling.md)) and replace `keys/addon-index.pub`. Never reuse a
   key of another store.
3. **Give it your own name.** Set `STORE_NAME` and `STORE_PUBLISHER` for `scripts/build.sh`, replace the files in
   `brand/` and the mark in `scripts/storetool.py`, and change the names in `policy.json` to the ones you want
   to protect. A private store must not look like the Dunree add-on store of Foley IT.
4. Set the repository variables: `STORE_URL` (where your site is served), `DUNREE_REF` (a tag or commit of
   Dunree; pin a commit for builds that repeat exactly), and `DUNREE_REPO` if you build from a fork.
5. Choose how to sign: the secret `ADDON_INDEX_KEY`, or `PUBLISH_MODE=offline` with
   `scripts/sign-and-publish.sh`.
6. Update `CODEOWNERS`, `SECURITY.md` and the addresses in `README.md`.

Things that are fixed in the scripts and that you may want to change:

* Artifact addresses must be GitHub release assets (`RELEASE_URL_RE` in `scripts/storetool.py`). For another
  host, change the pattern and keep the two properties that matter: `https`, and an address that names one
  version and never moves.
* GitHub Pages of a private repository is public unless your plan has access control for Pages. For a store
  that must not be public, publish `site/` to an internal web server instead (`scripts/build.sh` and
  `scripts/sign.sh` write a plain folder). The build downloads artifacts without credentials, so release assets
  of a private repository do not work with these scripts; use the folder variant above for those.
* The site is a plain folder. `scripts/build.sh && scripts/sign.sh`, then `rsync -a site/ host:/var/www/addons/`
  is a complete publish. Copy `index.json` and `index.json.sig` last and together.

## Offline use

Without internet access for the build, point `DUNREE_SRC` at a checkout of Dunree instead of cloning it, and
`PREVIOUS_INDEX` at the `index.json` you published last (a file):

```sh
DUNREE_SRC=~/src/dunree PREVIOUS_INDEX=/var/www/addons/index.json scripts/build.sh
```

The artifacts are still downloaded from the addresses in the manifests. For a store with no network at all, use
the folder variant above.

## On the Dunree side

Add the address as **Custom index URL** (or the folder as **Local folder**), give Dunree **your** public key
under **Plugin Manager > Plugin safety settings**, and set signature checking to **enforce**.

Dunree holds **one** index key for all sources. With your key configured, the official store shows as
`bad_signature` and is refused in enforce mode. If you want add-ons from the official store as well, list them in
your own store after your own review: the manifest can be copied as it is, since it points at the publisher's
release and pins it by hash, and your index is then signed with your key.
