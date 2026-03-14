# TODO / Review Notes

- [x] Validate target names are unique in config to avoid metric label collisions.
- [x] Parse `mtr --json` output with strict JSON parser (`json.loads`) instead of YAML parser.
- [x] Make stale hop metric removal resilient (ignore missing series during `remove`).
- [x] Clean GitHub workflow duplication so image build/push job is defined only once.
