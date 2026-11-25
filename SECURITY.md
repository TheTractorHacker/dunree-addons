# Security

## Report a malicious or compromised add-on

**Privately, not in a public issue:** open a private report under
[Security > Report a vulnerability](https://github.com/TheTractorHacker/dunree-addons/security/advisories/new)
of this repository.

Say which add-on (`id`) and version, what it does that it should not, and how you found out. A sample, a network
capture or a pointer into the source helps. We aim to answer within a few working days.

Report here as well:

* a release asset that changed after it was listed (the checksum no longer matches);
* an add-on repository or publisher account that was taken over;
* a problem in the store itself: the scripts, the workflows, the published site;
* any sign that the signing key is used by someone else (an index you cannot explain, a serial that jumps).

A vulnerability in Dunree is reported to the Dunree repository, not here. A bug in an honest add-on is reported
to its publisher (the `homepage` of the add-on).

## Takedown policy

An add-on is removed from the store when:

* it is malicious, or its publisher or repository is compromised;
* it does something its description and permissions do not say (hidden connections, telemetry, loading code);
* it has a serious vulnerability and no fixed version arrives in reasonable time;
* its released files no longer match the checksums of the manifest;
* it passes for Dunree, Foley IT or another add-on, or the submitter had no right to publish it;
* a court or the law requires it.

What a takedown does:

1. **The manifest is deleted and a new index is published, with a higher serial.** Removal from `main` is not
   left waiting for a discussion when users are at risk; the discussion follows.
2. **The old index is dead for Dunree in enforce mode.** Dunree remembers the highest serial it has seen with a
   valid signature and reports an older index as replayed. Nobody can serve the index that still listed the
   add-on to a proxy that has seen the newer one.
3. **A security advisory is published** in this repository with the id, the affected versions and what
   administrators should do.
4. **Installed copies are not removed.** The store cannot reach into a proxy. An administrator has to disable
   and remove the add-on; the advisory says so. When a fixed version exists it is published under the same id,
   so that the update reaches installations.

The publisher is told, unless that would help an attacker. A removed add-on can come back by a normal pull
request once the reason is gone.

## If the signing key leaks or is lost

The key signs the index. Whoever holds it decides what a Dunree in enforce mode accepts from this store. The
format has no way to revoke a key from inside an index, and a higher serial does not help against someone who can
sign any serial. So the plan has two different tools:

**Serial bump: revokes an index.** A new index with a higher serial replaces every older one for proxies in
enforce mode. This is what a takedown uses. It works only while the key is ours alone.

**Key rotation: revokes the key.** If the private key is exposed, or we cannot rule it out:

1. Stop publishing with the old key. Delete the secret `ADDON_INDEX_KEY` if it is set.
2. Create a new key pair on a clean machine ([docs/key-handling.md](docs/key-handling.md)).
3. Replace `keys/addon-index.pub`, review every manifest that changed since the last index we are sure of, and
   publish an index signed with the new key, with a higher serial.
4. Publish a security advisory here and in the Dunree repository with the new public key and its fingerprint,
   over a channel that does not depend on the old key.
5. Ship a Dunree release with the new key built in (`DunreeAddonStorePublicKey`).
6. Administrators replace the key under **Plugin Manager > Plugin safety settings**. Replacing the key in Dunree
   is the revocation: nothing the old key signed is accepted any more.

Until an administrator has replaced the key, a proxy in enforce mode shows this store as `bad_signature` and
installs nothing new from it, which is the safe direction. A proxy that still trusts the old key can be served a
forged index by whoever holds that key **and** controls what the proxy receives from the store address.

If the key is only lost (no copy, no exposure), steps 2 to 6 apply without the urgency.

## What the store protects against, and what it does not

| Threat | Covered |
|---|---|
| The index is changed on the way or on the host | yes, in enforce mode: the signature fails |
| An old index is served again | yes, in enforce mode: the serial is lower than the one seen |
| A release asset is replaced after review | yes: the hash differs; Dunree in enforce mode refuses the file |
| A pull request from a fork tries to reach the key | yes: pull request workflows have no secrets and a read-only token |
| A malicious add-on passes review | **no**: review lowers the risk, it does not remove it |
| GitHub, or the account of the maintainer, is compromised (key in a GitHub secret) | **no**: use the offline flow, [docs/key-handling.md](docs/key-handling.md) |
| A Dunree in `warn` or `off` mode | **no**: problems are shown, nothing is refused |
