#!/usr/bin/env python3
"""storetool - the checks and glue of the Dunree add-on store.

Standard library only. The index and the catalogue page are written by
tools/addon-store of the Dunree repository, and the signature by
tools/plugin-index/sign_plugin_index.go; this file does what those tools do not:

  validate        check every addons/<id>/addon.json against the store rules (no network)
  stage           download every artifact, compare sha256 and size, and lay out
                  the input folder tools/addon-store reads
  check-previous  fetch the published index and refuse a serial that is not higher
  finish          point the index at the release addresses, drop the copied
                  program files, check published versions did not change, brand the page
  mark-signed     render the page again once the index is signed
  diff            what a build changes in the catalogue, as plain text

scripts/build.sh runs them in order.
"""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

MAX_ARTIFACT = 256 << 20  # store policy; the format itself allows 1 GB
MAX_PICTURE = 4 << 20
MAX_INDEX = 8 << 20
PICTURE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}  # no svg: it can carry script
KNOWN_OS = {"linux", "windows", "darwin", "freebsd", "openbsd", "netbsd"}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
VERSION_RE = re.compile(r"^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})(-[0-9A-Za-z.-]+)?$")
PLATFORM_RE = re.compile(r"^([a-z0-9]{1,20})_([a-z0-9]{1,20})$")
LICENCE_RE = re.compile(r"^[A-Za-z0-9.+()-]+( (AND|OR|WITH) [A-Za-z0-9.+()-]+)*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
RELEASE_URL_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100})/releases/download/([^/?#%]{1,200})/([^/?#%]{1,128})$"
)
# Only for the local test of the pipeline (STORE_ALLOW_TEST_URLS=1), never set in a workflow
TEST_URL_RE = re.compile(r"^http://127\.0\.0\.1:[0-9]{2,5}/[A-Za-z0-9._/-]+$")

MANIFEST_KEYS = {
    "id", "name", "publisher", "description", "homepage", "licence", "license", "version", "api_version",
    "min_host_version", "type", "categories", "featured", "permissions", "changelog", "icon", "screenshots", "artifacts",
}
REQUIRED_KEYS = ["id", "name", "publisher", "description", "homepage", "version", "artifacts"]
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "*", "ANY"}

MARK_PATH = "M4 4H20V16H28V4H36V16H44V4H60V36A24 24 0 0 1 36 60H4Z M20 28H36A8 8 0 0 1 36 44H20Z"


class Problem(Exception):
    pass


def die(message):
    print("error: " + message, file=sys.stderr)
    sys.exit(1)


def test_urls_allowed():
    return os.environ.get("STORE_ALLOW_TEST_URLS") == "1"


# ---------------------------------------------------------------- names


CONFUSABLE = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "!": "l", "3": "e", "4": "a", "@": "a", "5": "s", "$": "s", "7": "t", "8": "b"})


def skeleton(text):
    """What a name looks like at a glance: no case, accents, spacing or
    punctuation, and digits read as the letters they are used for."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold().translate(CONFUSABLE)
    return "".join(c for c in text if c.isalnum())


def mixed_scripts(text):
    latin = other = False
    for c in text:
        if c.isalpha():
            if unicodedata.name(c, "").startswith("LATIN"):
                latin = True
            else:
                other = True
    return latin and other


def near(a, b):
    """True when two skeletons are the same or one edit apart (names of 6 or more)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 6 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:] or (i + 1 < len(a) and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2:] == b[i + 2:])
    return a[i:] == b[i + 1:]


def clean_text(value, limit, what, required=True):
    if value is None and not required:
        return
    if not isinstance(value, str) or (required and not value.strip()):
        raise Problem('"%s" is missing or not text' % what)
    if len(value) > limit:
        raise Problem('"%s" is longer than %d characters' % (what, limit))
    if any(unicodedata.category(c) in ("Cc", "Cf", "Co", "Cs") and c not in "\n\t" for c in value):
        raise Problem('"%s" has control or invisible characters' % what)


# ---------------------------------------------------------------- manifests


def load_json(path):
    def no_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise Problem('the field "%s" is there twice' % key)
            seen[key] = value
        return seen

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f, object_pairs_hook=no_duplicates)
    except (OSError, ValueError) as err:
        raise Problem("%s: %s" % (os.path.basename(path), err))


def load_policy(root):
    path = os.path.join(root, "policy.json")
    policy = {"reserved_words": ["dunree", "foleyit"], "reserved_id_prefixes": ["ie.foleyit.", "dunree."], "official_ids": []}
    if os.path.exists(path):
        policy.update(load_json(path))
    for key, kind in (("reserved_words", list), ("reserved_id_prefixes", list), ("official_ids", list), ("repository_moves", dict)):
        if not isinstance(policy.setdefault(key, kind()), kind):
            die("policy.json: %s must be a %s" % (key, kind.__name__))
    return policy


