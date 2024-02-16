@echo off

set ANACONDA_LOCAL_DIR="C:\ProgramData\Miniconda3"
set ENV_NAME="atoti-0.8.7"

if defined ANACONDA_DIR (goto anacondaCheckDone)
if exist %ANACONDA_LOCAL_DIR% (
	set ANACONDA_DIR=%ANACONDA_LOCAL_DIR%
	goto anacondaCheckDone
)

:anacondaCheckDone

call %ANACONDA_DIR%/Scripts/activate.bat %ANACONDA_DIR%
call activate %ENV_NAME%
call jupyter lab

pause
