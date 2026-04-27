# Contributing to splunk-soar-connectors

Guidance for Claude Code when working on a pull request to any `splunk-soar-connectors` repository.

---

## Before Starting Any Work

Always sync with upstream first — never branch off a stale local main.

```bash
git remote add upstream https://github.com/splunk-soar-connectors/<repo>.git
git fetch upstream
git checkout -b <your-branch> upstream/main
```

Check what version upstream is currently at before deciding your target version:

```bash
grep '"app_version"' <appname>.json
```

---

## Pre-commit

Pre-commit is **required** and must pass before a PR can be merged. Install it once per machine, then activate it per repo:

```bash
pip install pre-commit
pre-commit install       # run inside the repo
pre-commit run --all-files   # verify everything passes before opening the PR
```

What it checks: ruff (lint + format), djlint, mdformat, semgrep, secret detection, JSON/YAML validity, conventional commit format, release notes, copyright headers, and Splunk's SOAR App Linter (which validates Python 3.13 compatibility and the `app.json` schema).

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/). The pre-commit hook enforces this.

```
<type>: <short description>

[optional body]
```

Common types: `feat`, `fix`, `docs`, `refactor`, `chore`, `style`, `test`

---

## Versioning and Release Notes

Splunk uses semver. Determine the correct next version by checking the latest tag or `app_version` in the app JSON on upstream `main`, then increment:
- `fix` / `chore` → patch bump (e.g. `2.10.1` → `2.10.2`)
- `feat` → minor bump (e.g. `2.10.1` → `2.11.0`)

Two places to update:
1. `"app_version"` field in `<appname>.json`
2. A new file at `release_notes/<version>.md` — bullet points describing the changes

Release notes format (one bullet per logical change):
```markdown
* Fixed <describe the bug> in the "<action name>" action
* Added <describe the feature>
```

---

## App JSON: Contributors List

Add your name to the `contributors` array in `<appname>.json` if it isn't there already:

```json
"contributors": [
    {
        "name": "Your Name"
    }
]
```

---

## Scope Rules (Critical)

Splunk will **not** accept PRs that violate these:

- **One app per PR.** Never touch more than one app repo's files.
- **One issue per branch.** If you have two fixes, open two PRs from two branches.
- **Do not re-implement work already merged upstream.** Always check upstream `main` before starting — your changes may already be there in a different form.

---

## Opening the Pull Request

Target branch: `main` on the upstream repo (not `next`, not a feature branch).

**Required:** Check **"Allow edits and access to secrets by maintainers"** on the PR creation page. This is explicitly called out by Splunk and they will ask for it if you miss it.

The PR must follow the template below. Delete sections that don't apply.

### PR Template

```markdown
### Features
<!-- Delete if no new features -->
- <describe each new action, parameter, or auth method>

### Bug Fixes
<!-- Delete if no bug fixes -->
- <describe what broke and how it was fixed>

### Manual Documentation

<details><summary>
Have you made any changes that should be documented in manual_readme_content.md?
</summary><br />

The following changes require documentation in `manual_readme_content.md`:
- New, updated, or removed REST handlers
- New, updated, or removed authentication methods (especially OAuth)
- Compatibility considerations (e.g. actions that can't run on cloud or automation broker)

</details>

- [ ] I have verified that manual documentation has been updated where appropriate

### Other information
<!-- Delete if unused -->
```

### When to update `manual_readme_content.md`

Update it if you changed any of the following:
- REST handler behavior
- Authentication methods (especially OAuth flows)
- Actions that have cloud vs. on-prem limitations

---

## Python Compatibility

All apps must support **Python 3.9 and 3.13**. The SOAR App Linter (run via pre-commit) validates this automatically. If you add or upgrade a dependency, verify it has wheels for both versions in `wheels/`.

---

## Checklist Before Pushing

- [ ] Branched off the latest `upstream/main` (not a stale local copy)
- [ ] `pre-commit run --all-files` passes with no errors
- [ ] `app_version` bumped correctly in `<appname>.json`
- [ ] `release_notes/<version>.md` created with accurate bullet points
- [ ] Your name added to `contributors` in `<appname>.json`
- [ ] PR targets `main` on the upstream repo
- [ ] "Allow edits and access to secrets by maintainers" will be checked on submission
- [ ] PR description follows the template and irrelevant sections are deleted
- [ ] Only one app touched, only one issue addressed
