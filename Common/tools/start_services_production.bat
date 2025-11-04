@echo off
chcp 65001 >nul
title EV Charging System - 服务启动器

echo ============================================================
echo          EV 充电系统 - 快速启动脚本
echo ============================================================
echo.

echo [1/4] 启动中央系统 (EV Central)...
start "EV Central" cmd /k "python Core\Central\EV_Central.py 5002 localhost:9092" 
timeout /t 3 /nobreak >nul

echo [2/4] 启动充电桩引擎 (Charging Point Engine)...
echo          注意：Engine的CP_ID由Monitor提供
start "CP Engine" cmd /k "python Charging_point\Engine\EV_CP_E.py localhost:9092 --debug_port 5003"
timeout /t 2 /nobreak >nul

echo [3/4] 启动充电桩监控 (Charging Point Monitor)...
echo          Monitor负责管理充电桩ID
start "CP Monitor" cmd /k "python Charging_point\Monitor\EC_CP_M.py localhost:5003 localhost:5002 cp_001"
timeout /t 2 /nobreak >nul

echo [4/4] 启动驱动客户端 (EV Driver)...
start "EV Driver" cmd /k "python Driver\EV_Driver.py localhost:9092 driver_001"
timeout /t 1 /nobreak >nul

echo.
echo ============================================================
echo                   所有服务已启动！
echo ============================================================
echo.
echo 提示:
echo   - 所有服务已在独立窗口中启动
echo   - 关闭对应窗口即可停止服务
echo   - 确保 Kafka 服务已经启动
echo.
echo 按任意键退出启动脚本...
pause >nul