def addon_folders(addons_dir):
    """Folders that are add-ons. A name that starts with _ or . is never one:
    that is how addons/_example stays out of the index."""
    out = []
    for name in sorted(os.listdir(addons_dir)):
        full = os.path.join(addons_dir, name)
        if name.startswith(("_", ".")) or not os.path.isdir(full) or os.path.islink(full):
            continue
        out.append(name)
    return out


def inside(folder, rel, what):
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")) or "\\" in rel or any(p in ("", ".", "..") for p in rel.split("/")):
        raise Problem("%s must be a path inside the add-on folder" % what)
    full = os.path.join(folder, *rel.split("/"))
    # No link anywhere on the way: a linked folder would publish a file from outside the add-on
    if os.path.realpath(full) != os.path.join(os.path.realpath(folder), *rel.split("/")):
        raise Problem("%s: %s goes through a link; links are not published" % (what, rel))
    if os.path.islink(full) or not os.path.isfile(full):
        raise Problem("%s: %s is not a file in the add-on folder" % (what, rel))
    if os.path.splitext(full)[1].lower() not in PICTURE_EXT:
        raise Problem("%s: pictures must be png, jpg, webp or gif" % what)
    if not 0 < os.path.getsize(full) <= MAX_PICTURE:
        raise Problem("%s: must be between 1 byte and 4 MB" % what)
    return full


def check_url(url, version):
    """An artifact lives in a GitHub release of the add-on, under a tag that names the version."""
    if not isinstance(url, str):
        raise Problem("an artifact has no url")
    if test_urls_allowed() and TEST_URL_RE.match(url):
        parts = url.split("/", 3)[3].split("/")
        if any(p in ("", ".", "..") for p in parts):
            raise Problem("%s: empty, . and .. parts are not allowed in an address" % url)
        return (parts[0].lower() + "/test", parts[-1])  # the first part of the path plays the owner
    if not url.startswith("https://"):
        raise Problem("%s: an artifact address must be https" % url)
    if "/latest/" in url.lower() or "/releases/latest" in url.lower():
        raise Problem("%s: /latest/ moves; name the release tag" % url)
    match = RELEASE_URL_RE.match(url)
    if not match:
        raise Problem("%s: must be https://github.com/<owner>/<repo>/releases/download/<tag>/<file>" % url)
    owner, repo, tag, name = match.groups()
    if any(not part.strip(".") for part in (owner, repo, tag, name)):
        # github.com/<owner>/../... would be resolved to another repository by the server
        raise Problem("%s: . and .. are not allowed as a part of the address" % url)
    if tag.lower() == "latest":
        raise Problem("%s: /latest/ moves; name the release tag" % url)
    core = version.split("-")[0]
    if core not in tag:
        raise Problem("%s: the release tag %s does not name the version %s" % (url, tag, version))
    return ((owner + "/" + repo).lower(), name)


def url_repo(url):
    """owner/repo of an artifact address, lower case, or None. Lenient: also used
    on entries of the published index."""
    if not isinstance(url, str):
        return None
    match = RELEASE_URL_RE.match(url)
    if match:
        return (match.group(1) + "/" + match.group(2)).lower()
    if test_urls_allowed() and TEST_URL_RE.match(url):
        return url.split("/", 3)[3].split("/")[0].lower() + "/test"
    return None


def entry_repos(entry):
    arts = entry.get("artifacts") if isinstance(entry, dict) else None
    if not isinstance(arts, dict):
        return set()
    return {url_repo(a.get("url")) if isinstance(a, dict) else None for a in arts.values()}


