# services/

Python services and agents live here, one uv workspace member per directory. Created on D-Day
(hackathon rule: no product code before the event):

```bash
uv init --package services/<name>     # adds itself to the uv workspace
uv add --package <name> <dependency>
```

Put tests in `services/<name>/tests/` and add `services` to `testpaths` in the root
`pyproject.toml`.
