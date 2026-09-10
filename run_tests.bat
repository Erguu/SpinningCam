@echo off
REM ============================================================================
REM  SpinningCam - run the headless test suite
REM
REM  Activates the "spinning_cam" conda env, then runs run_tests.py.
REM
REM  ACTIVATION IS THE WHOLE POINT OF THIS FILE. Calling the env's python.exe
REM  directly gives an MKL BLAS delay-load crash (exit 127, no traceback) in
REM  anything touching np.linalg.* or np.polyfit, and healthy code then reports
REM  as broken. run_tests.py refuses to run if that happens, but the easiest way
REM  to never meet it is to start here.
REM
REM  Any arguments are passed straight through:
REM      run_tests.bat              everything
REM      run_tests.bat -k point     only files matching "point"
REM      run_tests.bat --list       show what would run
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
python run_tests.py %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo(
    echo [Tests reported failures - see the list above and TEST_STATUS.md]
)
endlocal & exit /b %RC%
