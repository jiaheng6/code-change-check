@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "TOOL_SCRIPT=%SCRIPT_DIR%scripts\code_change_check.py"
set "PYTHON_CMD="

where python >nul 2>nul
if not errorlevel 1 (
    python --version >nul 2>nul
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 --version >nul 2>nul
        py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )
)

if not defined PYTHON_CMD (
    echo 未检测到 Python 3.10+。
    echo 请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/
    echo 安装后请确认 python 或 py 命令可用。
    exit /b 1
)

%PYTHON_CMD% "%TOOL_SCRIPT%" %*
exit /b %ERRORLEVEL%
