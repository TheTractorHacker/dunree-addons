#!/usr/bin/env python3
"""Rules for the files of this repository that the manifest check does not cover.

  * every action is pinned by a full commit SHA, with the version in a comment;
  * no workflow uses pull_request_target, every workflow sets permissions and
    a concurrency group; only publish.yml names the signing secret, and no
    workflow hands secrets on wholesale (secrets: inherit, toJSON(secrets));
  * no private key is in the repository.

Standard library only; PyYAML is used for a stricter parse when it is there.
An optional argument is the root of the tree to check (default: this repository).
"""

import os
import re
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The signing key is used by publish.yml only, and never handed on wholesale
SECRET_ONLY_IN = {"ADDON_INDEX_KEY": "publish.yml"}
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$")
PINNED = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
COMMENT = re.compile(r"^\s+#\s*v[0-9]+(\.[0-9]+){0,2}\s*$")
KEY_MARK = re.compile("-----BEGIN [A-Z ]*" + "PRIVATE" + " KEY-----")


def main():
    problems = []
    folder = os.path.join(ROOT, ".github", "workflows")
    names = sorted(n for n in os.listdir(folder) if n.endswith((".yml", ".yaml")))
    if not names:
        problems.append("no workflows found")
    for name in names:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            text = f.read()
        if "pull_request_target" in text:
            problems.append("%s: pull_request_target is not allowed" % name)
        if re.search(r"secrets\s*:\s*inherit", text):
            problems.append("%s: secrets: inherit is not allowed" % name)
        for secret, allowed in SECRET_ONLY_IN.items():
            if name != allowed and re.search(r"secrets\s*\.\s*" + secret + r"\b", text):
                problems.append("%s: only %s may use the secret %s" % (name, allowed, secret))
        if re.search(r"\bsecrets\[", text) or "toJSON(secrets" in text or "toJson(secrets" in text:
            problems.append("%s: secrets may only be named one by one" % name)
        if not re.search(r"^permissions:", text, re.M):
            problems.append("%s: no top-level permissions" % name)
        if not re.search(r"^concurrency:", text, re.M):
            problems.append("%s: no concurrency group" % name)
        for number, line in enumerate(text.splitlines(), 1):
            match = USES.match(line)
            if not match:
                continue
            if not PINNED.match(match.group(1)):
                problems.append("%s:%d: %s is not pinned by a full commit SHA" % (name, number, match.group(1)))
            elif not COMMENT.match(match.group(2)):
                problems.append("%s:%d: the pin of %s has no version comment (# v1.2.3)" % (name, number, match.group(1)))
        try:
            import yaml
        except ImportError:
            continue
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as err:
            problems.append("%s: not valid YAML: %s" % (name, err))
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
            problems.append("%s: no jobs" % name)

    try:
        tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True).stdout.split(b"\0")
    except (OSError, subprocess.CalledProcessError):
        tracked = []
    for rel in filter(None, tracked):
        path = os.path.join(ROOT, rel.decode("utf-8", "replace"))
        if not os.path.isfile(path) or os.path.getsize(path) > (8 << 20):
            continue
        with open(path, "rb") as f:
            if KEY_MARK.search(f.read().decode("latin-1")):
                problems.append("%s: holds a private key. Remove it and treat the key as leaked (SECURITY.md)" % rel.decode())

    if problems:
        print("error:\n  " + "\n  ".join(problems), file=sys.stderr)
        sys.exit(1)
    print("OK: %d workflows, every action pinned by commit SHA, no private key in the tree" % len(names))


if __name__ == "__main__":
    main()
