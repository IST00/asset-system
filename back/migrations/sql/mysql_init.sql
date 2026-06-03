-- ============================================================================
-- Scaffold-python · MySQL 全量初始化脚本
-- 等价于 Alembic 迁移 001 + 002 + 003 一次性应用到全新 MySQL 实例。
--
-- 适用：首次部署 / 灾难重建 / 同事本地手工拉起。
-- 日常开发与小步演进仍走 `flask db upgrade`，不要手工 source 这个文件。
--
-- 假定：
--   - 目标 MySQL 8.0+，字符集 utf8mb4
--   - 当前会话已 `USE <db_name>;` 或允许下面的 CREATE DATABASE 生效
--   - 如果你的 DB 已存在并已被 Alembic 接管，请直接走 `flask db upgrade`，
--     不要 source 这个文件，否则 alembic_version 与表会冲突。
--
-- 用法：
--   mysql -h <host> -u <user> -p < back/migrations/sql/mysql_init.sql
--
-- 默认账号：admin / admin123（bcrypt hash 与 Alembic 001 完全一致）
-- ============================================================================

-- 如需脚本自建库,取消下面两行注释并按需修改库名:
-- CREATE DATABASE IF NOT EXISTS `scaffold` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE `scaffold`;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------------------------------------------------------
-- 表 users (迁移 001)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id`         INT          NOT NULL AUTO_INCREMENT,
  `username`   VARCHAR(64)  NOT NULL,
  `password`   VARCHAR(255) NOT NULL,
  `nickname`   VARCHAR(64)  DEFAULT NULL,
  `role`       VARCHAR(32)  DEFAULT NULL,
  `enabled`    TINYINT(1)   NOT NULL DEFAULT 1,
  `created_at` DATETIME     NOT NULL,
  `updated_at` DATETIME     NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_username` (`username`),
  KEY `ix_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 默认管理员: admin / admin123
-- bcrypt hash 与 back/migrations/versions/001_init.py 中的 _ADMIN_HASH 完全一致。
INSERT INTO `users` (`username`, `password`, `nickname`, `role`, `enabled`, `created_at`, `updated_at`)
VALUES (
  'admin',
  '$2b$10$f0NJc81l7nI/lQ9tn9Xhqe7r3tt7ELbU12TG2n98n/1gsI5CxdZI6',
  'Admin',
  'ADMIN',
  1,
  UTC_TIMESTAMP(),
  UTC_TIMESTAMP()
);

-- ----------------------------------------------------------------------------
-- 表 events (迁移 002) — Keke H5 五类埋点事件
--   visit / generate_start / generate_success / save_open / save_success
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS `events`;
CREATE TABLE `events` (
  `id`          INT          NOT NULL AUTO_INCREMENT,
  `event_name`  VARCHAR(32)  NOT NULL,
  `device_id`   VARCHAR(64)  NOT NULL,
  `source`      VARCHAR(32)  NOT NULL DEFAULT 'unknown',
  `ua`          VARCHAR(32)  DEFAULT NULL,
  `keyword`     VARCHAR(64)  DEFAULT NULL,
  `duration_ms` INT          DEFAULT NULL,
  `created_at`  DATETIME     NOT NULL,
  `updated_at`  DATETIME     NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_events_event_name` (`event_name`),
  KEY `ix_events_device_id`  (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 表 devices (迁移 003) — 首访设备登记,用于 UV 统计
--   不加 UNIQUE: 前端 localStorage 是主防重,DB 端宽松
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS `devices`;
CREATE TABLE `devices` (
  `id`         INT          NOT NULL AUTO_INCREMENT,
  `device_id`  VARCHAR(64)  NOT NULL,
  `source`     VARCHAR(32)  NOT NULL DEFAULT 'unknown',
  `ua`         VARCHAR(32)  DEFAULT NULL,
  `created_at` DATETIME     NOT NULL,
  `updated_at` DATETIME     NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_devices_device_id` (`device_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- alembic_version: 标记当前已应用到 003,让后续 `flask db upgrade` 知道
-- 应该从哪条迁移开始,不要再重新跑 001/002/003。
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE `alembic_version` (
  `version_num` VARCHAR(32) NOT NULL,
  CONSTRAINT `pk_alembic_version` PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `alembic_version` (`version_num`) VALUES ('003');

SET FOREIGN_KEY_CHECKS = 1;
