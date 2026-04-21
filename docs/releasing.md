# Releasing

Umbra follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and publishes to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC — no API tokens anywhere).

## One-time PyPI setup (maintainer)

1. Register the project on PyPI: https://pypi.org/manage/account/publishing/
   - Owner: `jimnoneill`
   - Project name: `obsidian-umbra`
   - Workflow: `publish.yml`
   - Environment: `pypi`
2. Same for TestPyPI: https://test.pypi.org/manage/account/publishing/
   - Environment: `testpypi`
3. In the GitHub repo → Settings → Environments, create two environments:
   - `pypi`
   - `testpypi`
   (No secrets needed — trusted publishing uses OIDC identity.)

## Cutting a release

1. Bump the version in `src/umbra/__init__.py`:
   ```python
   __version__ = "0.2.0"
   ```
2. Move unreleased entries in `CHANGELOG.md` under a new `[0.2.0]` heading
   with today's date. Update the compare links at the bottom.
3. Commit:
   ```bash
   git add src/umbra/__init__.py CHANGELOG.md
   git commit -m "Release 0.2.0"
   git push
   ```
4. Tag + create GitHub release (triggers the publish workflow):
   ```bash
   gh release create v0.2.0 \
     --title "0.2.0" \
     --notes-from-tag \
     --latest
   ```
   Or via the web UI: https://github.com/jimnoneill/obsidian-umbra/releases/new

5. Watch the workflow: https://github.com/jimnoneill/obsidian-umbra/actions
   - `build` job produces sdist + wheel and verifies the version matches
     the tag.
   - `publish-pypi` job uploads to PyPI via OIDC.

## Testing a release candidate

Use the manual workflow dispatch to push to TestPyPI without tagging:

```bash
gh workflow run publish.yml -f target=testpypi
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    obsidian-umbra==0.2.0rc1
```

## Version bumping rules

- **Patch** (`0.1.0` → `0.1.1`): bug fixes, doc updates, internal refactors.
- **Minor** (`0.1.0` → `0.2.0`): new phases, new config keys with defaults,
  new CLI flags, new supported model families.
- **Major** (`0.1.0` → `1.0.0`): breaking config changes, removed phases,
  renamed markers (invalidates user's vault state).
