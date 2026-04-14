# P11.3 Package Plan: Fetch V2

## Package Ralplan

P11.3 upgrades source intake for external links from locator-only manifests to
public-safe, bounded retrieval artifacts. The target loop is: "throw in a link"
for article/html, PDF/arXiv, and GitHub artifacts, then get a source packet
with useful metadata and a digest job without committing rights-unsafe full
content.

P11.3 does not implement digest queue providers, reconcile/apply automation,
OpenClaw live bridge, lint/doctor split, or subject/file-index commands.

## Reality Check

- `workers/fetch.py` currently fetches only local drafts. Article/html and
  PDF/arXiv use deferred manifests; GitHub URLs are parsed but not split into
  blob/issue/PR/diff contracts.
- `RAW_POLICY.md` requires excerpt-only defaults for third-party articles,
  PDFs, and most GitHub artifacts unless redistributable status is explicit.
- Tests must not depend on external network availability. Use local HTTP
  servers, injected opener/fetcher fakes, and local fixtures for deterministic
  fetch behavior; keep URL parsing tests for real GitHub/arXiv shapes.
- No new dependencies are allowed. Use stdlib `urllib`, `html.parser`,
  `email.message`/headers, `hashlib`, `ipaddress`, `socket`, and conservative
  text extraction.
- PDF text extraction without dependencies is limited. P11.3 can store metadata
  plus byte hash/length and a safe binary excerpt manifest; full PDF bytes stay
  out of Git unless explicitly stored as local-only blob outside tracked packet
  files.
- Existing digest provider request sanitization only exposes a small artifact
  allowlist. P11.3 must update that allowlist so useful fetch metadata reaches
  digest providers while path/blob secrets stay redacted.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.3a HTTP fetch core | Add bounded HTTP retrieval with timeouts, content-type/size guards, and SSRF protections | `workers/fetch.py` | local HTTP/fake opener tests for HTML, PDF, 404, oversize, non-UTF bytes, private IPs, redirects | fetch_chain records method/status; failures produce partial/blocked packets without tracebacks; private/local network URLs fail before fetch | unbounded download, SSRF exposure, or network-only tests |
| P11.3b Article/html body extraction | Extract public-safe article text/excerpt instead of locator-only manifest | `workers/fetch.py`, `RAW_POLICY.md` | local HTML fixture with nav/script/style/prompt injection text and external public_text cap tests | `excerpt.md` contains normalized body excerpt, hashes, provenance artifacts; no scripts/styles/full page dump; external `content.md` is capped | full third-party article committed by default |
| P11.3c PDF/arXiv metadata | Capture PDF/arXiv metadata, byte hash/length, and excerpt/blob manifest | `workers/fetch.py`, `RAW_POLICY.md` | local PDF bytes fixture; local PDF symlink/traversal tests; arXiv URL parser tests | packet records PDF metadata/artifact manifest and safe excerpt; no `.pdf` in packet dir; local PDFs must be safe lexical files under root | binary PDF bytes committed to raw packet dir or unsafe local PDF path read |
| P11.3d GitHub artifact split | Split GitHub blob/issue/PR/diff contracts and fetch safe excerpts where possible | `workers/fetch.py` | URL-shape tests, branch-with-slash tests, raw.githubusercontent tests, and fake fetcher blob/diff fixtures | artifacts distinguish `blob`, `issue`, `pull`, `diff`; blob/diff excerpts are bounded and public-safe; unpinned refs are marked mutable | one generic `github_artifact` blob hides issue/PR/diff semantics |
| P11.3e Digest request metadata | Preserve safe new fetch metadata for digest providers | `workers/digest.py` | request sanitizer tests for fetch/pdf/arXiv/GitHub metadata and unsafe redaction | safe content type, byte length, final URL, arXiv ID, repo, artifact type, number/ref/path reach `DigestModelRequest`; storage hints/local paths do not | richer fetch packets are invisible to digest providers or leak unsafe paths |
| P11.3f CLI/policy tests | Preserve ingest CLI and source packet invariants | `cli.py` if needed, `RAW_POLICY.md`, tests | P2/P11.3 tests | existing P2 behavior still passes; new V2 cases covered | source packet schema or digest job preconditions regress |

## Gemini Requirement

Required before unfreeze.

Reason: P11.3 changes untrusted external fetch handling, SSRF boundaries,
public/private leakage boundaries, digest-provider prompt metadata, and raw
source policy.

Acceptance:

- Save Gemini output under `.omx/artifacts/gemini-p11-3-*.md`.
- Summarize the artifact in `docs/package-reviews/P11_3_UNFREEZE.md`.
- Missing or rejected Gemini blocks P11.4.

## Fetch Core Contract

Add a bounded fetch helper:

