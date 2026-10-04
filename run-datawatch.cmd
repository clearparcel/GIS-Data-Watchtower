@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv-watchtower\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Watchtower virtual environment is missing: %PYTHON% 1>&2
  exit /b 2
)
set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
"%PYTHON%" -m clearparcel.datawatch --config "%ROOT%config\example_sources.json" check > "%ROOT%datawatch\latest.txt" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" exit /b %RC%
exit /b 0
