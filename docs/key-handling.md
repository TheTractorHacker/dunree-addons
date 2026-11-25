# The signing key

For maintainers. The index is signed with the **add-on index key**, an ed25519 key pair that is used for nothing
else. It is not the key Dunree releases are signed with, and the Dunree signer refuses the release key as an
index key.

* `addon-index.pem`: the **private** key. Whoever holds it decides what a Dunree in enforce mode accepts from
  this store. It is never in this repository, in an artifact, or in a log.
* `addon-index.pub`: the public key. It is `keys/addon-index.pub` here, `index.pub` on the published site, and
  what administrators give to Dunree. Its fingerprint is the first 8 bytes of the SHA-256 of the raw key, in hex;
  the signer prints it.

## Generate

On a machine you trust, from a checkout of Dunree:

```sh
mkdir -m 700 ~/.dunree-addon-index
go run tools/plugin-index/sign_plugin_index.go -genkey ~/.dunree-addon-index/addon-index.pem ~/.dunree-addon-index/addon-index.pub
chmod 600 ~/.dunree-addon-index/addon-index.pem
```

The tool refuses to overwrite an existing file. Copy `addon-index.pub` to `keys/addon-index.pub` by pull request.

## Back up, offline

* Two copies of the private key on media that are not connected to a network (two USB sticks, or one stick and a
  printout of the PEM text), kept in two places.
* Encrypt a copy that leaves your hands (`age -p`, `gpg -c`), and keep the passphrase somewhere else.
* Not in a cloud drive, a password manager that syncs to people who should not sign, a chat, an email, or a
  backup of your home folder that goes to a third party.
* Try a restore once: sign a test build with the restored key and verify it with `keys/addon-index.pub`.

Without a backup, a dead disk means a key rotation for every Dunree that uses the store.

## Two ways to sign

### A. In GitHub Actions (convenient)

The secret `ADDON_INDEX_KEY` holds the PEM file, base64 encoded. `publish.yml` writes it to a temporary file
for the one signing step and deletes it. Keep it as a secret of the environment `addon-signing` (the build job of
`publish.yml` runs in it), and set that environment's **Deployment branches** to `main` only. A repository secret
is readable by a workflow on any branch that someone with write access pushes; an environment secret limited to
`main` is not.

```sh
gh api --method PUT repos/TheTractorHacker/dunree-addons/environments/addon-signing \
  -F 'deployment_branch_policy[protected_branches]=false' -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api --method POST repos/TheTractorHacker/dunree-addons/environments/addon-signing/deployment-branch-policies -f name=main
base64 -w0 ~/.dunree-addon-index/addon-index.pem | gh secret set ADDON_INDEX_KEY --env addon-signing --repo TheTractorHacker/dunree-addons
```

(The command pipes the key into `gh`; it is not printed and not left in the shell history.)

Then **Settings > Pages > Source: GitHub Actions**. Every push to `main` publishes a signed index. Without the
secret the workflow fails with "SIGNING IS REQUIRED" and publishes nothing, so the store that is online keeps its last signed index.

What this trusts: GitHub, every account that can change workflows or secrets of this repository, and every
action the publish workflow uses (they are pinned by commit). Anyone who can push a workflow change to `main`
can make it sign something else. Protect `main` (pull request required, review by a code owner, no bypass) and
keep the list of people with write access short. Secrets are not given to pull requests from forks, and
`validate.yml` does not use any.

### B. On your own machine (higher assurance)

The key never leaves your machine. GitHub only ever sees the signed result.

Set up once:

* repository variable `PUBLISH_MODE` = `offline` (then `publish.yml` builds a draft and publishes nothing);
* no secret `ADDON_INDEX_KEY`;
* **Settings > Pages > Source: Deploy from a branch**, branch `gh-pages`, folder `/`.

To publish, after a pull request is merged:

```sh
git switch main && git pull --ff-only
scripts/sign-and-publish.sh            # build, sign, verify, show what changes
scripts/sign-and-publish.sh --push     # the same, and push to gh-pages
```

The script refuses a tree that is not exactly `origin/main`, builds the site (downloading and checking every
artifact), signs it with `ADDON_INDEX_KEY_FILE` (default `~/.dunree-addon-index/addon-index.pem`), verifies the
signature with `keys/addon-index.pub`, prints the catalogue diff against what is published, and with `--push`
commits the site to `gh-pages` and pushes it. Read the diff before you push: it is the last human look.

What this trusts: your machine. A takeover of the GitHub account can still replace the files on `gh-pages`, but
cannot sign them: a Dunree in enforce mode refuses the result.

Do not mix the two: with the secret set and Pages on "GitHub Actions", a push to `main` replaces what you
published by hand.

## The serial

Every index has a serial, and it must go up with every publish: Dunree remembers the highest serial it has seen
with a valid signature and reports a lower one as **replayed**.

* The serial is the UTC time of the build, `YYYYMMDDhhmmss` (`SERIAL` overrides it).
* `scripts/build.sh` fetches the published `index.json` (`PREVIOUS_INDEX`, default `$STORE_URL/index.json`) and
  refuses to build when the new serial is not higher. A `404` means nothing is published yet. Any other failure
  to fetch stops the build: a serial that cannot be compared is not published.
* Never publish with `PREVIOUS_INDEX=none`. It is for pull request experiments and tests.

## Rotate

Plan a rotation when a person with access to the key leaves, when the machine that held it is retired, or after
some years. The format has no signed "next key": the new key reaches a Dunree through its administrator or
through a Dunree release.

1. Generate a new pair (above). Back it up.
2. Replace `keys/addon-index.pub` by pull request. Update the key and the fingerprint in `README.md`.
3. Announce the new key and its fingerprint in the release notes of Dunree and in an advisory here, **before**
   the switch, so that administrators can see the announcement from a source they already trust.
4. Publish with the new key (replace the secret, or sign offline). The serial keeps going up.
5. Ship a Dunree release with the new `DunreeAddonStorePublicKey`.
6. Destroy the old private key and its backups.

From step 4 on, a Dunree in enforce mode that still has the old key shows the store as `bad_signature` and keeps
the add-ons of the last index it accepted, until its administrator replaces the key. One Dunree holds one index
key for all its sources, so there is no time in which both keys are accepted.

## If it leaked

Treat "might have leaked" as "leaked": a key in a commit (even a deleted one), in a log, on a machine that was
compromised, on a lost device without disk encryption.

Do the rotation above at once, with these differences: delete the secret first, tell users immediately rather
than in advance, and say in the advisory since when the old key cannot be trusted. Review what was published
since then (`gh-pages` history, or the deployments of `publish.yml`) against `main`. The full plan is in
[SECURITY.md](../SECURITY.md#if-the-signing-key-leaks-or-is-lost).

A key that was pushed to GitHub is burned even if the push is reverted within a minute.

`scripts/check-workflows.py` fails the pull request check when a file of the repository holds a private key, and
`.gitignore` ignores `*.pem` and `*.key`. Both are a net, not a reason to keep the key near the checkout:
`scripts/sign.sh` refuses a key that is inside the repository folder.