def check_manifest(folder, name):
    """Returns the manifest of one add-on folder, or raises Problem."""
    m = load_json(os.path.join(folder, "addon.json"))
    if not isinstance(m, dict):
        raise Problem("addon.json is not an object")
    unknown = sorted(set(m) - MANIFEST_KEYS)
    if unknown:
        raise Problem("unknown field: " + ", ".join(unknown))
    for key in REQUIRED_KEYS:
        if key not in m:
            raise Problem('"%s" is missing' % key)
    if "licence" in m and "license" in m:
        raise Problem('give "licence" or "license", not both')
    licence = m.get("licence", m.get("license"))

    if not isinstance(m["id"], str) or not ID_RE.match(m["id"]) or ".." in m["id"]:
        raise Problem('"id" must be 1 to 128 lower-case letters, digits, dot, dash or underscore, and start with a letter or digit')
    if m["id"] != name:
        raise Problem('the folder is called %s but "id" is %s: they must be the same' % (name, m["id"]))
    clean_text(m["name"], 100, "name")
    clean_text(m["publisher"], 100, "publisher")
    clean_text(m["description"], 4000, "description")
    for field in ("name", "publisher"):
        if "\n" in m[field] or m[field] != m[field].strip():
            raise Problem('"%s" has a line break or surrounding spaces' % field)
        if mixed_scripts(m[field]):
            raise Problem('"%s" mixes Latin letters with letters of another script' % field)
    if not isinstance(licence, str) or not LICENCE_RE.match(licence) or len(licence) > 100:
        raise Problem('"licence" is missing or not an SPDX expression such as AGPL-3.0-only or MIT')
    if not isinstance(m["version"], str) or not VERSION_RE.match(m["version"]):
        raise Problem('"version" must be major.minor.patch')
    mhv = m.get("min_host_version")
    if mhv is not None and (not isinstance(mhv, str) or not VERSION_RE.match(mhv)):
        raise Problem('"min_host_version" must be major.minor.patch')
    api = m.get("api_version", 0)
    if isinstance(api, bool) or not isinstance(api, int) or not 0 <= api <= 1000:
        raise Problem('"api_version" must be a whole number')
    if m.get("type", "utility") not in ("router", "utility"):
        raise Problem('"type" must be router or utility')
    if not isinstance(m.get("featured", False), bool):
        raise Problem('"featured" must be true or false')
    home = urllib.parse.urlsplit(m["homepage"]) if isinstance(m["homepage"], str) else None
    if not home or home.scheme != "https" or not home.hostname or home.username or len(m["homepage"]) > 500:
        raise Problem('"homepage" must be an https address')
    cats = m.get("categories", [])
    if not isinstance(cats, list) or len(cats) > 5:
        raise Problem('"categories" must be a list of at most 5')
    for c in cats:
        clean_text(c, 40, "categories")

    perms = m.get("permissions", [])
    if not isinstance(perms, list) or len(perms) > 100:
        raise Problem('"permissions" must be a list')
    for p in perms:
        if not isinstance(p, dict) or set(p) - {"method", "endpoint", "reason"}:
            raise Problem("a permission has the fields method, endpoint and reason")
        if not isinstance(p.get("method"), str) or p["method"] not in METHODS:
            raise Problem("a permission needs a method (GET, POST, ...)")
        if not isinstance(p.get("endpoint"), str) or not re.match(r"^/[A-Za-z0-9_./*{}:-]{0,200}$", p["endpoint"]):
            raise Problem("a permission needs an endpoint that starts with /")
        clean_text(p.get("reason"), 300, "reason of a permission")  # the store wants a reason for each one

    log = m.get("changelog", [])
    if not isinstance(log, list) or len(log) > 200:
        raise Problem('"changelog" must be a list')
    for entry in log:
        if not isinstance(entry, dict) or set(entry) - {"version", "date", "notes"}:
            raise Problem("a changelog entry has the fields version, date and notes")
        if not isinstance(entry.get("version"), str) or not VERSION_RE.match(entry["version"]):
            raise Problem("a changelog entry needs a version")
        if "date" in entry and (not isinstance(entry["date"], str) or not DATE_RE.match(entry["date"])):
            raise Problem("a changelog date is YYYY-MM-DD")
        clean_text(entry.get("notes"), 2000, "changelog notes", required=False)
    if log and log[0]["version"] != m["version"]:
        raise Problem('the first changelog entry must be for the version %s (newest first)' % m["version"])

    if "icon" in m:
        inside(folder, m["icon"], "icon")
    shots = m.get("screenshots", [])
    if not isinstance(shots, list) or len(shots) > 8:
        raise Problem('"screenshots" must be a list of at most 8')
    if len({s.rsplit("/", 1)[-1] for s in shots if isinstance(s, str)}) != len(shots):
        raise Problem("two screenshots have the same file name")
    for s in shots:
        inside(folder, s, "screenshot")

    arts = m["artifacts"]
    if not isinstance(arts, dict) or not arts:
        raise Problem('"artifacts" must name at least one platform')
    repos, files = set(), set()
    for platform, art in sorted(arts.items()):
        match = PLATFORM_RE.match(platform)
        if not match or match.group(1) not in KNOWN_OS:
            raise Problem("artifact platform %s must be os_arch as Go names them, e.g. linux_amd64" % platform)
        if not isinstance(art, dict) or set(art) != {"url", "sha256", "size"}:
            raise Problem("artifact %s must have exactly url, sha256 and size" % platform)
        if not isinstance(art["sha256"], str) or not SHA_RE.match(art["sha256"]):
            raise Problem("artifact %s: sha256 must be 64 lower-case hex digits" % platform)
        if isinstance(art["size"], bool) or not isinstance(art["size"], int) or not 0 < art["size"] <= MAX_ARTIFACT:
            raise Problem("artifact %s: size must be the number of bytes, at most %d MB" % (platform, MAX_ARTIFACT >> 20))
        repo, fname = check_url(art["url"], m["version"])
        if not FILE_RE.match(fname):
            raise Problem("artifact %s: the file name %s may only have letters, digits, dot, dash and underscore" % (platform, fname))
        is_exe = fname.lower().endswith(".exe")
        if (match.group(1) == "windows") != is_exe:
            raise Problem("artifact %s: a Windows program file ends in .exe, and only a Windows one does" % platform)
        if fname.lower() in files:
            raise Problem("two artifacts are called %s" % fname)
        files.add(fname.lower())
        repos.add(repo)
    if len(repos) > 1:
        raise Problem("the artifacts come from more than one repository: " + ", ".join(sorted(repos)))
    return m


