<!-- One add-on per pull request. Read CONTRIBUTING.md first. -->

## What this changes

- [ ] New add-on
- [ ] New version of an add-on that is already in the store
- [ ] Withdraws an add-on
- [ ] Store tooling or documentation

Add-on id:
Version:
Source repository:

## Checklist for the author

- [ ] The folder `addons/<id>/` is named exactly like the `id` in `addon.json`.
- [ ] Every artifact address is a release asset of my own repository under a tag that names the version
      (`.../releases/download/v1.2.0/...`), never `/latest/`.
- [ ] `sha256` and `size` are those of the released files (`sha256sum`, `stat -c %s`).
- [ ] `id` and `version` are what the program prints with `-introspect`.
- [ ] Every Dunree API endpoint the add-on calls is under `permissions`, each with a reason a person can judge.
- [ ] The source of this version is public, and `licence` is the SPDX identifier of its licence.
- [ ] The name does not use "Dunree" or "Foley IT" and cannot be mistaken for another add-on.
- [ ] I am allowed to publish this add-on (I am its author or act for its publisher).

## Notes for the reviewer

<!-- What changed since the last version; anything unusual about the build or the permissions. -->
