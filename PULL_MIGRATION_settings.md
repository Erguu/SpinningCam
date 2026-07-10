# One-Time Step After the "settings.json" Change

**Applies to:** anyone who **already had a clone** of SpinningCam before commit
`b13e502` (2026-07-10). Fresh clones need nothing — this is only for existing
copies.

## Why
`settings.json` used to be tracked in git, but the app rewrites it constantly
(camera, sidebar width, language, params, license/admin flags). That made every
`git pull` collide with your local changes. From commit `b13e502` on,
`settings.json` is **no longer tracked** — the app rebuilds it from built-in
defaults if it is missing.

Because your existing clone still has a *tracked, locally-modified*
`settings.json`, the **first** pull after this change will hit the collision one
last time (git wants to remove the file from tracking, but you have edits). Do
the steps below once to get past it cleanly.

## Steps (Windows PowerShell / CMD)

Run these in your SpinningCam folder, **before** pulling:

```powershell
copy settings.json settings.mine.json      # 1. back up your current settings
git checkout -- settings.json              # 2. drop local edits so the pull is clean
git pull                                    # 3. pull — settings.json leaves git tracking
copy settings.mine.json settings.json      # 4. restore your settings (now git-ignored)
```

That's it. After this, `settings.json` is ignored by git and your pulls are
clean forever.

## Steps (macOS / Linux)

```bash
cp settings.json settings.mine.json
git checkout -- settings.json
git pull
cp settings.mine.json settings.json
```

## Don't care about keeping your current settings?
Skip the backup — just run `git checkout -- settings.json` then `git pull`. The
app recreates `settings.json` from defaults the next time you launch it.

## Troubleshooting
- **`git pull` still says settings.json would be overwritten:** you skipped step
  2. Run `git checkout -- settings.json` (or `git stash`), then `git pull` again.
- **Program looks "reset" after pulling:** your restore (step 4) didn't run, so
  the app made a fresh `settings.json`. Copy your `settings.mine.json` back over
  it, or just re-set your preferences once.

## Note (not fixed yet)
`tools.json` and the machine profiles under `machines/` can still collide **if**
you edit tools or re-calibrate on your clone. That cleanup is planned for a later
session (see the Phase 2 note in `LAST_CHANGES.md`).
