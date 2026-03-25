module.exports = {
  apps: [
    {
      name: "kratos-trading",
      script: "streamlit",
      args: [
        "run", "app.py",
        "--server.port", "8501",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "poll",   // OneDrive klasörü için gerekli
      ],
      interpreter: "none",   // streamlit direkt çalıştır (Python değil)
      cwd: "C:\\Users\\canad\\OneDrive\\Masaüstü\\GitProjects\\DayiApp\\Kratos",
      watch: false,           // pm2'nin kendi watch'ını kapat (streamlit kendi yapıyor)
      autorestart: true,      // crash olursa yeniden başlat
      max_restarts: 5,
      restart_delay: 3000,    // 3sn bekle sonra yeniden başlat
      env: {
        PYTHONUNBUFFERED: "1",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "./kratos_pm2_error.log",
      out_file:   "./kratos_pm2_out.log",
      merge_logs: true,
    },
  ],
};
