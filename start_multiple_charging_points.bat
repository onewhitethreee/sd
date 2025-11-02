@echo off
chcp 65001 >nul
title EV Charging System - 多充电桩启动器

echo ============================================================
echo          EV 充电系统 - 多充电桩启动脚本
echo ============================================================
echo.

REM 设置变量
set BROKER_ADDRESS=localhost:9092
set CENTRAL_ADDRESS=localhost:5000

REM 设置充电桩数量
set NUM_CHARGING_POINTS=3

REM 起始端口号（每个充电桩需要1个端口给Engine）
set START_PORT=6000

echo 配置信息:
echo   - Broker地址: %BROKER_ADDRESS%
echo   - Central地址: %CENTRAL_ADDRESS%
echo   - 充电桩数量: %NUM_CHARGING_POINTS%
echo   - 起始端口: %START_PORT%
echo.
echo ============================================================
echo.

REM 等待用户确认
echo 按任意键开始启动充电桩...
pause >nul
echo.

REM 启动多个充电桩
for /l %%i in (1,1,%NUM_CHARGING_POINTS%) do (
    call :start_charging_point %%i
    timeout /t 2 /nobreak >nul
)

echo.
echo ============================================================
echo          所有充电桩已启动完成！
echo ============================================================
echo.
echo 启动的充电桩:
for /l %%i in (1,1,%NUM_CHARGING_POINTS%) do (
    set /a PORT=%START_PORT%+%%i-1
    echo   - CP_%%i (端口: !PORT!)
)
echo.
echo 提示:
echo   - 所有充电桩已在独立窗口中启动
echo   - 关闭对应窗口即可停止该充电桩
echo   - 确保 Central 和 Kafka 服务已经启动
echo.
echo 按任意键退出启动脚本...
pause >nul
exit /b

REM ============================================================
REM 子程序：启动单个充电桩
REM ============================================================
:start_charging_point
setlocal EnableDelayedExpansion
set CP_NUM=%1
set /a ENGINE_PORT=%START_PORT%+%CP_NUM%-1
set CP_ID=CP_%CP_NUM%

echo [%CP_NUM%/%NUM_CHARGING_POINTS%] 启动充电桩: %CP_ID% (Engine端口: %ENGINE_PORT%)

REM 1. 启动 Engine (EV_CP_E)
echo   └─ 启动 Engine...
start "Engine - %CP_ID%" cmd /k "set ENGINE_LISTEN_PORT=%ENGINE_PORT% && set ENGINE_LISTEN_HOST=localhost && python Charging_point\Engine\EV_CP_E.py %BROKER_ADDRESS%"
timeout /t 1 /nobreak >nul

REM 2. 启动 Monitor (EC_CP_M)
echo   └─ 启动 Monitor...
start "Monitor - %CP_ID%" cmd /k "python Charging_point\Monitor\EC_CP_M.py localhost:%ENGINE_PORT% %CENTRAL_ADDRESS% %CP_ID%"

endlocal
exit /b
