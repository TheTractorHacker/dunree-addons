# Contributing

There are two kinds of contribution: an add-on (a manifest in `addons/`) and a change to the store itself
(scripts, workflows, documentation). Both come as pull requests against `main`, and both need the review of a
maintainer ([CODEOWNERS](CODEOWNERS)).

## An add-on

Read [docs/publishing-an-addon.md](docs/publishing-an-addon.md) for the steps. The rules:

* **One add-on per pull request**, and nothing else in it.
* **You may publish it.** You are its author, or you act for its publisher and say so in the pull request.
* **The folder is the id.** `addons/<id>/addon.json`, with `id` in lower case: your domain in reverse and a name
  (`org.example.geo-block`). The ids below `ie.foleyit.` and with `dunree` in them are reserved.
* **Program files stay in your releases.** The manifest names
  `https://github.com/<owner>/<repo>/releases/download/<tag>/<file>` for each platform, all from one repository,
  under a tag that contains the version. Never `/latest/`. No binary is committed here.
* **`sha256` and `size` are exact.** The checks download every file and compare.
* **A published version never changes.** To fix something, release a new version and raise `version`. Do not
  replace the assets of a release that is listed here: the checksum would stop matching and installs would fail.
* **Every permission has a reason** that a person who does not know your code can judge.
* **The name is yours.** No "Dunree" or "Foley IT" in `name` or `publisher`, and nothing that can be mistaken
  for an add-on that is already listed. Say what it is for in the `description`.
* **The source is public** under the licence you declare in `licence` (an SPDX identifier).

Run the check before you push; it needs only Python 3:

```sh
python3 scripts/storetool.py validate
```

To run everything the pull request check runs (needs Go and git, and downloads your release files):

```sh
PREVIOUS_INDEX=none scripts/build.sh
```

What the reviewer looks at is in the [review rules](README.md#review-rules). Expect questions; a program that
runs on other people's proxies is worth them.

### Updating and withdrawing

* A new version: change `version`, the artifacts and the changelog (newest entry first, for the new version).
* Moving to another repository or GitHub account: say so in the pull request. The check refuses it until a
  maintainer has confirmed the move in a separate pull request that adds
  `"repository_moves": {"<id>": "<owner>/<repo>"}` to `policy.json` (the pull request check uses the policy
  of `main`).
* Withdrawing: a pull request that deletes the folder. The next index no longer lists the add-on. Copies that
  are installed stay installed; see [SECURITY.md](SECURITY.md) for what the store does about a harmful one.

## The store itself

* Scripts use the Python standard library and POSIX tools only. No dependency is installed in a workflow.
* Every action in a workflow is pinned by its full commit SHA with the version in a comment, workflows have
  least-privilege `permissions` and a `concurrency` group, and `pull_request_target` is not used.
  `python3 scripts/check-workflows.py` checks this.
* The private key is never in the repository, in an artifact or in a log. A change that makes a workflow print
  or upload more than `site/` is rejected.
* Changes to `scripts/`, `.github/`, `keys/` and `policy.json` decide what gets signed. They are reviewed like
  code that handles a key, because that is what they are.

## Licence of contributions

Manifests and changes to the store are contributed under AGPL-3.0 ([NOTICE.md](NOTICE.md)). Your add-on keeps
its own licence.
