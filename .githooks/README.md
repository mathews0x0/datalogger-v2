# RaceSense Git hooks

The tracked pre-commit hook increments `server/VERSION` once for every commit
and stages the updated value. Server and P4 firmware render that number as the
shared `Mark N` release identity.

Enable the tracked hooks in a new clone with:

```bash
git config core.hooksPath .githooks
```

If `server/VERSION` was changed explicitly, the hook preserves and stages that
value instead of incrementing it again. This supports deliberate jumps such as
Mark 180 to Mark 199 and prevents a failed commit retry from double-incrementing.
