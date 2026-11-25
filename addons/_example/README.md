# Example add-on (not published)

This folder is a template. A folder of `addons/` whose name starts with `_` is never read by the build, so
`_example` is not in the index and not on the catalogue page.

To start your own entry:

```sh
cp -r addons/_example addons/org.example.hello     # use your own id: your domain in reverse, lower case
rm addons/org.example.hello/README.md
$EDITOR addons/org.example.hello/addon.json
python3 scripts/storetool.py validate
```

The folder name must be exactly the `id` in `addon.json`. Replace every value: the checksums in the template are
zeros and the addresses do not exist. An optional `icon.png` and a `screenshots/` folder go next to `addon.json`
(`"icon": "icon.png"`, `"screenshots": ["screenshots/rules.png"]`).

The full walk-through is in [docs/publishing-an-addon.md](../../docs/publishing-an-addon.md).
