@echo off
setlocal enabledelayedexpansion


set loop_count=3
set kafka_host=192.168.24.1

for /l %%i in (1,1,%loop_count%) do (
    
    set "driver_id=driver_100%%i"
    
    echo !driver_id!

    start "Driver_%%i" cmd /k "python Driver\EV_Driver.py !kafka_host!:9092 !driver_id!"

    timeout /t 1 >nul
)

echo.
