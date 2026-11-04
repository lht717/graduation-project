-- =============================================================
-- FusionLab 数据库建表脚本（MySQL 8.0）
-- 数据库：fusionlab
-- 说明：管理员与用户之间的私信系统存储结构
-- =============================================================

-- 1. 创建数据库
CREATE DATABASE IF NOT EXISTS fusionlab
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE fusionlab;

-- 2. 用户表
CREATE TABLE IF NOT EXISTS `users` (
  `username`       varchar(64)  NOT NULL COMMENT '账号（学号，主键）',
  `account_id`     varchar(64)  NOT NULL COMMENT '学号',
  `display_name`   varchar(128) NOT NULL COMMENT '显示名（自定义名称）',
  `role`           varchar(16)  NOT NULL DEFAULT 'user' COMMENT '角色：admin=管理员 / user=普通用户',
  `role_name`      varchar(32)  NOT NULL DEFAULT '普通用户' COMMENT '角色显示名',
  `password_hash`  varchar(128) NOT NULL COMMENT '密码（加盐哈希）',
  `registered_at`  varchar(64)  NOT NULL DEFAULT '' COMMENT '注册时间',
  PRIMARY KEY (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户表';

-- 3. 私信表
CREATE TABLE IF NOT EXISTS `messages` (
  `id`               bigint       NOT NULL AUTO_INCREMENT COMMENT '消息ID',
  `subject`          varchar(255) NOT NULL DEFAULT '' COMMENT '主题',
  `sender`           varchar(128) NOT NULL COMMENT '发件人显示名',
  `sender_username`  varchar(64)  NOT NULL COMMENT '发件人账号',
  `recipient`        varchar(128) NOT NULL COMMENT '收件人显示名',
  `recipient_username` varchar(64) NOT NULL COMMENT '收件人账号',
  `content`          text         NOT NULL COMMENT '消息内容',
  `created_at`       varchar(64)  NOT NULL COMMENT '发送时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='私信表';
