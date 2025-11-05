@echo off
setlocal enabledelayedexpansion

set /a loop_count=3
set /a start_port=5003
set start_id=cp_001

for /l %%i in (1,1,%loop_count%) do (
    set /a current_port=!start_port! + %%i - 1
    set current_id=!start_id:~0,-1!%%i
    
    start "EV_CP_E_%%i" cmd /k "python Charging_point\Engine\EV_CP_E.py localhost:9092 --debug_port !current_port!"
    timeout /t 1 >nul
    start "EC_CP_M_%%i" cmd /k "python Charging_point\Monitor\EC_CP_M.py localhost:!current_port! localhost:5002 !current_id!"
)
