@echo off
chcp 65001 >nul
echo ============================================
echo   强国有我大思政课案例库 - 启动脚本
echo ============================================
echo.

cd /d "%~dp0backend"

echo [1/4] 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python未安装，请先安装Python
    pause
    exit /b 1
)
echo Python环境检查通过
echo.

echo [2/4] 安装依赖...
pip install fastapi uvicorn python-multipart pymongo python-dotenv -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

echo [3/4] 初始化数据库并添加演示数据...
cd /d "%~dp0backend"
if exist "%~dp0data\cases.db" (
    echo 数据库已存在，跳过案例初始化
) else (
    python demo.py
)
python init_users.py
echo.

echo [4/4] 启动后端服务...
cd /d "%~dp0backend"
echo.
echo ============================================
echo   后端服务地址：http://localhost:8001
echo   前端页面：http://localhost:8001
echo.
echo   按 Ctrl+C 停止服务
echo ============================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8001

pause
