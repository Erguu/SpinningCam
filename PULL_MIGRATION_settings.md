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

## Easiest: run the script (Windows)

Put **`migrate_before_pull.bat`** in your SpinningCam folder and double-click it.
It backs up your `settings.json`, `tools.json`, and machine profiles to a
timestamped folder, resets the tracked copies, runs `git pull`, then restores your
files (now git-ignored, so pulls stay clean). Your originals are always backed up
first, so it is safe.

> You need the `.bat` **before** you can pull it, so grab it from whoever sent you
> the update (email / USB / download) and drop it in the folder — it runs the pull
> for you.

Prefer to do it by hand? Use the manual steps below instead.

## Manual steps (Windows PowerShell / CMD)

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

## Also applies to tools.json and machine profiles (Phase 2)

The same untrack happened to `tools.json` and the per-machine files under
`machines/` (they collide once you edit a tool or re-calibrate). If your existing
clone has local edits to any of these, do the same one-time dance for them before
pulling:

```powershell
copy tools.json tools.mine.json
git checkout -- tools.json
copy machines\ID111-1.json machines\ID111-1.mine.json   # repeat for each machine you edited
git checkout -- machines\ID111-1.json
git pull
copy tools.mine.json tools.json
copy machines\ID111-1.mine.json machines\ID111-1.json
```

After the pull, the app ships tracked **seeds** (`tools.default.json`,
`machines/<id>.default.json`) and recreates the live file from its seed on first
launch if it is missing — so a fresh clone just works, and your later edits stay
local and never collide again.
