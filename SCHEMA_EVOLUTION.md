# Schema Evolution

Schemas will change. Evolution must preserve old records and make migrations
testable.

## Version Fields

Every durable JSON record eventually includes:

- `schema_version`
- `id`
- `created_at`
- `updated_at`

Version fields do not replace opaque IDs. IDs remain stable across schema
migrations.

## Compatibility Rule

Readers should support the current schema and the previous major version until
a migration has been run and verified.

## Migration Rule

Migrations must be:

- deterministic
- idempotent
- fixture-backed
- non-destructive by default
- explicit about fields that cannot be inferred

If a field cannot be migrated safely, the record becomes contested or requires
an escalation card.

## Fixture Rule

Every schema change adds:

- at least one old-version fixture
- expected migrated output or expected validation failure
- a note explaining whether the migration is automatic or human-gated

## Registry and Page Parity

Schema changes touching canonical nodes, claims, edges, aliases, or file refs
must update both page and registry validation expectations.
