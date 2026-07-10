@echo off
REM ============================================================================
REM  SpinningCam - one-time pull migration
REM ----------------------------------------------------------------------------
REM  Some files the app rewrites at runtime (settings.json, tools.json, and the
REM  machine profiles under machines\) used to be tracked in git. They are now
REM  UNTRACKED, so the FIRST pull after this change collides with your local
REM  edits. This script does the safe dance ONCE:
REM     1) back up your local files (timestamped, nothing is lost)
REM     2) reset the tracked copies so the pull is clean
REM     3) git pull
REM     4) restore your files (now git-ignored -> pulls are clean forever)
REM
REM  SAFE: your originals are copied to a backup folder before anything changes.
REM  Run it from your SpinningCam folder (the one with SpinningCam.exe / main.py).
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   SpinningCam - one-time pull migration
echo ============================================================
echo.

REM --- must be inside a git repository ---------------------------------------
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo ERROR: this folder is not a git repository.
    echo Put this file in your SpinningCam folder and run it there.
    echo.
    pause
    exit /b 1
)

REM --- TIP: save any program you care about as a .ssp first ------------------
echo IMPORTANT: your ACTIVE program lives in settings.json. If you have unsaved
echo work open in the app, use "Save Project" (.ssp) BEFORE continuing.
echo.
set /p GO="Type Y and press Enter to continue (anything else cancels): "
if /i not "%GO%"=="Y" (
    echo Cancelled. Nothing was changed.
    pause
    exit /b 0
)

REM --- timestamped backup folder --------------------------------------------
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
set "BK=migration_backup_%STAMP%"
mkdir "%BK%" >nul 2>&1
mkdir "%BK%\machines" >nul 2>&1
echo.
echo Backing up your local files to: %BK%\
call :backup "settings.json" "%BK%\settings.json"
call :backup "tools.json"    "%BK%\tools.json"
for %%F in (machines\*.json) do call :backup "%%F" "%BK%\%%F"

echo.
echo Resetting tracked copies so the pull is clean...
call :reset "settings.json"
call :reset "tools.json"
for %%F in (machines\*.json) do call :reset "%%F"

echo.
echo Pulling the latest version...
git pull
if errorlevel 1 (
    echo.
    echo ------------------------------------------------------------
    echo  PULL FAILED. Nothing of yours was lost - your backup is in:
    echo     %BK%\
    echo  Fix the error above, or ask support, then re-run this file.
    echo ------------------------------------------------------------
    pause
    exit /b 1
)

echo.
echo Restoring your local files...
call :restore "%BK%\settings.json" "settings.json"
call :restore "%BK%\tools.json"    "tools.json"
for %%F in ("%BK%\machines\*.json") do call :restore "%%F" "machines\%%~nxF"

echo.
echo ============================================================
echo   DONE. Pull is complete and your settings/tools/calibration
echo   are restored. Future pulls will NOT collide anymore.
echo   Backup kept in: %BK%\  (delete it once you're happy.)
echo ============================================================
echo.
pause
exit /b 0

REM ---------------------------------------------------------------------------
:backup
REM %~1 = source file, %~2 = destination in backup folder
if exist "%~1" (
    copy /y "%~1" "%~2" >nul
    echo   backed up  %~1
)
exit /b 0

:reset
REM %~1 = tracked file to reset to the repo version (ignore if not tracked)
git checkout -- "%~1" >nul 2>&1
exit /b 0

:restore
REM %~1 = backup source, %~2 = live destination
if exist "%~1" (
    if not exist "%~dp2" mkdir "%~dp2" >nul 2>&1
    copy /y "%~1" "%~2" >nul
    if errorlevel 1 (
        echo   WARNING: could not restore %~2 - your copy is safe in the backup folder
    ) else (
        echo   restored   %~2
    )
)
exit /b 0
