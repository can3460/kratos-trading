@echo off
title KRATOS Trading Platform
color 0B
echo.
echo  =========================================
echo    ^⚡  KRATOS Unified Trading Platform
echo  =========================================
echo.
cd /d "C:\Users\canad\OneDrive\Masaüstü\GitProjects\DayiApp\Kratos"

:: Check if streamlit is installed
where streamlit >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Streamlit bulunamadi. Yuklenıyor...
    pip install -r requirements.txt
)

echo  [*] Sunucu baslatılıyor: http://localhost:8501
echo  [*] Durdurmak icin bu pencereyi kapatın veya Ctrl+C
echo.
start http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
