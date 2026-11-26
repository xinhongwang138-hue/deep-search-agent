-- 示例业务库：药品流通（供数据库查询子智能体演示）
-- 执行：mysql -u root -p < sql/db.sql

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS cps_demo
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE cps_demo;

CREATE TABLE IF NOT EXISTS drugs (
  drug_id         VARCHAR(16)  NOT NULL COMMENT '药品编码',
  drug_name       VARCHAR(64)  NOT NULL COMMENT '商品名',
  generic_name    VARCHAR(64)  NOT NULL COMMENT '通用名',
  category        VARCHAR(32)  NOT NULL COMMENT '品类（抗生素/心血管/消化系统/中成药/维生素）',
  spec            VARCHAR(64)  NOT NULL COMMENT '规格',
  manufacturer    VARCHAR(64)  NOT NULL COMMENT '生产企业',
  approval_no     VARCHAR(32)  NOT NULL COMMENT '批准文号',
  unit_price      DECIMAL(10,2) NOT NULL COMMENT '含税单价（元）',
  is_prescription TINYINT      NOT NULL DEFAULT 1 COMMENT '是否处方药 1是 0否',
  status          VARCHAR(16)  NOT NULL DEFAULT '在售' COMMENT '在售/停售',
  created_at      DATE         NOT NULL COMMENT '建档日期',
  PRIMARY KEY (drug_id),
  KEY idx_drugs_category (category),
  KEY idx_drugs_name (drug_name)
) ENGINE = InnoDB COMMENT = '药品基础信息';

CREATE TABLE IF NOT EXISTS inventory (
  inventory_id  BIGINT       NOT NULL AUTO_INCREMENT COMMENT '库存流水号',
  drug_id       VARCHAR(16)  NOT NULL COMMENT '药品编码',
  warehouse     VARCHAR(32)  NOT NULL COMMENT '仓库（华东仓/华南仓/华北仓）',
  batch_no      VARCHAR(32)  NOT NULL COMMENT '批号',
  quantity      INT          NOT NULL COMMENT '在库数量',
  safety_stock  INT          NOT NULL COMMENT '安全库存下限',
  expiry_date   DATE         NOT NULL COMMENT '有效期至',
  updated_at    DATETIME     NOT NULL COMMENT '最近更新时间',
  PRIMARY KEY (inventory_id),
  KEY idx_inventory_drug (drug_id),
  KEY idx_inventory_warehouse (warehouse),
  CONSTRAINT fk_inventory_drug FOREIGN KEY (drug_id) REFERENCES drugs (drug_id)
) ENGINE = InnoDB COMMENT = '库存快照';

CREATE TABLE IF NOT EXISTS sales_orders (
  order_id      BIGINT       NOT NULL COMMENT '订单号',
  drug_id       VARCHAR(16)  NOT NULL COMMENT '药品编码',
  customer_type VARCHAR(16)  NOT NULL COMMENT '客户类型（医院/连锁药房/经销商/电商）',
  region        VARCHAR(16)  NOT NULL COMMENT '销售区域（华东/华南/华北/西南）',
  quantity      INT          NOT NULL COMMENT '销售数量',
  unit_price    DECIMAL(10,2) NOT NULL COMMENT '成交单价（元）',
  amount        DECIMAL(12,2) NOT NULL COMMENT '成交金额（元）',
  order_date    DATE         NOT NULL COMMENT '下单日期',
  salesperson   VARCHAR(16)  NOT NULL COMMENT '业务员',
  PRIMARY KEY (order_id),
  KEY idx_sales_date (order_date),
  KEY idx_sales_drug (drug_id),
  KEY idx_sales_region (region),
  CONSTRAINT fk_sales_drug FOREIGN KEY (drug_id) REFERENCES drugs (drug_id)
) ENGINE = InnoDB COMMENT = '销售流水';