- Schemes: `http`, `https`.
- Timeout: default 15 seconds.
- Max bytes: default 1 MiB for HTML/text, 5 MiB for PDF/blob metadata.
- Redirects: allow stdlib defaults only when each redirect target passes SSRF
  validation; record final URL.
- Headers: use a simple `User-Agent: knowledge-topology-fetch/1`.
- Decode text from declared charset or UTF-8 with replacement.
- Never execute scripts, HTML, shell, or provider commands from fetched content.
- Fetched content is untrusted input. It can feed excerpts and hashes only.

SSRF / local network policy:

- Reject `file:`, `ftp:`, `data:`, and every non-HTTP(S) scheme before fetch.
- Reject hostnames and IPs that resolve to localhost, loopback, unspecified,
  multicast, private RFC1918, IPv6 ULA/link-local, and cloud metadata ranges
  including `169.254.169.254`.
- Reject literal IPv6 loopback such as `::1`.
- Re-check the final URL after redirects; redirect-to-private/local is blocked.
- Do not validate DNS and then hand the original hostname to an opener that can
  resolve again. The production fetcher must bind the connection to a validated
  address, or use an equivalent connector contract where the resolver output and
  connection target are the same checked address.
- Tests must include a fake resolver/connector pair where validation resolves
  to a public address but the connector attempts a private address; the fetch
  must fail before content is accepted.
- Tests must cover `localhost`, `127.0.0.1`, `::1`, `10.0.0.1`,
  `172.16.0.1`, `192.168.0.1`, `169.254.169.254`, unsupported schemes, and a
  fake redirect to a blocked host.

Implementation seam:

- Fetch helpers accept an optional opener/fetcher callable for tests.
- Production CLI uses the default stdlib opener.
- Tests for GitHub raw/diff fetching and redirects use local fake fetchers so
  the suite never requires github.com, raw.githubusercontent.com, or arxiv.org.

Failure handling:

- 4xx/5xx, timeout, unsupported content type, decode failure, or oversize
  produces `content_status=blocked` or `partial` with a fetch_chain failure
  record and safe metadata.
- No Python traceback should reach packet artifacts.

## Article/html Contract

Default article/html behavior:

- `content_mode=excerpt_only`
- `content_status=partial` when excerpt is available, otherwise `blocked`
- write `excerpt.md` only, capped at 800 characters initially
- include artifacts:
  - `kind=html_excerpt`, `path=excerpt.md`, `hash_sha256`
  - `kind=fetch_metadata` with content type, final URL, status code, byte length
- strip scripts, styles, noscript, SVG, forms, comments, and tags
- normalize whitespace
- reject or ignore instruction-shaped HTML content as plain untrusted text; do
  not copy hidden/script content into excerpts

If caller explicitly chooses `content_mode=public_text`, require
`redistributable=yes` and still cap tracked external content to 8,000
characters unless the source is a local draft. P11.3 does not add copyright
classification. Acceptance tests must prove `redistributable!=yes` fails before
fetch/write and `redistributable=yes` writes bounded `content.md`, not a full
article/blob/diff dump.

## PDF/arXiv Contract

For PDF URLs or local PDF files:

- default `content_mode=excerpt_only`
- reject `content_mode=public_text` for PDF/arXiv in P11.3, even when
  `redistributable=yes`, because stdlib-only extraction cannot safely derive
  bounded textual public content
- record byte length and SHA-256 hash
- write `excerpt.md` containing a safe, bounded metadata/excerpt summary, not
  raw PDF bytes
- include `local_blob_ref` artifact when `content_mode=local_blob`, but only a
  hash/storage hint; no binary file in packet dir
- include `kind=pdf_metadata` artifact with URL/file metadata, byte length,
  hash, and content type when known

Local PDF safe-path rules:

- Local PDF paths must resolve lexically under the topology root.
- Every parent component and the final file must be real, not symlinks.
- Local PDF paths must not traverse through nested `.topology`.
- Unsafe local PDFs fail before packet directory creation.
- Tests cover outside-root path, traversal, final symlink, parent symlink, and
  nested `.topology` rejection.

For arXiv URLs:

- parse arXiv ID from `/abs/<id>` or `/pdf/<id>.pdf`
- canonicalize `/abs/<id>` as canonical URL when possible
- include `kind=arxiv_metadata` artifact with `arxiv_id`, `abs_url`, and
  `pdf_url`
- if fetched HTML/PDF is available, include bounded excerpt metadata as above

## GitHub Artifact Contract

Split GitHub artifact types:

- `blob`: `/owner/repo/blob/<ref>/<path>`
- `issue`: `/owner/repo/issues/<number>`
- `pull`: `/owner/repo/pull/<number>`
- `diff`: `/owner/repo/pull/<number>.diff`, `/pull/<number>/files`, or diff
  URL variants
- `commit`: `/owner/repo/commit/<sha>`
- `repo`: fallback repository URL

Parsing and mutability rules:

