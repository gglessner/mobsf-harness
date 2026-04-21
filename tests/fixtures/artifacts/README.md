# E2E fixtures

Drop a small open-source APK or IPA here and create `apps.e2e.yaml` pointing
at it with `source: drop_dir` and a `drop_path` of this directory structured
as `<version>-<code>/artifact.apk`. Then:

```bash
MOBSF_HARNESS_E2E=1 \
MOBSF_API_KEY=... \
ANTHROPIC_API_KEY=... \
pytest -m e2e tests/e2e/
```
