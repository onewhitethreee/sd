@echo off
setlocal enabledelayedexpansion


set loop_count=5
set host_ip=localhost

for /l %%i in (1,1,%loop_count%) do (
    
    set "driver_id=driver_00%%i"
    
    echo !driver_id!

    start "Driver_%%i" cmd /k "python Driver\EV_Driver.py !host_ip!:9092 !driver_id!"

    timeout /t 1 >nul
)

echo.