- Parse pull/issue/commit/diff routes before blob routes.
- Blob refs are ambiguous when branch names contain `/`; parse by known URL
  structure only when the ref is a 40-character commit SHA. Non-40-char blob
  refs are metadata-only in P11.3: preserve the visible first ref segment,
  record the remaining path conservatively, set `commit_sha=null`, and mark
  `mutable_ref=true` and `ambiguous_ref=true`; do not fetch an excerpt.
- Pinned 40-char blob refs may produce raw URL hints and fetched excerpts.
- Raw GitHub URLs (`raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>`) are
  recognized as blob artifacts. They are fetched only when `<ref>` is a
  40-character commit SHA; otherwise they are metadata-only with
  `mutable_ref=true` and `ambiguous_ref=true`.
- Pull `.diff` and `/pull/<number>/files` are classified as `diff` when the
  user intent is diff/file review; `/pull/<number>` without `.diff` is `pull`.
- Tests cover branch refs containing slashes, 40-char commit refs,
  `/pull/<n>.diff`, `/pull/<n>/files`, `/issues/<n>`, `/pull/<n>`,
  `/commit/<sha>`, repo fallback, and raw.githubusercontent.com. Tests must
  prove unpinned slash refs do not trigger network fetches.

Artifacts include:

- `kind=github_blob`, `github_issue`, `github_pull`, `github_diff`,
  `github_commit`, or `github_repo`
- `repo`, `artifact_type`, `ref`/`number`, `path`, `commit_sha` when pinned
- `canonical_api_hint` or `raw_url` only as locator metadata
- bounded `excerpt.md` for fetched blob/diff/text when public-safe

Public safety:

- Default GitHub content remains `excerpt_only`.
- Do not infer redistributable license from GitHub URL.
- Full blob text is tracked only if caller explicitly uses
  `content_mode=public_text` and `redistributable=yes`, and even then P11.3
  caps content to 8,000 characters to avoid accidental large dumps.

## Digest Provider Metadata Compatibility

Update the provider request sanitizer in `workers/digest.py` to pass safe
artifact metadata through:

- generic fetch: `content_type`, `status_code`, `final_url`, `byte_length`
- PDF: `byte_length`, `hash_sha256`, `content_type`
- arXiv: `arxiv_id`, `abs_url`, `pdf_url`
- GitHub: `repo`, `artifact_type`, `number`, `ref`, `path`, `commit_sha`,
  `mutable_ref`, `raw_url`

Still redact:

- local absolute paths
- `storage_hint`
- raw/local blob paths
- private/cache paths
- unknown artifact fields

Tests must prove safe metadata reaches `DigestModelRequest` and unsafe fields
do not.

## Acceptance Tests

Required tests:

- Existing P2 source packet/fetch tests still pass.
- Local HTTP article fixture writes a useful `excerpt.md` body excerpt and
  strips script/style/nav/form/comment text.
- Article 404/timeout-like failure produces safe blocked/partial packet and
  still enqueues digest when packet is usable.
- Article oversize response is bounded and does not write full content.
- External article/GitHub/diff `public_text` with `redistributable=yes` writes
  bounded `content.md` capped at 8,000 characters; `redistributable!=yes` fails
  before fetch/write.
- PDF/arXiv `public_text` is rejected before fetch/write.
- Local PDF bytes fixture records byte length/hash metadata, writes
  `excerpt.md`, and does not write `.pdf` bytes to packet dir.
- Unsafe local PDF paths fail before packet writes: outside root, traversal,
  final symlink, parent symlink, nested `.topology`.
- arXiv `/abs` and `/pdf` URLs produce arXiv metadata artifacts and canonical
  URL normalization.
- GitHub URL parsing distinguishes blob, issue, pull, diff, commit, repo.
- GitHub URL tests include branch refs with slashes, raw.githubusercontent.com,
  pull `.diff`, `/pull/<n>/files`, issue vs pull numbers, commit refs, and repo
  fallback.
- GitHub blob/diff fake fetcher fixture writes bounded excerpt and records split
  artifact kind without hitting the network.
- Digest provider request sanitizer exposes safe fetch/pdf/arXiv/GitHub
  metadata and redacts local paths/blob hints.
- `local_blob` mode records hash/storage hint only and keeps bytes out of Git.
- CLI ingest smoke still works for article/html, pdf/arXiv, and GitHub URL
  shapes.
- Malformed URLs, unsupported schemes, private/local network hosts, redirect to
  private/local host, and path traversal local inputs fail before writing.

## Stop Conditions

- Article/html still only stores a locator manifest with no body excerpt.
- PDF/arXiv still lacks metadata/hash/excerpt/blob manifest.
- GitHub artifacts remain a single generic kind without blob/issue/PR/diff
  distinction.
- Full third-party article/PDF/GitHub content is committed by default.
- Private/local network URLs can be fetched.
- Network-dependent tests are required for the suite to pass.
