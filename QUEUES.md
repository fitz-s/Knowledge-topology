# Queue Contract

Active worker queues use a spool directory model, not shared JSONL queue files.
This avoids concurrent append conflicts, half-line writes, noisy Git merges,
and inconsistent filesystem lock semantics.

V1 queues are single-filesystem queues, not a distributed broker. Cross-host
workers sharing a network mount are out of scope until a real broker exists.
Lease expiry relies on local clock discipline.

## Spool Layout

```text
ops/queue/
  ingest/{pending,leased,done,failed}
  digest/{pending,leased,done,failed}
  reconcile/{pending,leased,done,failed}
  apply/{pending,leased,done,failed}
  compile/{pending,leased,done,failed}
  audit/{pending,leased,done,failed}
  writeback/{pending,leased,done,failed}
```

`ops/queue/**` is local-only runtime state. Durable semantic history is recorded
under `ops/events/<yyyy>/<mm>/<dd>/evt_<ulid>.json`.

## Job Files

Each job is one JSON file named with an immutable opaque ID:

```text
job_<ulid>.json
```

Minimum fields:

- `id`
- `kind`
- `created_at`
- `created_by`
- `subject_repo_id`
- `subject_head_sha`
- `base_canonical_rev`
- `payload`
- `attempts`
- `lease_owner`
- `leased_at`
- `lease_expires_at`

## State Transitions

Workers move files atomically:

1. write complete job to a temp path in the target filesystem
2. rename into `pending/`
3. claim by renaming from `pending/` to `leased/`
4. finish by renaming to `done/` or `failed/`

Workers must never update a job in place across state directories. If metadata
changes, write a replacement file and atomically rename.

## Lease Recovery

Each lease has `lease_owner`, `leased_at`, and `lease_expires_at`. `topology
doctor queues` may requeue expired leases after writing an event.

## Audit

Tracked durable audit records capture semantic events only. Queue churn such as
create, lease, complete, fail, and requeue belongs in local-only runtime logs
unless a worker promotes it to a semantic event. Events are not the active
queue.

Poisoned jobs move to `failed/` and require explicit requeue. Workers should not
auto-retry jobs that fail validation or safety checks.
