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
| audio/video transcript | `excerpt_only` plus optional `local_blob` | Defer full transcript tracking until rights are clear. |
| social thread | `excerpt_only` | Preserve URL and limited quoted evidence. |

## Excerpt Rules

Until a stricter copyright-aware checker exists:

- keep excerpts short
- preserve provenance and location
- avoid storing complete third-party articles, papers, or transcripts
- prefer claim/evidence maps over copied source text

## Fetch Failure

Fetch failure should produce `content_status: partial` when usable metadata or
safe excerpts exist. Escalate only for canonical ambiguity, authentication or
paywall blocks, catastrophic fetch failure, or unclear legal/trust boundaries.
