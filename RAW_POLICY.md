# Raw Source Policy

Raw source packets balance translation fidelity with public repository safety.

## Content Modes

The `content_mode` field controls what source content may be tracked.

- `public_text`: normalized text is safe to track.
- `excerpt_only`: track metadata, limited excerpts, and digest references.
- `local_blob`: track metadata, hashes, fetch manifests, and storage hints;
  store full content outside Git.

## Redistribution

Every source packet declares `redistributable`:

- `yes`: content can be tracked when size and sensitivity allow.
- `no`: full content must not be tracked.
- `unknown`: default to `excerpt_only` or `local_blob`.

## Source-Type Defaults

| Source Type | Default Mode | Notes |
| --- | --- | --- |
| local draft | `public_text` or `excerpt_only` | Use `excerpt_only` if secrets or private content may exist. |
| GitHub artifact | `public_text` for public permissive source, otherwise `excerpt_only` | Pin commit SHA or artifact ID. |
| article/html | `excerpt_only` | Store canonical URL, fetch manifest, and limited excerpts. |
| PDF/arXiv | `excerpt_only` plus optional `local_blob` | Do not track full PDFs by default. |
| video platform URL | `excerpt_only` | Store locator, capture plan, and later operator-provided transcript/key-frame/audio artifacts. Do not assume a direct media download. |
| audio/video transcript | `excerpt_only` plus optional `local_blob` | Defer full transcript tracking until rights are clear. |
| social thread | `excerpt_only` | Preserve URL and limited quoted evidence. |

## Excerpt Rules

Until a stricter copyright-aware checker exists:

- keep excerpts short
- preserve provenance and location
- avoid storing complete third-party articles, papers, or transcripts
- prefer claim/evidence maps over copied source text
- P11.3 caps tracked external `public_text` bodies at 8,000 characters even
  when `redistributable=yes`
- PDF/arXiv `public_text` is rejected in P11.3; store metadata/excerpt and
  optional local-only blob references instead
- video platform URLs are locator-only by default; tracked packets may include
  an operator-authored capture brief but not full media bytes or complete
  third-party transcripts unless rights are clear
- downloaded platform videos can be attached as local-only blob evidence with
  `topology video attach-artifact`; tracked packets store hashes, byte lengths,
  and storage hints only

## External Fetch Safety

P11.3 fetches are bounded and public-safe:

- reject local/private/metadata network targets before fetch
- re-check redirect targets
- bind production connections to validated public addresses or an equivalent
  resolver/connector contract
- keep network tests deterministic through local fixtures or injected fetchers
- do not infer redistribution rights from a URL, including GitHub URLs

## Fetch Failure

Fetch failure should produce `content_status: partial` when usable metadata or
safe excerpts exist. Escalate only for canonical ambiguity, authentication or
paywall blocks, catastrophic fetch failure, or unclear legal/trust boundaries.
