============================================================================
  SpinningCam - Setup & Run (from source, no exe needed)
============================================================================

Run these THREE steps in order. Steps 1 and 2 are done ONCE per computer.
Step 3 is how you start the program every day.


----------------------------------------------------------------------------
  STEP 1 - Install Miniconda   (one time)
----------------------------------------------------------------------------
  Double-click:   Miniconda3-latest-Windows-x86_64.exe

  Click through the installer with the DEFAULT options.
  ("Just Me" is fine. You do NOT need to check any PATH options.)

  When it finishes, continue to Step 2.


----------------------------------------------------------------------------
  STEP 2 - Install the program's dependencies   (one time)
----------------------------------------------------------------------------
  Double-click:   setup_env.bat

  This creates the Python environment and downloads every library the
  program needs. It takes a few minutes and needs an internet connection.

  Wait until you see:  "=== Setup complete ==="
  Then close the window and continue to Step 3.

  (If it says it cannot find conda, restart the computer once and try
   again - this lets Windows finish registering Miniconda.)


----------------------------------------------------------------------------
  STEP 3 - Start the program   (every time)
----------------------------------------------------------------------------
  Double-click:   run.bat

  That's it. From now on, only Step 3 is needed to launch the program.


----------------------------------------------------------------------------
  Quick reference
----------------------------------------------------------------------------
  Miniconda3-latest-Windows-x86_64.exe  ->  install once (Step 1)
  setup_env.bat                         ->  run once     (Step 2)
  run.bat                               ->  run to start (Step 3)

  Trouble? Make sure Steps 1 and 2 both finished without errors before
  running run.bat.
============================================================================
