# ClassMatter security boundaries

Pre-alpha, synthetic data only. Not approved for real students, public deployment or organizational responsibility assignment. No production security certification is claimed.

Default entry points bind loopback. Queries use QG, writes use preview/approval/BCG and identity uses ISB. Model text cannot grant permission or mutate schema. Secret storage in the supported Windows local runtime uses DPAPI; do not copy runtime directories across hosts. Model endpoint compatibility does not establish provider trust or safe handling of user-entered private text.

Do not publish vulnerabilities with credentials, student data, personal screenshots or original logs. A dedicated private reporting channel has not yet been configured; do not post sensitive evidence in public issues, discussions or pull requests and do not invent a security email address. GitHub private vulnerability reporting is available to public repositories: after the owner separately authorizes Public visibility, the maintainer should enable it in Settings > Security and quality > Advanced Security, verify the private report form, and only then update this policy to claim an active private channel. Until a channel is verified, request contact through a nonsensitive inquiry rather than sending exploit details.

If a secret is exposed: stop publication, revoke/rotate with the issuer, preserve restricted evidence, review all affected refs/platform artifacts, then re-audit a new candidate. Deleting a file on main does not remove historical objects.
