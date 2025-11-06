@echo off

chcp 65001 >nul
title EV Charging System

echo only available in production environment(.env set debug_mode to false)
echo [1/4] (EV Central)...
start "EV Central" cmd /k "python Core\Central\EV_Central.py 5002 localhost:9092" 
timeout /t 3 /nobreak >nul

echo [2/4] (Charging Point Engine)...
start "CP Engine" cmd /k "python Charging_point\Engine\EV_CP_E.py localhost:9092 --debug_port 5003"
timeout /t 2 /nobreak >nul

echo [3/4] (Charging Point Monitor)...
start "CP Monitor" cmd /k "python Charging_point\Monitor\EC_CP_M.py localhost:5003 localhost:5002 cp_001"
timeout /t 2 /nobreak >nul

echo [4/4] (EV Driver)...
start "EV Driver" cmd /k "python Driver\EV_Driver.py localhost:9092 driver_001"
timeout /t 1 /nobreak >nul

