@echo off
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0run_task04.py" %*
) else (
    python "%~dp0run_task04.py" %*
)
exit /b %errorlevel%
