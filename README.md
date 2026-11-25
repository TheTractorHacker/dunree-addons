<p><img src="brand/dunree-mark.svg" alt="Dunree" width="56" height="56"></p>

# Dunree add-on store

This repository is the public add-on store of [Dunree](https://github.com/TheTractorHacker/dunree), the reverse
proxy and web gateway published by Foley IT.

An add-on is a program that Dunree starts next to itself. The store is the list of add-ons a Dunree administrator
can install from **System > Add-ons**. It is made of static files only:

| Part | Where it is | What it holds |
|---|---|---|
| The catalogue | this repository, `addons/<id>/addon.json` | one manifest per add-on: who publishes it, which version, which Dunree API it asks for, and the address, SHA-256 and size of every program file |
| The index | GitHub Pages of this repository | `index.json` built from the manifests, `index.json.sig` (its signature), `index.pub`, and a catalogue page |
| The program files | the GitHub Releases of each add-on's own repository | the binaries. The store never hosts or rebuilds them; it pins them by checksum |

There is no server, no account system and no tracking. Dunree fetches `index.json` and its signature, and then the
one program file an administrator chose to install.

## Use the store in Dunree

| | |
|---|---|
| Index address | `https://thetractorhacker.github.io/dunree-addons/index.json` |
| Catalogue page | <https://thetractorhacker.github.io/dunree-addons/> |
| Public key | [`keys/addon-index.pub`](keys/addon-index.pub), fingerprint `36557d137d47e9ee` |

```
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAEaDXYOjHyrKrLdbJYA0frdmww/Wd2xIfrRCpnHn+PMw=
-----END PUBLIC KEY-----
```

1. Open **System > Add-ons > Sources**. Choose **Dunree add-on store** (one click, in Dunree releases that have
   the store built in), or **Custom index URL** and enter the index address above.
2. Open **Plugin Manager > Plugin safety settings** and paste the public key (or start Dunree with
   `-plugin_index_pubkey`). The one-click choice sets the key for you when none is configured.
3. Set **Signature checking** to **enforce**. The source must show **Signed**.

Dunree ships without any store. Until you add a source it contacts nothing. More in
[docs/using-with-dunree.md](docs/using-with-dunree.md).

## What you can rely on, and what you cannot

**The trust model in four points:**

* **The index is signed.** `index.json.sig` is an ed25519 signature over the exact bytes of `index.json`, made
  with a key that is used for nothing else. It is not the key Dunree releases are signed with. Each index has a
  serial number that only goes up, so an old index cannot be served again without Dunree noticing.
* **Every program file is pinned by hash.** The index names the SHA-256 and the size of each file. The build of
  this store downloads every file and compares both before an index is written; Dunree compares them again before
  it installs.
* **Permissions are shown.** The Dunree API endpoints an add-on asks for are in its manifest, with a reason for
  each. They are shown on the catalogue page, in the pull request that adds or changes the add-on, and in Dunree
  before the install.
* **Enforce mode makes it binding.** Dunree has three settings for signature checking:

  | Mode | What Dunree does |
  |---|---|
  | `off` | compares nothing |
  | `warn` (default) | logs and shows every problem, and installs anyway |
  | `enforce` | installs and updates only from an index with a valid signature of the configured key that is not older than the last one it saw, and refuses a program file whose hash or size differs |

  Only `enforce` protects you from a tampered index or a swapped program file. Use it.

**What the store does not give you:** an add-on is a program that runs on your proxy with the rights of the
Dunree process. A maintainer reads every manifest and looks at the source before an add-on is listed (the review
rules are below), but nobody audits every line of every version, the store does not build the binaries from
source, and it does not sandbox anything. The signature says "this is the catalogue Foley IT published". It does
not say "this program is safe". Install only what you trust, and read the permissions.

## Submit an add-on

By pull request, one add-on per pull request. The short version:

1. Publish a release of your add-on in your own GitHub repository, with one static binary per platform.
2. Copy [`addons/_example`](addons/_example) to `addons/<your id>/` and fill in `addon.json`, with the release
   address, `sha256` and `size` of every binary.
3. Run `python3 scripts/storetool.py validate` and open the pull request.

The full walk-through is [docs/publishing-an-addon.md](docs/publishing-an-addon.md); the rules for contributors
are in [CONTRIBUTING.md](CONTRIBUTING.md).

### What the checks do on every pull request

* the manifest has the right fields and nothing else (a misspelled field is an error);
* every artifact address is `https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`, with a tag that
  names the version. `/latest/` and any other moving address is refused;
* every artifact is downloaded and its SHA-256 and size compared with the manifest, and its header is checked to
  be a program for the platform it is listed under;
* the name, publisher and id do not pass for Dunree, Foley IT or an add-on that is already in the store;
* a version that is already published still points at the same files, and the files of an add-on keep coming
  from the repository they came from (a move needs a maintainer's entry in `policy.json`);
* the same or a look-alike publisher name is not used from another GitHub account;
* the checks that decide run with the scripts, `policy.json` and key of `main`, not with those of the pull
  request, so a pull request cannot weaken the checks that judge it;
* an **unsigned** draft of the index is built and kept as an artifact of the run, and a comment on the pull
  request lists what it changes in the catalogue.

### Review rules

A maintainer merges an add-on only when all of this holds:

1. **The source is public** and is the source of the released binaries. The licence in the manifest is the
   licence of that source.
2. **The submitter may publish it.** They are the author or act for the publisher. A new version comes from the
   same people and the same repository as the one before; a change of repository or publisher is questioned.
3. **Every permission is needed** and its reason is true. An add-on that asks for more than it uses is sent back.
4. **It does what it says.** No hidden network connections, no telemetry that the description does not mention,
   no download of further code at run time, no obfuscated source.
5. **The name is honest.** It describes the add-on. It does not use "Dunree" or "Foley IT" and cannot be mistaken
   for another add-on.
6. **The checks are green**, and the catalogue diff in the pull request shows what the reviewer expects and
   nothing else.

`featured` is set by maintainers only.

## Layout

```
addons/<id>/addon.json     one add-on (plus optional icon and screenshots)
addons/_example/           template, never published: a folder that starts with _ is skipped
keys/addon-index.pub       the public key of the store
policy.json                reserved names and the ids that may use them
scripts/build.sh           builds ./site (unsigned) with the Dunree tools at a pinned ref
scripts/sign.sh            signs ./site and verifies it
scripts/sign-and-publish.sh  build, sign and verify on the maintainer's machine, push to gh-pages
scripts/storetool.py       the store's own checks
.github/workflows/         validate (pull requests), comment (the catalogue diff), publish (main)
docs/                      architecture, keys, publishing, private stores, the Dunree side
```

Build it yourself (needs Go, Python 3 and git; `DUNREE_SRC=<checkout>` uses a local copy of Dunree instead of
cloning):

```sh
scripts/build.sh                 # writes ./site, unsigned
```

## Documentation

* [docs/architecture.md](docs/architecture.md): the three parts and how a release reaches a proxy
* [docs/publishing-an-addon.md](docs/publishing-an-addon.md): for add-on authors
* [docs/using-with-dunree.md](docs/using-with-dunree.md): the Dunree side
* [docs/key-handling.md](docs/key-handling.md): the signing key, for maintainers
* [docs/private-store.md](docs/private-store.md): run your own store
* [SECURITY.md](SECURITY.md): report a malicious add-on; takedown; what happens if the key leaks

## Licence

The store tooling and the catalogue (the manifests) are licensed under AGPL-3.0, like Dunree: see
[LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). **Each add-on carries its own licence**, declared in the `licence`
field of its manifest; listing an add-on here does not change it. "Dunree" and the Dunree logo identify the
releases and the store published by Foley IT.
