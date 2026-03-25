@echo off
:: Bu dosyayi YONETICI olarak calistir (Sag tik -> Yonetici olarak calistır)
title KRATOS — Windows Task Scheduler Kurulum

set TASK_NAME=KRATOS_Trading
set BAT_PATH=C:\Users\canad\OneDrive\Masaüstü\GitProjects\DayiApp\Kratos\kratos_start.bat

echo  [*] Eski gorev siliniyor (varsa)...
schtasks /delete /tn "%TASK_NAME%" /f 2>nul

echo  [*] Windows oturumu acildiginda otomatik baslama gorevi olusturuluyor...
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%BAT_PATH%\"" ^
  /sc ONLOGON ^
  /delay 0000:30 ^
  /ru "%USERNAME%" ^
  /f

echo.
echo  [✓] Gorev olusturuldu: "%TASK_NAME%"
echo      Bir sonraki Windows girişinde KRATOS otomatik baslar.
echo.
echo  Manuel calistirmak icin:
echo    schtasks /run /tn "%TASK_NAME%"
echo.
pause
