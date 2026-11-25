# How Dunree uses the store

For administrators of a Dunree proxy.

## By default: nothing

Dunree ships without a store source. Until you add one it fetches nothing and opens no connection.
**System > Add-ons** shows "No add-on store configured" and three ways to add a source:

| Choice | What it is |
|---|---|
| **Dunree add-on store** | this store, one click. Available in Dunree releases that have the address and the key of the store built in; in other builds the choice is shown as "not open yet" |
| **Custom index URL** | any `index.json` on the web. Use this to add this store by hand, or a private one |
| **Local folder** | a folder on the server with `index.json` and the program files. No network |

## Add this store

1. **System > Add-ons > Sources**: choose **Dunree add-on store**, or **Custom index URL** with

   ```
   https://thetractorhacker.github.io/dunree-addons/index.json
   ```

2. **Plugin Manager > Plugin safety settings**: paste the public key of the store (the PEM text, or the 32 bytes
   in base64). It is [`keys/addon-index.pub`](../keys/addon-index.pub) in this repository and `index.pub` next to
   the index. The start flag `-plugin_index_pubkey` does the same. The one-click choice sets the key when none is
   configured yet.

   ```
   -----BEGIN PUBLIC KEY-----
   MCowBQYDK2VwAyEAEaDXYOjHyrKrLdbJYA0frdmww/Wd2xIfrRCpnHn+PMw=
   -----END PUBLIC KEY-----
   ```

   Fingerprint: `36557d137d47e9ee`. Take the key from this repository or from a Dunree release, not from a page
   somebody sent you: the key is what everything else is checked against.

3. **Plugin safety settings > Signature checking**: choose the mode.

## Off, warn, enforce

| Mode | The index | A program file |
|---|---|---|
| `off` | nothing is compared; the source shows `unchecked` | not compared |
| `warn` (default) | every problem is logged, shown in the source list and written to the audit log. Nothing is refused | a file that does not match `sha256` or `size` is installed, with a warning |
| `enforce` | add-ons are installed and updated only from an index with a valid signature of the configured key that is not older than the last one seen. While a source serves something else, the add-ons of its last valid index stay on offer | a file that does not match is refused; the download is cut off at `size` |

`warn` tells you about a problem and installs anyway. **Use `enforce` for this store**: it is always signed, so
`enforce` costs nothing and is the only mode in which the signature protects you.

## What the source list says

| State | Meaning | What to do |
|---|---|---|
| `signed` | valid signature of your key | nothing |
| `no_key` | no public key is configured | add the key |
| `missing` | no `index.json.sig` next to the index | the store published an unsigned draft, or something stripped the file. Do not install; check this repository for an announcement |
| `bad_signature` | the signature is not from your key | the index was changed on the way, or the store rotated its key. Check [SECURITY.md](../SECURITY.md) and the advisories before you replace a key |
| `replayed` | the index is older than one this Dunree has seen | someone serves an old index, or a cache is stale |
| `unchecked` | signature checking is off | turn it on |

## Installing

Before the install Dunree shows the publisher, the licence and the Dunree API endpoints the add-on asks for.
What the installed program declares is what you approve; a permission that was not in the index is not granted
silently.

Dunree downloads the artifact for exactly its own platform (for example `linux_amd64`), compares it with the
index, runs it once with `-introspect`, and only then moves it into place. A new add-on is not started until you
enable it. An update keeps the previous program file, so a failed update can be rolled back.

Independent of the mode, Dunree refuses an add-on whose `min_host_version` is newer than itself, and a program
that declares the id of another installed add-on.

## Things to know

* **One key for all sources.** Dunree holds one add-on index key. A second source signed with another key shows
  as `bad_signature` and is refused in enforce mode. To use a private store and this one together in enforce
  mode, list the add-ons you want from here in your private store ([private-store.md](private-store.md)).
* **Removing the source** stops every fetch. Installed add-ons keep running and get no updates.
* **A takedown does not uninstall.** When the store withdraws an add-on, your installed copy stays. Watch the
  security advisories of this repository.
* **The browser loads icons and screenshots** from the store address when you open the Add-ons page.
* **What the store learns about you:** GitHub Pages sees the address of your proxy when it fetches the index, and
  GitHub sees it when a program file is downloaded from a release. Nothing else is sent. To avoid both, mirror
  the store into a local folder.