def check_impersonation(manifests, policy):
    """No add-on may pass for Dunree, for Foley IT, or for another add-on."""
    problems = []
    official = set(policy.get("official_ids", []))
    words = [skeleton(w) for w in policy.get("reserved_words", [])]
    prefixes = [p.lower() for p in policy.get("reserved_id_prefixes", [])]
    for m in manifests:
        if m["id"] in official:
            continue
        for field in ("name", "publisher"):
            hit = [w for w in words if w and w in skeleton(m[field])]
            if hit:
                problems.append('%s: "%s" (%s) uses a name reserved for Dunree and Foley IT. Say what the add-on does; the description may say it is for Dunree' % (m["id"], field, m[field]))
        id_skel = skeleton(m["id"])
        if any(m["id"].startswith(p) for p in prefixes) or any(w and w in id_skel for w in words):
            problems.append("%s: this id is in a namespace reserved for Dunree and Foley IT. Use your own domain in reverse" % m["id"])
    for i, a in enumerate(manifests):
        for b in manifests[i + 1:]:
            if near(skeleton(a["name"]), skeleton(b["name"])):
                problems.append('%s and %s: the names "%s" and "%s" are the same or too close to tell apart' % (a["id"], b["id"], a["name"], b["name"]))
            if skeleton(a["id"]) == skeleton(b["id"]):
                problems.append("%s and %s: the ids are too close to tell apart" % (a["id"], b["id"]))
            # A publisher is tied to the account its releases come from: the same (or a
            # look-alike) publisher name from another GitHub account passes for someone else
            if near(skeleton(a["publisher"]), skeleton(b["publisher"])):
                owners = {r.split("/")[0] for r in entry_repos(a) | entry_repos(b) if r}
                if len(owners) > 1:
                    problems.append('%s and %s: the publisher "%s" / "%s" is the same or too close, but the artifacts come from different accounts (%s)' % (
                        a["id"], b["id"], a["publisher"], b["publisher"], ", ".join(sorted(owners))))
    return problems


def load_all(root, addons_dir):
    manifests, problems = [], []
    for name in addon_folders(addons_dir):
        folder = os.path.join(addons_dir, name)
        if os.path.islink(os.path.join(folder, "addon.json")) or not os.path.isfile(os.path.join(folder, "addon.json")):
            problems.append("%s: no addon.json (a link is not read)" % name)
            continue
        try:
            manifests.append(check_manifest(folder, name))
        except Problem as err:
            problems.append("%s: %s" % (name, err))
    if not problems:
        problems = check_impersonation(manifests, load_policy(root))
    if problems:
        die("the catalogue is not valid:\n  " + "\n  ".join(problems))
    return manifests


def cmd_validate(args):
    manifests = load_all(args.root, args.addons)
    print("OK: %d add-on manifests are valid" % len(manifests))


# ---------------------------------------------------------------- download


