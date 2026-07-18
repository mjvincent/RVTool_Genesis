# Contributing to RVTool Genesis

Thank you for contributing. This guide covers the conventions this project follows
so changes stay consistent and reviewable.

---

## Table of Contents

1. [Branch naming](#branch-naming)
2. [Commit messages](#commit-messages)
3. [Pull requests](#pull-requests)
4. [Tests](#tests)
5. [Documentation](#documentation)
6. [Code style](#code-style)
7. [Remotes](#remotes)

---

## Branch naming

```
<type>/<short-description>
```

| Type | When to use |
|---|---|
| `feat/` | New user-facing feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `chore/` | Tooling, dependencies, hygiene |
| `refactor/` | Internal restructure with no behaviour change |
| `test/` | Test-only changes |

Examples:
```
feat/powervs-pricing-template-merge
fix/disk-clamping-powervs-bypass
docs/ux-polish-plan
```

---

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>): <short summary in present tense>

<optional body — what and why, not how>
```

- **Summary line:** 72 characters max, lowercase after the colon, no period.
- **Body:** Wrap at 100 characters. Explain *what* changed and *why*; the diff
  shows *how*.
- **Breaking changes:** Add `BREAKING CHANGE:` in the footer.

```
fix(ai-normalizer): bypass VPC disk clamping for PowerVS records

PowerVS storage has no 100 GB floor or 250 GB ceiling — the IBM Price
Estimator accepts any disk size the customer provides. x86 behaviour unchanged.
```

Allowed types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `ci`.

---

## Pull requests

1. **Keep PRs focused** — one logical change per PR. A PR that fixes a bug and
   adds an unrelated feature is harder to review and harder to revert.

2. **Title** — Use the same Conventional Commits format as the commit message.

3. **Description must include:**
   - **What** — one-paragraph summary of the change.
   - **Why** — the problem being solved or the use case being addressed.
   - **Testing** — what was run to verify the change (test names, manual steps).
   - **Documentation** — confirm `README.md`, `CHANGELOG.md`, and/or
     `docs/USER_GUIDE.md` are updated if the change is user-facing.

4. **Self-review** — Read the diff yourself before requesting review. Remove any
   debugging artifacts, `console.log` statements, or commented-out code.

5. **No force-pushes to `main`** after another person has branched from it.

---

## Tests

All tests run inside the Docker container:

```bash
# Full suite
make test

# Specific file
docker compose exec api python3 -m pytest /tests/test_pricing_template_filler.py -v

# With coverage
docker compose exec api python3 -m pytest /tests/ --cov=services --cov-report=term-missing
```

### Requirements

- **New features** must include tests covering the happy path and at least one
  error/edge-case path.
- **Bug fixes** must include a regression test that would have caught the bug.
- **All existing tests must pass** before a PR is mergeable. The one pre-existing
  failure in `test_pipeline.py::test_generator_and_validator` is a known issue
  (extra RVTools sheets in the validator); do not add new failures.

### Test file conventions

| What you're testing | File |
|---|---|
| `services/pricing_template_filler` | `tests/test_pricing_template_filler.py` |
| `services/ai_normalizer` | `tests/test_normalizer_disk_clamping.py` (or add new file) |
| VPC profile selection | `tests/test_vpc_profile.py` |
| End-to-end pipeline | `tests/test_pipeline.py` |

New test files follow the `test_<module_name>.py` pattern and go in `tests/`.

---

## Documentation

User-facing changes require documentation updates in the **same PR**:

| Change type | Files to update |
|---|---|
| New feature or behaviour change | `README.md` (Changelog section + relevant reference section), `docs/USER_GUIDE.md` (relevant step), `CHANGELOG.md` |
| Bug fix | `CHANGELOG.md` |
| New API endpoint | `README.md` (Architecture section if the route tree changes) |
| Breaking change | All of the above + prominent note in PR description |

### CHANGELOG.md format

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Add entries under `## [Unreleased]` — they are moved to a versioned section on release.

```markdown
## [Unreleased]

### Fixed
- **Short title** — One-sentence description of what changed and why it matters.
  (`path/to/file.py` — function name if relevant)
```

---

## Code style

### Python (backend)

- Python 3.12+. Follow existing patterns — no new dependencies without discussion.
- Type hints on all public functions.
- `logger.info/warning/exception` for observability; no bare `print()`.
- Keep functions focused. If a function is doing two things, consider splitting it.

### TypeScript / React (frontend)

- Follow the existing Carbon Design System component usage patterns.
- No `as any` casts unless genuinely unavoidable — add a comment explaining why.
- State variables follow the `[noun, setNoun]` convention.
- No inline event handlers in JSX that do more than call a named function.

### General

- Minimal changes — only touch lines directly related to the task.
- No speculative refactors in a feature or fix PR.
- Delete commented-out code before merging.

---

## Remotes

This repository has two remotes. **Always push to both:**

```bash
git push origin main
git push ibm main
```

| Remote | URL |
|---|---|
| `origin` | `github.com/mjvincent/RVTool_Genesis` |
| `ibm` | `github.ibm.com/jonesmi/RVTool_Genesis` |
