# Candidate dependency security remediation

This is a local candidate-only change, not a private-source push, new Agent design or formal release approval. Existing contracts, tool allowlists, memory authority and gateway boundaries remain unchanged.

Initial Python audit reported:

| Package | Advisory | Candidate remediation |
|---|---|---|
| Pydantic AI slim 2.46.0 | GHSA-6fqq-452j-qhrp: model limiter streaming capacity retention | Pin 2.53.0 |
| Pydantic AI slim 2.46.0 | GHSA-v36g-jcw9-x7cw: local web-fetch HTML conversion resource use | Pin 2.53.0 |
| pytest 9.0.2 | GHSA-6w46-j5rx-g56g: Unix temporary-directory weakness | Pin 9.0.3 in each Python test project |

Neither the SDK model-concurrency wrapper nor local web-fetch tools is registered in this application's current tools. That limits current reachability but does not erase the advisories or justify suppressing the audit. Same-major remediation is preferred to adding unused features or broad upgrades.

The patched SDK requires OpenAI >=3.19 and genai-prices >=0.1.9. The backend therefore pins OpenAI 3.19.0/genai-prices 0.1.13; unrelated constraints remain. The optional isolated ag-ui adapter requires ag-ui-protocol 0.1.22 rather than the old spike's 1.0.0. Its exact-version assertion is explicitly updated and strengthened with an exact SDK assertion; the independent-project-port assertions, all wire/stream tests and tool safety tests remain. This dependency change is not a change to the product's event envelope.

Locks are regenerated through uv, not manually edited. Agent SBOM/license metadata are regenerated against the lock; synthetic routing quality remains unmeasured and Jev stays disabled. Core contract exporter, existing negative tests, all synthetic backend/database/browser tests and spike drift checks must run against the final pins. A successful offline transport test does not prove real-provider model quality.

OpenAI documentation notes that retry behavior varies with SDK versions. Existing explicit no-retry/time-bound transport rules are preserved and tested; no live API request or model migration is made. See [official rate-limit handling](https://developers.openai.com/api/docs/guides/rate-limits#retrying-with-exponential-backoff), [model limiter advisory](https://github.com/pydantic/pydantic-ai/security/advisories/GHSA-6fqq-452j-qhrp) and [web-fetch advisory](https://github.com/pydantic/pydantic-ai/security/advisories/GHSA-v36g-jcw9-x7cw).

Final scan/test results belong in the public audit. Do not substitute these remediation intentions for a completed scan or claim production safety.
