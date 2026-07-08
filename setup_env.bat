@echo off
REM ============================================================================
REM  SpinningCam - one-time environment setup (run from source, no exe build)
REM
REM  PREREQUISITE: Miniconda (or Anaconda) must already be installed.
REM      Download: https://docs.conda.io/en/latest/miniconda.html
REM
REM  This script:
REM    1. Locates conda (PATH or common install folders)
REM    2. Creates the "spinning_cam" conda env with Python 3.11
REM    3. Installs pythonocc-core (conda-only, provides the OCC / STEP import)
REM    4. pip installs everything in requirements.txt
REM
REM  Run it ONCE. After it finishes, use run.bat to start the program.
REM ============================================================================
setlocal EnableDelayedExpansion

set "ENV_NAME=spinning_cam"
set "PY_VERSION=3.11"
set "PROJECT_DIR=%~dp0"

echo(
echo === SpinningCam environment setup ===
echo(

REM --- Locate conda --------------------------------------------------------
set "CONDA_BAT="
where conda >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%i in ('conda info --base 2^>nul') do set "CONDA_BASE=%%i"
    if defined CONDA_BASE set "CONDA_BAT=!CONDA_BASE!\Scripts\activate.bat"
)

if not defined CONDA_BAT (
    for %%D in (
        "%USERPROFILE%\miniconda3"
        "%USERPROFILE%\anaconda3"
        "%USERPROFILE%\AppData\Local\miniconda3"
        "%USERPROFILE%\AppData\Local\Continuum\anaconda3"
        "%ProgramData%\miniconda3"
        "%ProgramData%\Anaconda3"
        "C:\Users\PC\anaconda3"
    ) do (
        if exist "%%~D\Scripts\activate.bat" (
            set "CONDA_BASE=%%~D"
            set "CONDA_BAT=%%~D\Scripts\activate.bat"
            goto :found_conda
        )
    )
)
:found_conda

if not defined CONDA_BAT (
    echo [ERROR] Could not find conda.
    echo(
    echo   Please install Miniconda first:
    echo       https://docs.conda.io/en/latest/miniconda.html
    echo(
    echo   Then re-run this script.
    echo(
    pause
    exit /b 1
)

echo Found conda at: !CONDA_BASE!
call "!CONDA_BAT!"

REM --- Create the env (skip if it already exists) --------------------------
call conda env list | findstr /r /c:"^%ENV_NAME% " /c:"\\%ENV_NAME%$" >nul 2>nul
if not errorlevel 1 (
    echo Env "%ENV_NAME%" already exists - skipping creation.
) else (
    echo Creating env "%ENV_NAME%" with Python %PY_VERSION% ...
    call conda create -y -n "%ENV_NAME%" python=%PY_VERSION%
    if errorlevel 1 (
        echo [ERROR] Failed to create the conda env.
        pause
        exit /b 1
    )
)

REM --- Activate it ---------------------------------------------------------
call conda activate "%ENV_NAME%"
if errorlevel 1 (
    echo [ERROR] Failed to activate "%ENV_NAME%".
    pause
    exit /b 1
)

REM --- Conda-only dependency ----------------------------------------------
echo(
echo Installing pythonocc-core (conda-forge, STEP import / geometry) ...
call conda install -y -c conda-forge pythonocc-core
if errorlevel 1 (
    echo [ERROR] Failed to install pythonocc-core.
    pause
    exit /b 1
)

REM --- Pip dependencies ----------------------------------------------------
echo(
echo Installing pip dependencies from requirements.txt ...
python -m pip install --upgrade pip
python -m pip install -r "%PROJECT_DIR%requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo(
echo === Setup complete ===
echo You can now start the program by running:  run.bat
echo(
pause
endlocal
