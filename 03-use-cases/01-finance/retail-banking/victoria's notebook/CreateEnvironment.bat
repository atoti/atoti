@echo off

set ANACONDA_LOCAL_DIR="C:\ProgramData\Miniconda3"
set ENV_NAME="atoti-0.8.7"
set ATOTI_VERSION=0.8.7

if defined ANACONDA_DIR (goto anacondaCheckDone)
if exist %ANACONDA_LOCAL_DIR% (
	set ANACONDA_DIR=%ANACONDA_LOCAL_DIR%
	goto anacondaCheckDone
)

:anacondaCheckDone

call %ANACONDA_DIR%/Scripts/activate.bat %ANACONDA_DIR%
call conda env remove -n %ENV_NAME%
call conda create -y -n %ENV_NAME%
call conda activate %ENV_NAME%
call conda install -y atoti=%ATOTI_VERSION% atoti-jupyterlab3=%ATOTI_VERSION%

pause
