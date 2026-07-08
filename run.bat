@echo off
REM ============================================================================
REM  SpinningCam - launcher (run from source)
REM
REM  Activates the "spinning_cam" conda env and starts the app.
REM  Run setup_env.bat ONCE first if the env does not exist yet.
REM ============================================================================
setlocal EnableDelayedExpansion

set "ENV_NAME=spinning_cam"
set "PROJECT_DIR=%~dp0"

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
            set "CONDA_BAT=%%~D\Scripts\activate.bat"
            goto :found_conda
        )
    )
)
:found_conda

if not defined CONDA_BAT (
    echo [ERROR] Could not find conda. Install Miniconda and run setup_env.bat first.
    pause
    exit /b 1
)

call "!CONDA_BAT!" "%ENV_NAME%"
if errorlevel 1 (
    echo [ERROR] Could not activate env "%ENV_NAME%". Run setup_env.bat first.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"
python main_tk.py
if errorlevel 1 (
    echo(
    echo [The program exited with an error - see messages above.]
    pause
)
endlocal
