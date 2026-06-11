-- 阶段二：仅创建业务数据库
-- 表结构由 SQLAlchemy Model + python app/db/init_db.py 创建

CREATE DATABASE IF NOT EXISTS digital_employee
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
