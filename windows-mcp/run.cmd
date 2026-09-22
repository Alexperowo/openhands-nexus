@echo off
setlocal
set "PY_EXE=C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe"
if exist "%PY_EXE%" (
    "%PY_EXE%" "%~dp0server.py" %*
) else (
    python "%~dp0server.py" %*
)
