# Hybrid execution profiles

Some public GIS providers accept requests from local/residential or organizational networks but reject cloud-datacenter egress. Watchtower does not attempt to bypass those controls.

A source may optionally declare:

```json
"execution_profiles": ["cloud"]
```

or:

```json
"execution_profiles": ["local"]
```

Sources without this field run in every profile. `"any"` also runs in every profile.

Use `watchtower check --execution-profile local` for a local worker. Cloud jobs default to the `cloud` profile and can override it with `WATCHTOWER_EXECUTION_PROFILE`.

This is intended for respectful hybrid deployments, not for circumventing provider blocks. If a provider rejects cloud traffic, mark that source local-only or remove it.
