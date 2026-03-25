@echo off
title KRATOS — pm2 Kurulum
color 0B
echo.
echo  =========================================
echo    ^⚡  KRATOS — pm2 Background Service
echo  =========================================
echo.

:: pm2 kurulu mu?
where pm2 >nul 2>&1
if %errorlevel% neq 0 (
    echo  [*] pm2 kuruluyor...
    npm install -g pm2
    npm install -g pm2-windows-startup
)

cd /d "C:\Users\canad\OneDrive\Masaüstü\GitProjects\DayiApp\Kratos"

echo  [*] Mevcut kratos process durduruluyor (varsa)...
pm2 delete kratos-trading 2>nul

echo  [*] KRATOS baslatılıyor...
pm2 start ecosystem.config.js

echo  [*] Windows baslangiçta otomatik calissin mi?
echo      (Bunu once ADMIN olarak calistir!)
pm2 save

echo.
echo  =========================================
echo   [✓] KRATOS http://localhost:8501 adresinde!
echo  =========================================
echo.
echo  Komutlar:
echo    pm2 status              — durum görüntüle
echo    pm2 logs kratos-trading — logları izle
echo    pm2 restart kratos-trading — yeniden başlat
echo    pm2 stop kratos-trading    — durdur
echo.
start http://localhost:8501
pause
