# Licensing of this repository

Copyright (C) 2026 Foley IT and the contributors of this repository.

## The store tooling and the catalogue: AGPL-3.0

Everything Foley IT and its contributors wrote in this repository is licensed under the GNU Affero General
Public License, version 3 (the text is in [LICENSE](LICENSE)), the licence of Dunree itself. That covers:

* the scripts in `scripts/` and the workflows in `.github/workflows/`;
* the documentation;
* the catalogue: the manifests in `addons/`, as a collection and one by one.

By contributing a manifest you license it under the same terms.

The index and the catalogue page are generated with `tools/addon-store` and `tools/plugin-index` of the Dunree
repository, which are AGPL-3.0 as well.

## The add-ons: each its own licence

An add-on listed here is **not** part of this repository and is not licensed by it. Its program files live in the
releases of its own repository, and it is published under the licence its publisher declares in the `licence`
field of its manifest (an SPDX identifier). Listing an add-on does not relicense it, and it is no statement by
Foley IT about that licence.

Icons and screenshots in an add-on folder belong to the publisher of that add-on, who allows them to be shown
on the catalogue page and in Dunree by submitting them.

## Name and logo

"Dunree" and the Dunree logo (`brand/`) identify the releases and the store published by Foley IT. The licence
above does not allow a store or an add-on to pass as coming from Foley IT. A private store built from this
repository needs its own name; see [docs/private-store.md](docs/private-store.md).
