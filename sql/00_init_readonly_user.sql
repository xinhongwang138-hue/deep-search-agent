-- 演示环境初始化（容器首次启动时按文件名顺序最先执行）
-- 目的：建只读账号，仅授予 SELECT，模拟企业侧给智能体的最小权限数据源账号。

CREATE DATABASE IF NOT EXISTS cps_demo
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

-- pymysql 走原生密码插件，避免额外依赖 cryptography
CREATE USER IF NOT EXISTS 'readonly'@'%'
  IDENTIFIED WITH mysql_native_password BY 'demo_readonly_2024';

GRANT SELECT ON cps_demo.* TO 'readonly'@'%';

FLUSH PRIVILEGES;
