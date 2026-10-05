@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv-watchtower\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Watchtower virtual environment is missing: %PYTHON% 1>&2
  exit /b 2
)
set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
if not exist "%ROOT%datawatch" mkdir "%ROOT%datawatch"
if defined CLEARPARCEL_WATCHTOWER_CONFIG (
  set "CONFIG=%CLEARPARCEL_WATCHTOWER_CONFIG%"
) else (
  set "CONFIG=%ROOT%config\example_sources.json"
)
"%PYTHON%" -m clearparcel.datawatch --config "%CONFIG%" check > "%ROOT%datawatch\latest.txt" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" exit /b %RC%
exit /b 0