class NoRedirectToHttp(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://") and not (test_urls_allowed() and newurl.startswith("http://127.0.0.1:")):
            raise urllib.error.URLError("redirect to an address that is not https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url, timeout=60, fresh=False):
    opener = urllib.request.build_opener(NoRedirectToHttp)
    headers = {"User-Agent": "dunree-addons-store"}
    if fresh:
        headers.update({"Cache-Control": "no-cache", "Pragma": "no-cache"})
    return opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)


def download(url, dest, want_sha, want_size):
    """Downloads at most want_size+1 bytes and compares the checksum."""
    h, got = hashlib.sha256(), 0
    try:
        with open_url(url) as resp, open(dest, "wb") as out:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                got += len(chunk)
                if got > want_size:
                    raise Problem("%s is larger than the %d bytes the manifest says" % (url, want_size))
                h.update(chunk)
                out.write(chunk)
    except (urllib.error.URLError, OSError) as err:
        raise Problem("%s could not be downloaded: %s" % (url, err))
    if got != want_size:
        raise Problem("%s has %d bytes, the manifest says %d" % (url, got, want_size))
    if h.hexdigest() != want_sha:
        raise Problem("%s has sha256 %s, the manifest says %s" % (url, h.hexdigest(), want_sha))


def cmd_stage(args):
    """Writes the folder tools/addon-store reads: the same manifest, with the
    downloaded and verified files in place of the addresses."""
    manifests = load_all(args.root, args.addons)
    if os.path.exists(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out)
    problems = []
    for m in manifests:
        src, dst = os.path.join(args.addons, m["id"]), os.path.join(args.out, m["id"])
        os.makedirs(os.path.join(dst, "artifacts"))
        staged = {k: v for k, v in m.items() if k != "artifacts"}
        staged["artifacts"] = {}
        for platform, art in sorted(m["artifacts"].items()):
            fname = art["url"].rsplit("/", 1)[1]
            try:
                download(art["url"], os.path.join(dst, "artifacts", fname), art["sha256"], art["size"])
                print("verified %s %s (%d bytes, sha256 %s)" % (m["id"], platform, art["size"], art["sha256"]))
            except Problem as err:
                problems.append("%s, %s: %s" % (m["id"], platform, err))
            staged["artifacts"][platform] = {"file": "artifacts/" + fname, "sha256": art["sha256"]}
        for rel in ([m["icon"]] if "icon" in m else []) + m.get("screenshots", []):
            target = os.path.join(dst, *rel.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(os.path.join(src, *rel.split("/")), target)
        with open(os.path.join(dst, "addon.json"), "w", encoding="utf-8") as f:
            json.dump(staged, f, indent=2, ensure_ascii=False)
    if problems:
        die("an artifact is not what its manifest says:\n  " + "\n  ".join(problems))
    print("OK: %d add-ons staged in %s" % (len(manifests), args.out))


# ---------------------------------------------------------------- the published index


def read_index(path):
    with open(path, "rb") as f:
        raw = f.read(MAX_INDEX + 1)
    if len(raw) > MAX_INDEX:
        raise Problem("%s is larger than 8 MB" % path)
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != "dunree-addon-index" or doc.get("version") != 1:
        raise Problem("%s is not a Dunree add-on index, format version 1" % path)
    if isinstance(doc.get("serial"), bool) or not isinstance(doc.get("serial"), int) or not isinstance(doc.get("addons"), list):
        raise Problem("%s has no serial number or no add-ons" % path)
    return doc


def cmd_check_previous(args):
    """The serial rule: a new index must have a higher serial than the one that
    is published. Saves the published index for the later checks and the diff."""
    source = args.source
    if os.path.lexists(args.save):
        os.remove(args.save)
    if source == "none":
        print("serial %d: not compared with a published index (PREVIOUS_INDEX=none)" % args.serial)
        return
    if re.match(r"^https?://", source):
        if not source.startswith("https://") and not (test_urls_allowed() and source.startswith("http://127.0.0.1:")):
            die("the published index must be fetched over https: " + source)
        # GitHub Pages is behind a CDN that caches for minutes. A stale copy would hide
        # the newest serial and the newest versions from the checks, so the address is
        # made unique for this build and caches are asked to revalidate.
        fresh_url = source + ("&" if "?" in source else "?") + "fresh=%d" % args.serial
        try:
            with open_url(fresh_url, timeout=30, fresh=True) as resp:
                raw = resp.read(MAX_INDEX + 1)
        except urllib.error.HTTPError as err:
            if err.code == 404:
                print("serial %d: nothing is published at %s yet (404), this is the first index" % (args.serial, source))
                return
            die("the published index could not be fetched (%s): %s. Nothing was built: without it the serial cannot be checked" % (source, err))
        except (urllib.error.URLError, OSError) as err:
            die("the published index could not be fetched (%s): %s. Nothing was built: without it the serial cannot be checked" % (source, err))
        with open(args.save, "wb") as f:
            f.write(raw)
    else:
        if not os.path.isfile(source):
            die("PREVIOUS_INDEX %s is not a file (use none to compare with nothing)" % source)
        shutil.copyfile(source, args.save)
    try:
        previous = read_index(args.save)
    except (Problem, ValueError) as err:
        os.remove(args.save)
        die("what is published at %s is not an add-on index: %s" % (source, err))
    if args.serial <= previous["serial"]:
        os.remove(args.save)
        die("serial %d is not higher than the published serial %d (%s). Dunree reports an older index as replayed, so it is refused here" % (args.serial, previous["serial"], source))
    print("serial %d is higher than the published serial %d" % (args.serial, previous["serial"]))


def version_key(v):
    core = v.split("-")[0].split("+")[0]
    return tuple(int(x) for x in core.split("."))


def check_immutable(previous, manifests, policy=None):
    """What a published version points at never changes, versions do not go down,
    and the program files of an add-on keep coming from the same repository."""
    problems = []
    moves = {k: str(v).lower() for k, v in (policy or {}).get("repository_moves", {}).items()}
    old = {a.get("id"): a for a in previous.get("addons", []) if isinstance(a, dict)}
    for m in manifests:
        before = old.get(m["id"])
        if not before or not isinstance(before.get("version"), str):
            continue
        was, now = entry_repos(before), entry_repos(m)
        if was and now != was and not (len(now) == 1 and moves.get(m["id"]) in now):
            problems.append(
                "%s: the artifacts moved from %s to %s. A takeover looks exactly like this; a maintainer who has "
                'checked it confirms the move in policy.json: "repository_moves": {"%s": "%s"}' % (
                    m["id"], ", ".join(sorted(r or "?" for r in was)), ", ".join(sorted(r or "?" for r in now)), m["id"], sorted(r or "?" for r in now)[0]))
        try:
            went_down = version_key(m["version"]) < version_key(before["version"])
        except ValueError:
            continue
        if went_down:
            problems.append("%s: version %s is lower than the published %s" % (m["id"], m["version"], before["version"]))
        elif m["version"] == before["version"] and m["artifacts"] != before.get("artifacts"):
            problems.append("%s: version %s is published already and its artifacts changed. A published version is never replaced: raise \"version\"" % (m["id"], m["version"]))
    return problems


# ---------------------------------------------------------------- finish


BADGE_RE = re.compile(r'\s*<span class="badge (?:ok|warn)">(?:Signed index|Index not signed)</span>')

BRAND_CSS = """
.brand { display: flex; align-items: center; gap: .6rem; margin: 0 0 1.25rem; }
.brand svg { width: 32px; height: 32px; fill: var(--accent); flex: 0 0 auto; }
.brand b { font-size: 1.15rem; letter-spacing: .01em; }
.brand span { color: var(--muted); font-size: .9rem; }
.trust { background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--ok); border-radius: 10px; padding: 1rem; margin: 0 0 1.25rem; }
.trust.draft { border-left-color: var(--warn); }
.trust h2 { margin: 0 0 .5rem; font-size: 1rem; }
.trust p { margin: .35rem 0; }
.trust pre { margin: .5rem 0 0; padding: .6rem .75rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; font-size: .8rem; }
"""


def public_key_text(pub_path):
    with open(pub_path, encoding="ascii") as f:
        text = f.read().strip()
    if "PRIVATE" in text or "BEGIN PUBLIC KEY" not in text:
        raise Problem("%s is not a public key" % pub_path)
    return text


def render_page(raw, info, signed, fingerprint=""):
    """Brands the page tools/addon-store wrote and says whether the index is
    signed. The tool is run without a key, so the page it writes always says
    'not signed'; that line is replaced by the state this build really has."""
    for anchor in ("</head>", "</style>", "<main>"):
        if raw.count(anchor) != 1:
            raise Problem("the catalogue page of tools/addon-store changed (%s not found once): scripts/storetool.py must follow" % anchor)
    raw, badges = BADGE_RE.subn("", raw)
    if badges != 1:
        raise Problem("the catalogue page of tools/addon-store changed (its signature badge was not found): scripts/storetool.py must follow")
    esc = html.escape
    index_url = info["store_url"].rstrip("/") + "/index.json"
    if signed:
        state = (
            '<section class="trust"><h2>Signed index <span class="badge ok">serial %d</span></h2>'
            "<p>Index address: <code>%s</code></p>"
            "<p>The index is signed with the key of this store%s. Give Dunree the public key under <b>Plugin Manager &gt; Plugin safety settings</b> "
            'and set <b>Signature checking</b> to <b>enforce</b>: <a href="index.pub">index.pub</a></p><pre>%s</pre></section>'
        ) % (info["serial"], esc(index_url), (" (fingerprint <code>%s</code>)" % esc(fingerprint)) if fingerprint else "", esc(info["public_key"]))
    else:
        state = (
            '<section class="trust draft"><h2>Draft: this index is not signed <span class="badge warn">serial %d</span></h2>'
            "<p>This is a build that was not signed with the key of the store. Dunree shows such a source as <b>missing</b> "
            "and refuses it when signature checking is set to <b>enforce</b>. Do not install from it.</p></section>"
        ) % info["serial"]
    brand = (
        '<header class="brand"><svg viewBox="0 0 64 64" role="img" aria-label="Dunree"><path fill-rule="evenodd" d="%s"/></svg>'
        "<b>Dunree</b><span>reverse proxy and web gateway</span></header>"
    ) % MARK_PATH
    raw = raw.replace("</style>", BRAND_CSS + "</style>")
    raw = raw.replace("</head>", '<link rel="icon" type="image/svg+xml" href="favicon.svg">\n</head>')
    raw = raw.replace("<main>", "<main>\n" + brand + "\n" + state)
    return raw


def write_page(site, work, info, signed, fingerprint=""):
    with open(os.path.join(work, "tool-index.html"), encoding="utf-8") as f:
        raw = f.read()
    page = render_page(raw, info, signed, fingerprint)
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


def cmd_finish(args):
    manifests = {m["id"]: m for m in load_all(args.root, args.addons)}
    site, work = args.site, args.work
    index_path = os.path.join(site, "index.json")
    try:
        doc = read_index(index_path)
        page_path = os.path.join(site, "index.html")
        with open(page_path, encoding="utf-8") as f:
            page = f.read()
        if sorted(a["id"] for a in doc["addons"]) != sorted(manifests):
            raise Problem("the index does not list exactly the add-ons of addons/")

        previous_path = os.path.join(work, "previous-index.json")
        if os.path.exists(previous_path):
            problems = check_immutable(read_index(previous_path), manifests.values(), load_policy(args.root))
            if problems:
                raise Problem("\n  ".join(problems))

        # The program files stay in the releases of their add-ons: the index names
        # those addresses, and the copies the tool made are not published
        for a in doc["addons"]:
            m = manifests[a["id"]]
            if set(a["artifacts"]) != set(m["artifacts"]):
                raise Problem("%s: the index and the manifest list other platforms" % a["id"])
            for platform, art in a["artifacts"].items():
                want = m["artifacts"][platform]
                if art["sha256"] != want["sha256"] or art["size"] != want["size"]:
                    raise Problem("%s, %s: checksum or size differ between the index and the manifest" % (a["id"], platform))
                local = art["url"]
                href = 'href="%s"' % html.escape(local)
                if urllib.parse.urlsplit(local).scheme or page.count(href) != 1:
                    raise Problem("%s, %s: unexpected address %s in what tools/addon-store wrote" % (a["id"], platform, local))
                page = page.replace(href, 'href="%s" rel="noopener noreferrer"' % html.escape(want["url"]))
                copied = os.path.join(site, *local.split("/"))
                os.remove(copied)
                art["url"] = want["url"]
            version_dir = os.path.join(site, "addons", a["id"], a["version"])
            os.rmdir(version_dir)  # fails if something unexpected is in it
            if not os.listdir(os.path.dirname(version_dir)):
                os.rmdir(os.path.dirname(version_dir))
        if os.path.isdir(os.path.join(site, "addons")) and not os.listdir(os.path.join(site, "addons")):
            os.rmdir(os.path.join(site, "addons"))

        raw = (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        with open(index_path, "wb") as f:
            f.write(raw)
        with open(os.path.join(work, "tool-index.html"), "w", encoding="utf-8") as f:
            f.write(page)

        shutil.copyfile(args.pub, os.path.join(site, "index.pub"))
        for name in ("favicon.svg", "dunree-mark.svg"):
            shutil.copyfile(os.path.join(args.root, "brand", name), os.path.join(site, name))
        open(os.path.join(site, ".nojekyll"), "w").close()
        # On the gh-pages branch git must not touch line ends: the signature is over the exact bytes
        with open(os.path.join(site, ".gitattributes"), "w") as f:
            f.write("* -text\n")
        info = {
            "serial": doc["serial"],
            "store_url": args.store_url,
            "public_key": public_key_text(args.pub),
            "addons": len(doc["addons"]),
            "index_sha256": hashlib.sha256(raw).hexdigest(),
            "dunree_ref": args.dunree_ref,
            "dunree_commit": args.dunree_commit,
            "store_commit": args.store_commit,
        }
        with open(os.path.join(work, "build-info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
        public = {k: info[k] for k in ("serial", "addons", "index_sha256", "dunree_ref", "dunree_commit", "store_commit")}
        with open(os.path.join(site, "build.json"), "w", encoding="utf-8") as f:
            json.dump(public, f, indent=2)
            f.write("\n")
        write_page(site, work, info, signed=False)
    except (Problem, OSError, ValueError, KeyError) as err:
        shutil.rmtree(site, ignore_errors=True)  # never leave a half-finished site behind
        die("not built: %s" % err)
    print("OK: %s lists %d add-ons at their release addresses, serial %d, NOT signed yet" % (index_path, len(doc["addons"]), doc["serial"]))


def cmd_mark_signed(args):
    with open(os.path.join(args.work, "build-info.json"), encoding="utf-8") as f:
        info = json.load(f)
    with open(os.path.join(args.site, "index.json"), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != info["index_sha256"]:
            die("index.json changed since scripts/build.sh wrote it")
    sig = os.path.join(args.site, "index.json.sig")
    if not os.path.isfile(sig) or os.path.getsize(sig) != 64:
        die("there is no signature of 64 bytes next to index.json")
    try:
        write_page(args.site, args.work, info, signed=True, fingerprint=args.fingerprint)
    except Problem as err:
        die(str(err))
    print("OK: the catalogue page says the index is signed")


# ---------------------------------------------------------------- diff


def one_line(value):
    return " ".join(str(value).split())[:300]


def describe(a):
    lines = ["    name: %s | publisher: %s | version: %s | licence: %s | type: %s" % (
        one_line(a.get("name")), one_line(a.get("publisher")), one_line(a.get("version")), one_line(a.get("licence", "")), one_line(a.get("type", "utility")))]
    lines.append("    homepage: %s" % one_line(a.get("homepage", "")))
    for p in a.get("permissions") or []:
        lines.append("    permission: %s %s (%s)" % (one_line(p.get("method")), one_line(p.get("endpoint")), one_line(p.get("reason", ""))))
    if not a.get("permissions"):
        lines.append("    permissions: none")
    for platform, art in sorted((a.get("artifacts") or {}).items()):
        lines.append("    %s: %s" % (platform, one_line(art.get("url"))))
        lines.append("      sha256 %s, %s bytes" % (one_line(art.get("sha256")), one_line(art.get("size"))))
    return lines


def cmd_diff(args):
    new = read_index(args.new)
    old = read_index(args.old) if args.old and os.path.exists(args.old) else {"serial": 0, "addons": []}
    before = {a["id"]: a for a in old["addons"]}
    after = {a["id"]: a for a in new["addons"]}
    out = ["Catalogue: %d add-ons published (serial %s), %d after this change." % (len(before), old["serial"] or "none", len(after)), ""]
    changed = False
    for i in sorted(set(after) - set(before)):
        changed = True
        out += ["ADDED " + i] + describe(after[i]) + [""]
    for i in sorted(set(before) - set(after)):
        changed = True
        out += ["REMOVED %s (was %s by %s, version %s)" % (i, one_line(before[i].get("name")), one_line(before[i].get("publisher")), one_line(before[i].get("version"))), ""]
    for i in sorted(set(before) & set(after)):
        a, b = before[i], after[i]
        if a == b:
            continue
        changed = True
        out.append("CHANGED " + i)
        if entry_repos(a) != entry_repos(b):
            out.append("    !! ARTIFACT REPOSITORY CHANGED: %s -> %s" % (", ".join(sorted(r or "?" for r in entry_repos(a))), ", ".join(sorted(r or "?" for r in entry_repos(b)))))
        if a.get("publisher") != b.get("publisher"):
            out.append("    !! PUBLISHER CHANGED")
        if len(b.get("permissions") or []) > len(a.get("permissions") or []):
            out.append("    !! ASKS FOR MORE PERMISSIONS")
        for key in sorted(set(a) | set(b)):
            if a.get(key) == b.get(key):
                continue
            if key == "permissions":
                was = {json.dumps(p, sort_keys=True) for p in a.get(key) or []}
                now = {json.dumps(p, sort_keys=True) for p in b.get(key) or []}
                for p in sorted(now - was):
                    out.append("    permission ADDED: " + one_line(p))
                for p in sorted(was - now):
                    out.append("    permission removed: " + one_line(p))
            elif key == "artifacts":
                for platform in sorted(set(a.get(key) or {}) | set(b.get(key) or {})):
                    x, y = (a.get(key) or {}).get(platform), (b.get(key) or {}).get(platform)
                    if x != y:
                        out.append("    %s: %s" % (platform, "removed" if y is None else one_line(y.get("url"))))
                        if y is not None:
                            out.append("      sha256 %s, %s bytes%s" % (one_line(y.get("sha256")), one_line(y.get("size")), "" if x else " (new platform)"))
            elif key in ("changelog", "screenshots", "description", "categories"):
                out.append("    %s changed" % key)
            else:
                out.append("    %s: %s -> %s" % (key, one_line(a.get(key, "(none)")), one_line(b.get(key, "(none)"))))
        out.append("")
    if not changed:
        out.append("No add-on is added, removed or changed.")
    text = "\n".join(out).rstrip() + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    sys.stdout.write(text)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=root, help=argparse.SUPPRESS)
    parser.add_argument("--addons", default=os.environ.get("ADDONS_DIR") or os.path.join(root, "addons"), help="folder with one folder per add-on")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate").set_defaults(func=cmd_validate)
    p = sub.add_parser("stage")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_stage)
    p = sub.add_parser("check-previous")
    p.add_argument("--serial", type=int, required=True)
    p.add_argument("--source", required=True, help="address or file of the published index.json, or none")
    p.add_argument("--save", required=True)
    p.set_defaults(func=cmd_check_previous)
    p = sub.add_parser("finish")
    for name in ("site", "work", "pub", "store-url"):
        p.add_argument("--" + name, required=True)
    for name in ("dunree-ref", "dunree-commit", "store-commit"):
        p.add_argument("--" + name, default="")
    p.set_defaults(func=cmd_finish)
    p = sub.add_parser("mark-signed")
    p.add_argument("--site", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--fingerprint", default="")
    p.set_defaults(func=cmd_mark_signed)
    p = sub.add_parser("diff")
    p.add_argument("--old")
    p.add_argument("--new", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_diff)
    args = parser.parse_args()
    if args.command in ("validate", "stage", "finish") and not os.path.isdir(args.addons):
        die("%s is not a folder" % args.addons)
    args.func(args)


if __name__ == "__main__":
    main()
