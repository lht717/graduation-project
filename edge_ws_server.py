#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FusionLab AutoDrive —— 边缘主板 WebSocket 接入服务（独立可运行）

本项目用于「虚实结合」模式的真实边缘设备接入：
    边缘主板（Jetson / RK3588 / Ascend …）
        │  ① 上报目标检测 JSON（上行）
        │  ② 接收前端下发的控制指令（下行）
        ▼
    本文件提供的 FastAPI WebSocket 服务
        │  ③ 把检测结果实时广播给浏览器工作台
        │  ④ 把控制指令精准转发给指定 device_id
        ▼
    FusionLab 前端工作台 / 其他订阅方

功能清单（对应毕设需求）：
    1. WebSocket 握手鉴权：URL 参数 device_id + token，未通过直接 1008 拒绝；
    2. 在线设备连接池：device_id -> 连接对象，含状态、心跳、上下线时间；
    3. 接收边缘主板上传的目标检测 JSON（兼容多种字段/纯数组）；
    4. 前端控制指令按 device_id 转发，并回执 command_status；
    5. 捕获 WebSocketDisconnect，断开时自动清理连接池 + 广播离线；
    6. 分级日志（控制台 + 滚动文件），可选把设备事件/检测结果写入 MySQL；
    7. 局域网可访问：默认 --host 0.0.0.0，命令行参数可改端口与密钥。

运行方式（Windows / Linux / macOS 通用）：
    # 最简启动（默认 0.0.0.0:8081，避免与其它的 8080 冲突）
    python edge_ws_server.py

    # 指定端口、全局设备密钥、并开启 MySQL 日志
    python edge_ws_server.py --port 8081 --token fusionlab-edge-token \
        --mysql --mysql-password 123456

    # 为每台设备下发独立密钥（更接近真实生产）
    python edge_ws_server.py --device-token "jetson-nano:nano-secret,rk3588:rk-secret"

设备侧连接示例：
    ws://192.168.1.20:8081/ws/edge?device_id=jetson-nano&token=fusionlab-edge-token

前端工作台连接示例：
    ws://192.168.1.20:8081/ws/dashboard?token=fusionlab-edge-token

依赖：
    pip install fastapi uvicorn
    pip install pymysql          # 仅在启用 MySQL 日志时需要
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import hmac
import json
import logging
import os
import time
import uuid
import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 全局配置（在 main() 中由命令行参数填充，服务运行期间只读）
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """服务运行配置，集中管理，避免魔法数字散落在业务代码里。"""

    host: str = "0.0.0.0"                     # 监听地址：0.0.0.0 表示局域网内可访问
    port: int = 8081                          # 监听端口（避开 CARLA 链路占用的 8080）
    default_token: str = "fusionlab-edge-token"   # 未单独配置密钥的设备默认使用它
    device_tokens: Dict[str, str] = field(default_factory=dict)  # device_id -> 独立密钥
    dashboard_token: str = ""                 # 控制端密钥；留空表示不校验控制端
    # 控制端鉴权回调（token -> bool）。嵌入 main.py 时指向平台登录会话，
    # 这样浏览器只带平台自己的 token 就能订阅，不需要额外一套密钥。
    dashboard_auth: Optional[Callable[[str], bool]] = None
    kick_duplicate: bool = True               # 同一 device_id 重复连接时是否踢掉旧连接
    heartbeat_timeout: float = 60.0           # 超过该秒数没收到任何消息则判为掉线
    max_detection_per_second: float = 30.0    # 单设备上报限流（防止刷爆服务与数据库）
    snapshot_limit: int = 50                  # 设备断开时写入日志的检测条数上限
    log_file: Optional[str] = "logs/edge_ws_server.log"
    log_level: str = "INFO"
    # 设备上线/离线历史（本地 JSON，重启后仍能展示「最近连接过的设备」）
    history_file: str = "logs/edge_devices_history.json"
    history_limit: int = 50                   # 最多保留多少台设备的历史

    # ---- 可选的 MySQL 持久化（毕设扩展项，默认关闭，不影响主链路）----
    mysql_enabled: bool = False
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "fusionlab"


CFG = Config()
logger = logging.getLogger("edge_ws")


# ---------------------------------------------------------------------------
# 版本兼容：Python 3.7 没有 asyncio.to_thread，create_task 也不接受 name 参数。
# 现场机器（JetPack / Anaconda 老环境）可能仍是 3.7，这里统一包一层，
# 避免服务在启动或处理 MySQL 批量写入时因为 API 不存在而崩溃。
# ---------------------------------------------------------------------------


async def run_in_thread(func, *args):
    """把阻塞调用丢到默认线程池执行（等价 asyncio.to_thread，兼容 3.7）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args))


def spawn(coro, name: str = "") -> "asyncio.Task":
    """创建后台任务；name 只用于调试，3.7 不支持该参数时忽略。"""
    try:
        return asyncio.create_task(coro, name=name)
    except TypeError:  # Python 3.7
        return asyncio.create_task(coro)


# ---------------------------------------------------------------------------
# 日志：控制台 + 可选滚动文件。所有关键动作都走同一套 logger，
# 后期接 ELK / 文件采集不需要改业务代码。
# ---------------------------------------------------------------------------


# 缩略图上限：超过这个长度的 thumb 一律丢弃（防止设备端发大图把广播和数据库撑爆）。
# 320px 宽的 JPEG 约 20~30 KB，base64 后约 40 KB 字符，512 KB 已经是 10 倍余量。
MAX_THUMB_CHARS = 512 * 1024
THUMB_PREFIX = "data:image/jpeg;base64,"


def pick_thumb(message: Any) -> str:
    """
    从设备上报里取出缩略图，并把它从原始报文里剔除。

    剔除的原因是同一个 base64 会被用到三处：broadcast 的 `thumb` 字段、`raw` 原始报文、
    MySQL 的 raw_json 列。如果不删，单帧流量直接翻倍，数据库也会以每秒几十 KB 的速度膨胀。
    """
    if not isinstance(message, dict):
        return ""
    target = message
    # 兼容 {"data": {"thumb": ...}} 这种外面又包一层的格式
    if isinstance(message.get("data"), dict) and "thumb" not in message:
        target = message["data"]
    thumb = target.pop("thumb", "")
    if not isinstance(thumb, str) or not thumb.startswith(THUMB_PREFIX) or len(thumb) > MAX_THUMB_CHARS:
        return ""
    return thumb


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """初始化日志格式与输出目标（重复调用不会叠加 handler）。"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    # 格式：[2026-11-11 16:20:01] INFO  边缘设备已接入｜device_id=jetson-nano
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,   # 单文件 10MB
            backupCount=5,              # 保留 5 份历史
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # 降低第三方库噪音，只保留警告以上
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def now_str() -> str:
    """统一时间格式，便于日志与数据库对齐。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_iso() -> str:
    """ISO 时间戳，下发给前端时使用，浏览器可直接 new Date() 解析。"""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


# ---------------------------------------------------------------------------
# 数据模型：连接池中保存的「一台边缘设备」
# ---------------------------------------------------------------------------


@dataclass
class DeviceConn:
    """在线设备的一条连接记录（连接池 value）。"""

    device_id: str
    websocket: WebSocket
    connected_at: float = field(default_factory=time.time)  # 接入时间（时间戳）
    last_seen: float = field(default_factory=time.time)     # 最近一次收到消息（用于心跳超时）
    name: str = ""            # 设备显示名，如 Jetson Nano
    vendor: str = ""          # 厂商
    model: str = ""           # 芯片 / 型号
    device_no: str = ""       # 设备编号，如 Edge-01
    status: str = "idle"      # idle=空闲 / busy=正在检测
    remote_addr: str = ""     # 对端 IP，便于排查现场问题
    message_count: int = 0    # 累计收到的消息数
    detection_count: int = 0  # 累计收到的检测帧数
    # 每台设备一把发送锁：Starlette 的 WebSocket 不允许并发调用 send_text
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def summary(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的字典，直接下发给前端。"""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "vendor": self.vendor,
            "model": self.model,
            "device_no": self.device_no,
            "status": self.status,
            "remote_addr": self.remote_addr,
            "connected_at": datetime.fromtimestamp(self.connected_at).strftime("%Y-%m-%d %H:%M:%S"),
            "online_seconds": int(time.time() - self.connected_at),
            "last_seen": datetime.fromtimestamp(self.last_seen).strftime("%Y-%m-%d %H:%M:%S"),
            "message_count": self.message_count,
            "detection_count": self.detection_count,
        }


@dataclass(eq=False)  # eq=False：按对象身份比较/哈希，才能放进 set 里做订阅集合
class DashboardConn:
    """前端 / 订阅端连接（只收数据，不下发到设备）。"""

    websocket: WebSocket
    client: str = "dashboard"
    connected_at: float = field(default_factory=time.time)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# ---------------------------------------------------------------------------
# 可选：MySQL 异步写入器
#   检测数据是高频流，直接在 WebSocket 回调里执行 SQL 会阻塞事件循环，
#   所以这里用「内存队列 + 后台消费者 + 批量插入」的解耦写法。
# ---------------------------------------------------------------------------


class MySQLWriter:
    """设备事件与检测结果的可选持久化组件（未启用时不产生任何开销）。"""

    EVENT_DDL = """
    CREATE TABLE IF NOT EXISTS `edge_device_event` (
      `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
      `device_id`   VARCHAR(64)  NOT NULL COMMENT '边缘设备ID',
      `event`       VARCHAR(32)  NOT NULL COMMENT '事件：online/offline/auth_failed/...',
      `detail`      VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '事件详情',
      `remote_addr` VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '对端地址',
      `created_at`  DATETIME(3)  NOT NULL COMMENT '发生时间',
      PRIMARY KEY (`id`),
      KEY `idx_device_event_device` (`device_id`),
      KEY `idx_device_event_time` (`created_at`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='边缘设备上下线事件'
    """

    DETECTION_DDL = """
    CREATE TABLE IF NOT EXISTS `edge_detection_log` (
      `id`             BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
      `device_id`      VARCHAR(64) NOT NULL COMMENT '边缘设备ID',
      `object_count`   INT         NOT NULL DEFAULT 0 COMMENT '本帧目标数量',
      `top_class`      VARCHAR(64) NOT NULL DEFAULT '' COMMENT '置信度最高的类别',
      `top_confidence` DOUBLE      NOT NULL DEFAULT 0 COMMENT '最高置信度',
      `payload`        LONGTEXT    NULL COMMENT '原始检测JSON（便于回溯）',
      `created_at`     DATETIME(3) NOT NULL COMMENT '上报时间',
      PRIMARY KEY (`id`),
      KEY `idx_detection_device` (`device_id`),
      KEY `idx_detection_time` (`created_at`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='边缘设备目标检测上报记录'
    """

    def __init__(self, maxsize: int = 5000) -> None:
        self.queue: "asyncio.Queue[tuple]" = asyncio.Queue(maxsize=maxsize)
        self.available = False          # 数据库是否成功连接（决定是否入队）
        self.worker: Optional[asyncio.Task] = None
        self.dropped = 0                # 队列满时丢弃的条数，便于观察压力

    # ---------------- 连接与建表 ----------------
    def _connect(self):
        """同步建立连接（放在线程里执行，避免阻塞事件循环）。"""
        import pymysql

        return pymysql.connect(
            host=CFG.mysql_host,
            port=CFG.mysql_port,
            user=CFG.mysql_user,
            password=CFG.mysql_password,
            database=CFG.mysql_database,
            charset="utf8mb4",
            autocommit=True,
        )

    def _init_tables(self) -> None:
        """启动时自动建表，降低答辩部署成本。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(self.EVENT_DDL)
                cur.execute(self.DETECTION_DDL)
        finally:
            conn.close()

    async def start(self) -> None:
        """启用时调用：建表 + 拉起后台消费者。失败只告警，不影响 WebSocket 主链路。"""
        if not CFG.mysql_enabled:
            return
        try:
            await run_in_thread(self._init_tables)
        except Exception as exc:  # noqa: BLE001 - 数据库故障不允许拖垮主服务
            logger.error("MySQL 初始化失败，已自动降级为仅日志模式：%s", exc)
            return
        self.available = True
        self.worker = spawn(self._consume(), "mysql-writer")
        logger.info(
            "MySQL 日志已启用：%s:%s/%s（设备事件 + 检测记录）",
            CFG.mysql_host, CFG.mysql_port, CFG.mysql_database,
        )

    async def stop(self) -> None:
        """退出前尽量把队列里剩下的数据刷完，避免丢记录。"""
        if not self.worker:
            return
        self.worker.cancel()
        try:
            await self.worker
        except asyncio.CancelledError:
            pass
        self.worker = None

    # ---------------- 入队（非阻塞） ----------------
    def log_event(self, device_id: str, event: str, detail: str = "", remote: str = "") -> None:
        self._put(("event", (device_id, event, detail[:1000], remote, now_str())))

    def log_detection(self, device_id: str, detections: List[dict], raw: Any) -> None:
        top_class, top_conf = _top_object(detections)
        try:
            payload = json.dumps(raw, ensure_ascii=False)[:20000]
        except (TypeError, ValueError):
            payload = ""
        self._put((
            "detection",
            (device_id, len(detections), top_class, float(top_conf), payload, now_str()),
        ))

    def _put(self, item: tuple) -> None:
        if not self.available:
            return
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped % 200 == 1:
                logger.warning("MySQL 写入队列已满，累计丢弃 %d 条（可调大 --mysql-queue）", self.dropped)

    # ---------------- 后台批量写入 ----------------
    async def _consume(self) -> None:
        """每 0.5 秒或攒够 50 条就批量落库一次，兼顾实时性与写入效率。"""
        batch: List[tuple] = []
        while True:
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                batch.append(item)
            except asyncio.TimeoutError:
                pass

            # 一次性把队列里现有的都取出来（最多 200 条）
            while len(batch) < 200 and not self.queue.empty():
                batch.append(self.queue.get_nowait())

            if not batch:
                continue
            try:
                await run_in_thread(self._flush, list(batch))
            except Exception as exc:  # noqa: BLE001
                logger.warning("MySQL 批量写入失败（%d 条已丢弃）：%s", len(batch), exc)
            batch.clear()

    def _flush(self, batch: List[tuple]) -> None:
        events = [payload for kind, payload in batch if kind == "event"]
        detections = [payload for kind, payload in batch if kind == "detection"]
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if events:
                    cur.executemany(
                        "INSERT INTO edge_device_event "
                        "(device_id, event, detail, remote_addr, created_at) VALUES (%s,%s,%s,%s,%s)",
                        events,
                    )
                if detections:
                    cur.executemany(
                        "INSERT INTO edge_detection_log "
                        "(device_id, object_count, top_class, top_confidence, payload, created_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        detections,
                    )
        finally:
            conn.close()


DB = MySQLWriter()


# ---------------------------------------------------------------------------
# 检测数据解析：兼容不同厂商主板的 JSON 结构
# ---------------------------------------------------------------------------


def _bbox_of(obj: dict) -> List[float]:
    """统一取出边界框，支持 bbox / box / xyxy 等常见字段名。"""
    for key in ("bbox", "box", "xyxy", "rect"):
        value = obj.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            try:
                return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
            except (TypeError, ValueError):
                continue
    # 兼容 {x1,y1,x2,y2} 这种对象写法
    if all(k in obj for k in ("x1", "y1", "x2", "y2")):
        try:
            return [float(obj["x1"]), float(obj["y1"]), float(obj["x2"]), float(obj["y2"])]
        except (TypeError, ValueError):
            return []
    return []


def normalize_detection(message: Any) -> Dict[str, Any]:
    """
    把主板上报的数据整理成统一结构：{"detections": [...], "raw": ...}

    支持四种常见上报格式：
        1) {"type":"detection","detections":[...]}
        2) {"detections": [...]} / {"objects": [...]} / {"results": [...]}
        3) 直接一个数组 [...]
        4) {"type":"detection","data":{"detections":[...]}}
    """
    raw = message
    detections: List[dict] = []

    # 情形 4：外面又包了一层 data
    if isinstance(message, dict) and isinstance(message.get("data"), (dict, list)):
        inner = message["data"]
        if isinstance(inner, list) and not isinstance(message.get("detections"), list):
            detections = inner
        elif isinstance(inner, dict):
            message = inner

    if not detections:
        if isinstance(message, list):
            detections = message
        elif isinstance(message, dict):
            for key in ("detections", "objects", "results", "items"):
                if isinstance(message.get(key), list):
                    detections = message[key]
                    break

    # 逐条规范化，前端就不用再猜字段名了
    cleaned: List[dict] = []
    for obj in detections:
        if not isinstance(obj, dict):
            continue
        cleaned.append({
            "class_name": str(obj.get("class_name") or obj.get("label") or obj.get("name") or "unknown")[:64],
            "confidence": _to_float(obj.get("confidence", obj.get("score", 0.0))),
            "bbox": _bbox_of(obj),
            # 保留原字段，方便前端展示完整 JSON 或后续扩展（如 track_id）
            "raw": obj,
        })

    return {"detections": cleaned, "raw": raw}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _top_object(detections: List[dict]) -> tuple:
    """取置信度最高的类别，作为检测记录的摘要字段。"""
    best_class, best_conf = "", 0.0
    for obj in detections:
        conf = _to_float(obj.get("confidence"))
        if conf >= best_conf:
            best_class, best_conf = str(obj.get("class_name", ""))[:64], conf
    return best_class, best_conf


# ---------------------------------------------------------------------------
# 连接池（核心）
# ---------------------------------------------------------------------------


class ConnectionManager:
    """
    在线设备连接池 + 控制端订阅集合。

    - devices:    device_id -> DeviceConn      （一个设备只保留一条连接）
    - dashboards: 所有前端 / 订阅端连接
    - lock:       保护字典读写，避免并发注册/清理导致数据错乱
    """

    def __init__(self) -> None:
        self.devices: Dict[str, DeviceConn] = {}
        self.dashboards: Set[DashboardConn] = set()
        self._lock = asyncio.Lock()

    # ---------------- 设备注册 / 注销 ----------------
    async def register_device(self, conn: DeviceConn) -> Optional[DeviceConn]:
        """
        注册设备。若同一 device_id 已在线：
            kick_duplicate=True  → 踢掉旧连接（常见于设备断网重连，旧连接还没超时）
            kick_duplicate=False → 拒绝新连接
        返回被踢掉的旧连接（没有则返回 None），由调用方负责关闭它。
        """
        old: Optional[DeviceConn] = None
        async with self._lock:
            old = self.devices.get(conn.device_id)
            if old is not None and not CFG.kick_duplicate:
                raise RuntimeError(f"设备 {conn.device_id} 已在线")
            self.devices[conn.device_id] = conn
        return old

    async def unregister_device(self, device_id: str, websocket: WebSocket) -> Optional[DeviceConn]:
        """
        注销设备。必须校验 websocket 是否是同一条连接——
        否则「旧连接被踢 → 新连接已注册 → 旧连接 finally 才执行」会把新连接误删。
        """
        async with self._lock:
            conn = self.devices.get(device_id)
            if conn is not None and conn.websocket is websocket:
                del self.devices[device_id]
                return conn
        return None

    # ---------------- 控制端注册 / 注销 ----------------
    async def add_dashboard(self, conn: DashboardConn) -> None:
        async with self._lock:
            self.dashboards.add(conn)

    async def remove_dashboard(self, conn: DashboardConn) -> None:
        async with self._lock:
            self.dashboards.discard(conn)

    # ---------------- 查询 ----------------
    def get_device(self, device_id: str) -> Optional[DeviceConn]:
        return self.devices.get(device_id)

    def device_list(self) -> List[Dict[str, Any]]:
        return [conn.summary() for conn in self.devices.values()]

    def stats(self) -> Dict[str, Any]:
        return {
            "online_devices": len(self.devices),
            "online_dashboards": len(self.dashboards),
            "mysql_enabled": DB.available,
            "mysql_dropped": DB.dropped,
            "uptime_seconds": int(time.time() - START_TIME),
        }

    # ---------------- 发送封装 ----------------
    @staticmethod
    async def safe_send(websocket: WebSocket, lock: asyncio.Lock, message: Dict[str, Any],
                        timeout: float = 3.0) -> bool:
        """
        安全发送：加锁 + 超时 + 吞掉已断开异常。
        返回 True 表示发送成功，False 表示对端已不可用（调用方据此清理）。
        """
        text = json.dumps(message, ensure_ascii=False)
        try:
            async with lock:
                await asyncio.wait_for(websocket.send_text(text), timeout=timeout)
            return True
        except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
            return False

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """广播给所有控制端；发送失败的控制端顺手剔除。"""
        if not self.dashboards:
            return
        dead: List[DashboardConn] = []
        for dash in tuple(self.dashboards):
            ok = await self.safe_send(dash.websocket, dash.send_lock, message)
            if not ok:
                dead.append(dash)
        for dash in dead:
            await self.remove_dashboard(dash)

    async def send_to_device(self, device_id: str, message: Dict[str, Any]) -> bool:
        """把指令精确下发给某台设备；失败则清理该设备。"""
        conn = self.devices.get(device_id)
        if conn is None:
            return False
        ok = await self.safe_send(conn.websocket, conn.send_lock, message)
        if not ok:
            await self.close_device(conn, reason="send_failed", notify=False)
            return False
        return True

    async def close_device(self, conn: DeviceConn, reason: str = "", notify: bool = True) -> None:
        """主动关闭一条设备连接（踢重连、心跳超时、发送失败时调用）。"""
        try:
            await conn.websocket.close(code=4000, reason=reason or "closed")
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        removed = await self.unregister_device(conn.device_id, conn.websocket)
        if removed and notify:
            await self.broadcast_device_offline(removed, reason or "closed")
        elif removed:
            # notify=False（发送失败踢掉）也要落历史，否则该设备会一直显示「在线」
            HISTORY.record_offline(removed.device_id, reason or "closed",
                                   removed.message_count, removed.detection_count)

    # ---------------- 业务广播 ----------------
    async def broadcast_device_online(self, conn: DeviceConn) -> None:
        HISTORY.record_online(conn)
        await self.broadcast({
            "type": "device_online",
            "device_id": conn.device_id,
            "device": conn.summary(),
            "devices": self.device_list(),
            "timestamp": now_iso(),
        })

    async def broadcast_device_offline(self, conn: DeviceConn, reason: str) -> None:
        HISTORY.record_offline(conn.device_id, reason, conn.message_count, conn.detection_count)
        await self.broadcast({
            "type": "device_offline",
            "device_id": conn.device_id,
            "reason": reason,
            "devices": self.device_list(),
            "timestamp": now_iso(),
        })


MANAGER = ConnectionManager()
START_TIME = time.time()


# ---------------------------------------------------------------------------
# 设备上线/离线历史（本地 JSON 持久化，不依赖数据库）
# 目的：连接池只存「当前在线」的设备，后端一重启记录就没了；
# 这里把每台设备最近一次上线/离线写到 JSON 文件，重启后前端仍能展示
# 「最近连接过的设备」，同一 device_id 反复上下线只更新同一条记录。
# ---------------------------------------------------------------------------


class DeviceHistory:
    """按 device_id 记录设备最近一次连接信息的本地 JSON 存储。"""

    def __init__(self, path: str, limit: int = 50) -> None:
        self.path = Path(path)
        self.limit = max(1, int(limit))
        self.records: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ---------------- 读写 ----------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("devices", [])
            for item in items:
                if isinstance(item, dict) and item.get("device_id"):
                    self.records[item["device_id"]] = item
        except Exception as exc:  # noqa: BLE001 - 历史文件坏了不能影响主服务
            logger.warning("设备历史记录加载失败，已重置：%s", exc)
            self.records = {}

    def _save(self) -> None:
        """按最近上线时间倒序截断后原子写盘（先写临时文件再替换）。"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            ordered = sorted(
                self.records.values(),
                key=lambda r: str(r.get("last_online", "")),
                reverse=True,
            )[: self.limit]
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("设备历史记录写入失败：%s", exc)

    # ---------------- 记录事件 ----------------
    def record_online(self, conn: "DeviceConn") -> None:
        rec = self.records.setdefault(conn.device_id, {"device_id": conn.device_id})
        rec.update({
            "device_id": conn.device_id,
            "name": conn.name or conn.device_id,
            "vendor": conn.vendor,
            "model": conn.model,
            "device_no": conn.device_no,
            "remote_addr": conn.remote_addr,
            "last_online": now_str(),
            "last_offline": "",
            "last_offline_reason": "",
            "online": True,
        })
        self._save()

    def record_offline(self, device_id: str, reason: str = "",
                       message_count: int = 0, detection_count: int = 0) -> None:
        rec = self.records.get(device_id)
        if rec is None:          # 从未成功上线的设备无需记录离线
            return
        rec.update({
            "online": False,
            "last_offline": now_str(),
            "last_offline_reason": reason or "-",
            "message_count": int(message_count),
            "detection_count": int(detection_count),
        })
        self._save()

    # ---------------- 查询 ----------------
    def recent(self) -> List[Dict[str, Any]]:
        """按最近上线时间倒序返回全部历史记录（前端展示「最近连接过的设备」）。"""
        return sorted(
            self.records.values(),
            key=lambda r: str(r.get("last_online", "")),
            reverse=True,
        )


HISTORY = DeviceHistory(CFG.history_file, CFG.history_limit)


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------


def verify_device_token(device_id: str, token: str) -> bool:
    """
    校验设备密钥：
        优先匹配 --device-token 里为该设备单独配置的密钥；
        未单独配置时回落到 --token 指定的全局密钥。
    hmac.compare_digest 做定长比较，避免时序攻击（比 == 更规范）。
    """
    if not device_id or not token:
        return False
    expected = CFG.device_tokens.get(device_id, CFG.default_token)
    return hmac.compare_digest(expected, token)


def verify_dashboard_token(token: str) -> bool:
    """
    控制端鉴权，优先级：
        1) CFG.dashboard_auth 回调（嵌入 main.py 时复用平台登录会话）；
        2) --dashboard-token 固定密钥；
        3) 两者都没配 → 放行（单机联调方便，生产建议配置）。
    """
    if CFG.dashboard_auth is not None:
        try:
            return bool(CFG.dashboard_auth(token or ""))
        except Exception as exc:  # noqa: BLE001 - 鉴权回调异常一律按拒绝处理
            logger.warning("控制端鉴权回调异常，按拒绝处理：%s", exc)
            return False
    if not CFG.dashboard_token:
        return True
    return hmac.compare_digest(CFG.dashboard_token, token or "")


# ---------------------------------------------------------------------------
# 业务处理：设备上行
# ---------------------------------------------------------------------------


async def handle_device_message(conn: DeviceConn, text: str) -> None:
    """处理边缘主板上行消息：心跳 / 检测数据 / 指令回执。"""
    conn.last_seen = time.time()
    conn.message_count += 1

    # ---- 1) 非 JSON：按纯文本心跳处理，回 pong，保证连接活跃 ----
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("设备上行非 JSON 文本（device_id=%s）：%s", conn.device_id, text[:200])
        await MANAGER.safe_send(conn.websocket, conn.send_lock, {
            "type": "error", "message": "消息必须是合法 JSON", "timestamp": now_iso(),
        })
        return

    msg_type = message.get("type") if isinstance(message, dict) else None

    # ---- 2) 心跳：更新 last_seen 即可，回一条 pong 让设备知道链路正常 ----
    if msg_type in ("heartbeat", "ping", "keepalive"):
        await MANAGER.safe_send(conn.websocket, conn.send_lock, {
            "type": "pong", "device_id": conn.device_id, "server_time": now_iso(),
        })
        return

    # ---- 3) 指令回执：转发给控制端，让页面知道设备已执行 ----
    if msg_type in ("command_ack", "command_result", "status"):
        await MANAGER.broadcast({
            "type": "command_ack",
            "device_id": conn.device_id,
            "payload": message,
            "timestamp": now_iso(),
        })
        logger.info("设备回执 | device_id=%s | %s", conn.device_id, json.dumps(message, ensure_ascii=False)[:300])
        return

    # ---- 4) 其余一律当作目标检测数据（兼容纯数组 / 无 type 字段）----
    # 先摘出缩略图（顺带从原始报文里删掉），再做归一化，避免 raw 里重复携带一份 base64
    thumb = pick_thumb(message)
    result = normalize_detection(message)
    detections = result["detections"]
    if not detections:
        # 区分两种情况：
        #   a) 报文里根本没带检测数组 → 报错，让设备端知道格式不对
        #   b) 明确上报了空数组（本帧确实没有目标）→ 这是有效数据，要继续广播，
        #      否则页面会一直停在上一帧，看起来像卡死。
        source = message if isinstance(message, dict) else {}
        has_array = isinstance(message, list) or any(
            isinstance(source.get(key), list) for key in ("detections", "objects", "results", "items")
        )
        if not has_array:
            await MANAGER.safe_send(conn.websocket, conn.send_lock, {
                "type": "error", "message": "未在消息中找到 detections/objects/results 数组", "timestamp": now_iso(),
            })
            return

    conn.detection_count += 1

    # 透传设备侧附加字段：模型名、帧尺寸、推理耗时、序号。
    # 帧尺寸必须保留——前端要按 frame.width/height 把像素框缩放到画布上。
    meta = message if isinstance(message, dict) else {}
    extra: Dict[str, Any] = {}
    for key in ("model", "seq", "infer_ms", "fps"):
        if key in meta:
            extra[key] = meta[key]
    frame_meta = meta.get("frame")
    if isinstance(frame_meta, dict):
        extra["frame"] = {"width": frame_meta.get("width"), "height": frame_meta.get("height")}

    # 下发给所有控制端：附带统一结构 + 原始 JSON，前端展示与调试都够用
    event: Dict[str, Any] = {
        "type": "detection",
        "device_id": conn.device_id,
        "device_name": conn.name or conn.device_id,
        "status": conn.status,
        "count": len(detections),
        "detections": detections,
        "raw": result["raw"],
        "timestamp": now_iso(),
        **extra,
    }
    # 缩略图单独挂载：前端拿它当底图，按 frame 尺寸把 bbox 画上去。
    # 没有 thumb（设备端 --thumb-width 0）时前端会退化成空白画布只画框。
    if thumb:
        event["thumb"] = thumb
    await MANAGER.broadcast(event)

    # 落库（默认关闭，开启后按队列批量写入，不影响实时性）
    DB.log_detection(conn.device_id, detections, result["raw"])

    # 每 100 帧打印一次，避免日志被高频帧刷爆
    if conn.detection_count % 100 == 1:
        top_class, top_conf = _top_object(detections)
        logger.info(
            "检测上报 | device_id=%s | 本帧 %d 个目标 | top=%s(%.2f) | 累计 %d 帧",
            conn.device_id, len(detections), top_class or "-", top_conf, conn.detection_count,
        )


# ---------------------------------------------------------------------------
# 业务处理：控制端下行（指令转发）
# ---------------------------------------------------------------------------


# 允许下发的指令白名单：新增指令只需在这里加一项，避免前端任意透传
# 说明：start/stop 与 start_detection/stop_detection 是同一语义的两套命名，
#       边缘客户端（edge_device_client.py）两套都认，前端按习惯用其中一套即可。
ALLOWED_COMMANDS = {
    "start",               # 启动目标检测（简写）
    "stop",                # 停止目标检测（简写）
    "start_detection",     # 启动目标检测
    "stop_detection",      # 停止目标检测
    "switch_model",        # 切换 YOLO 权重（params.model）
    "set_threshold",       # 调整置信度阈值
    "set_resolution",      # 调整推理分辨率
    "capture_snapshot",    # 抓拍一张
    "restart",             # 重启检测进程
    "ping",                # 链路探测
}


async def handle_dashboard_message(dash: DashboardConn, text: str) -> None:
    """
    处理控制端消息：
        {"type":"command","device_id":"jetson-nano","command":"start_detection","params":{...}}
        {"type":"list_devices"}
        {"type":"ping"}
    指令只转发给目标设备，并给控制端回执，便于页面做交互反馈。
    """
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        await MANAGER.safe_send(dash.websocket, dash.send_lock, {
            "type": "error", "message": "消息必须是合法 JSON", "timestamp": now_iso(),
        })
        return

    if not isinstance(message, dict):
        await MANAGER.safe_send(dash.websocket, dash.send_lock, {
            "type": "error", "message": "消息必须是 JSON 对象", "timestamp": now_iso(),
        })
        return

    msg_type = message.get("type", "command")

    # 查询在线设备（页面刷新时用得上）
    if msg_type == "list_devices":
        await MANAGER.safe_send(dash.websocket, dash.send_lock, {
            "type": "device_list", "devices": MANAGER.device_list(),
            "stats": MANAGER.stats(), "timestamp": now_iso(),
        })
        return

    if msg_type == "ping":
        await MANAGER.safe_send(dash.websocket, dash.send_lock, {
            "type": "pong", "timestamp": now_iso(),
        })
        return

    if msg_type != "command":
        await MANAGER.safe_send(dash.websocket, dash.send_lock, {
            "type": "error", "message": f"不支持的消息类型：{msg_type}", "timestamp": now_iso(),
        })
        return

    # ---- 指令校验 ----
    device_id = str(message.get("device_id") or "").strip()
    command = str(message.get("command") or "").strip()
    params = message.get("params") or {}
    request_id = str(message.get("request_id") or uuid.uuid4().hex[:12])

    if not command:
        await _reject_command(dash, request_id, device_id, "缺少 command 字段")
        return
    if command not in ALLOWED_COMMANDS:
        await _reject_command(dash, request_id, device_id, f"指令不在白名单内：{command}")
        return
    if not device_id:
        await _reject_command(dash, request_id, device_id, "缺少 device_id，无法确定目标设备")
        return

    conn = MANAGER.get_device(device_id)
    if conn is None:
        await _reject_command(dash, request_id, device_id, "目标设备不在线", code="device_offline")
        logger.warning("指令转发失败（设备离线） | device_id=%s | command=%s", device_id, command)
        return

    # ---- 转发给目标设备 ----
    payload = {
        "type": "command",
        "command": command,
        "params": params,
        "request_id": request_id,
        "issued_at": now_iso(),
    }
    ok = await MANAGER.send_to_device(device_id, payload)

    if not ok:
        await _reject_command(dash, request_id, device_id, "指令发送失败，设备刚刚断开", code="device_offline")
        return

    # 更新设备使用状态，并同步给所有控制端
    if command in ("start", "start_detection"):
        conn.status = "busy"
    elif command in ("stop", "stop_detection", "restart"):
        conn.status = "idle"

    logger.info(
        "指令已下发 | 控制端=%s | device_id=%s | command=%s | request_id=%s",
        dash.client, device_id, command, request_id,
    )

    await MANAGER.safe_send(dash.websocket, dash.send_lock, {
        "type": "command_status",
        "ok": True,
        "device_id": device_id,
        "command": command,
        "request_id": request_id,
        "device_status": conn.status,
        "timestamp": now_iso(),
    })
    await MANAGER.broadcast_device_online(conn)  # 状态变化后刷新设备卡片


async def _reject_command(dash: DashboardConn, request_id: str, device_id: str,
                          reason: str, code: str = "bad_request") -> None:
    """统一回执格式，前端只判断 ok 字段即可。"""
    await MANAGER.safe_send(dash.websocket, dash.send_lock, {
        "type": "command_status",
        "ok": False,
        "code": code,
        "device_id": device_id,
        "request_id": request_id,
        "message": reason,
        "timestamp": now_iso(),
    })


# ---------------------------------------------------------------------------
# 心跳看门狗：及时清理「TCP 已断但没发 close 帧」的僵尸连接
# ---------------------------------------------------------------------------


async def heartbeat_watchdog() -> None:
    """每 10 秒巡检一次，超时设备主动关闭并从连接池移除。"""
    while True:
        await asyncio.sleep(10)
        try:
            now = time.time()
            for conn in list(MANAGER.devices.values()):
                if now - conn.last_seen > CFG.heartbeat_timeout:
                    logger.warning(
                        "心跳超时，清理连接 | device_id=%s | 静默 %.0f 秒",
                        conn.device_id, now - conn.last_seen,
                    )
                    await MANAGER.close_device(conn, reason="heartbeat_timeout")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 巡检异常不能中断任务
            logger.error("心跳巡检异常：%s", exc)


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """独立运行时的启动 / 关闭钩子（复用 start_service / stop_service，避免两套逻辑）。"""
    logger.info("边缘接入服务启动中 … 监听 ws://%s:%d/ws/edge", CFG.host, CFG.port)
    await start_service()
    try:
        yield
    finally:
        await stop_service()


app = FastAPI(
    title="FusionLab AutoDrive 边缘设备接入服务",
    description="边缘主板 WebSocket 接入：设备鉴权、连接池、检测上报、指令转发、日志与 MySQL 落地",
    version="1.0.0",
    lifespan=lifespan,
)


# ------------------------------ 设备端 WebSocket ------------------------------
async def handle_device_ws(websocket: WebSocket) -> None:
    """
    边缘主板接入入口（可被独立 app 或 main.py 复用）。

    URL 示例：
        ws://192.168.1.20:8081/ws/edge?device_id=jetson-nano&token=fusionlab-edge-token
    可选参数（用于工作台设备卡片展示）：
        name / vendor / model / device_no
    """
    device_id = (websocket.query_params.get("device_id") or "").strip()[:64]
    token = websocket.query_params.get("token") or websocket.query_params.get("access_token") or ""
    remote = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"

    # 先 accept 再 close：这样客户端能拿到 1008 + 具体原因，联调时更容易定位问题。
    # （若想直接拒绝握手，可在 accept 之前 close，但客户端只能看到一个 403）
    await websocket.accept()

    if not device_id:
        logger.warning("拒绝接入：缺少 device_id | remote=%s", remote)
        await websocket.close(code=1008, reason="missing device_id")
        return
    if not verify_device_token(device_id, token):
        logger.warning("鉴权失败 | device_id=%s | remote=%s", device_id, remote)
        DB.log_event(device_id, "auth_failed", "token 校验不通过", remote)
        await websocket.send_text(json.dumps(
            {"type": "error", "code": "unauthorized", "message": "token 无效"}, ensure_ascii=False))
        await websocket.close(code=1008, reason="invalid token")
        return

    # ---- 组装连接对象并登记到连接池 ----
    conn = DeviceConn(
        device_id=device_id,
        websocket=websocket,
        name=(websocket.query_params.get("name") or device_id).strip()[:80],
        vendor=(websocket.query_params.get("vendor") or "").strip()[:80],
        model=(websocket.query_params.get("model") or "").strip()[:80],
        device_no=(websocket.query_params.get("device_no") or "").strip()[:64],
        remote_addr=remote,
    )
    try:
        old = await MANAGER.register_device(conn)
    except RuntimeError as exc:
        logger.warning("拒绝接入：%s", exc)
        await websocket.send_text(json.dumps(
            {"type": "error", "code": "duplicate", "message": str(exc)}, ensure_ascii=False))
        await websocket.close(code=1008, reason="device already online")
        return

    # 同一设备重复连接：先踢掉旧连接，避免一个 device_id 两条会话互相抢占
    if old is not None:
        logger.warning("设备重复接入，踢掉旧连接 | device_id=%s | old_remote=%s", device_id, old.remote_addr)
        try:
            await old.websocket.close(code=4001, reason="replaced by new connection")
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    logger.info(
        "设备已接入 | device_id=%s | name=%s | remote=%s | 当前在线 %d 台",
        device_id, conn.name, remote, len(MANAGER.devices),
    )
    DB.log_event(device_id, "online", f"name={conn.name}", remote)

    # 欢迎包：告诉设备服务端时间、心跳要求与可用指令，方便主板侧自检
    await MANAGER.safe_send(websocket, conn.send_lock, {
        "type": "welcome",
        "device_id": device_id,
        "server_time": now_iso(),
        "heartbeat_interval": 20,
        "heartbeat_timeout": CFG.heartbeat_timeout,
        "commands": sorted(ALLOWED_COMMANDS),
        "message": "已连接 FusionLab 边缘接入服务，上报检测数据请使用 type=detection",
    })
    await MANAGER.broadcast_device_online(conn)

    # ---- 主循环：一直读消息，直到断开 ----
    try:
        while True:
            text = await websocket.receive_text()
            await handle_device_message(conn, text)
    except WebSocketDisconnect as exc:
        # 需求 5：捕获断开事件，自动清理由 finally 完成
        logger.info(
            "设备断开 | device_id=%s | code=%s | 原因=%s | 累计消息 %d 条 / 检测 %d 帧",
            device_id, exc.code, exc.reason or "-", conn.message_count, conn.detection_count,
        )
        DB.log_event(device_id, "offline", f"code={exc.code} reason={exc.reason or '-'}", remote)
    except Exception as exc:  # noqa: BLE001 - 任何异常都要保证连接被清理
        logger.exception("设备会话异常 | device_id=%s | %s", device_id, exc)
        DB.log_event(device_id, "error", str(exc)[:500], remote)
    finally:
        # 关键：只有「当前连接仍是池中那条」时才会真正删除，避免误删重连后的新连接
        removed = await MANAGER.unregister_device(device_id, websocket)
        if removed is not None:
            logger.info("连接池已清理 | device_id=%s | 剩余在线 %d 台", device_id, len(MANAGER.devices))
            await MANAGER.broadcast_device_offline(removed, "disconnected")
        try:
            await websocket.close()
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass


@app.websocket("/ws/edge")
async def edge_device_ws(websocket: WebSocket) -> None:
    """独立运行（python edge_ws_server.py）时的设备端入口。"""
    await handle_device_ws(websocket)


# ------------------------------ 控制端 WebSocket ------------------------------
async def handle_panel_ws(websocket: WebSocket) -> None:
    """
    前端工作台接入入口：接收检测结果广播、下发控制指令。

    URL 示例：
        ws://192.168.1.20:8081/ws/dashboard?token=fusionlab-edge-token&client=browser-01
    """
    token = websocket.query_params.get("token") or websocket.query_params.get("access_token") or ""
    client = (websocket.query_params.get("client") or "dashboard").strip()[:64]
    remote = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"

    await websocket.accept()
    if not verify_dashboard_token(token):
        logger.warning("控制端鉴权失败 | client=%s | remote=%s", client, remote)
        await websocket.send_text(json.dumps(
            {"type": "error", "code": "unauthorized", "message": "token 无效"}, ensure_ascii=False))
        await websocket.close(code=1008, reason="invalid token")
        return

    dash = DashboardConn(websocket=websocket, client=client)
    await MANAGER.add_dashboard(dash)
    logger.info("控制端已连接 | client=%s | remote=%s | 当前控制端 %d 个", client, remote, len(MANAGER.dashboards))

    # 连接即推送一次完整快照，页面不必再多发一次请求
    await MANAGER.safe_send(websocket, dash.send_lock, {
        "type": "device_list",
        "devices": MANAGER.device_list(),
        "recent_devices": HISTORY.recent(),
        "stats": MANAGER.stats(),
        "commands": sorted(ALLOWED_COMMANDS),
        "timestamp": now_iso(),
    })

    try:
        while True:
            text = await websocket.receive_text()
            await handle_dashboard_message(dash, text)
    except WebSocketDisconnect as exc:
        logger.info("控制端断开 | client=%s | code=%s", client, exc.code)
    except Exception as exc:  # noqa: BLE001
        logger.exception("控制端会话异常 | client=%s | %s", client, exc)
    finally:
        await MANAGER.remove_dashboard(dash)
        try:
            await websocket.close()
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    """独立运行时的控制端入口。"""
    await handle_panel_ws(websocket)


# ------------------------------ HTTP 辅助接口 ------------------------------
class CommandRequest(BaseModel):
    """REST 下发指令的请求体（给不方便用 WebSocket 的页面 / 脚本用）。"""

    device_id: str = Field(..., description="目标边缘设备 ID")
    command: str = Field(..., description="指令名，需在服务端白名单内")
    params: Dict[str, Any] = Field(default_factory=dict, description="指令参数")


async def health_impl() -> Dict[str, Any]:
    """健康检查：部署后先用它确认服务活着。"""
    return {"status": "ok", "server_time": now_iso(), **MANAGER.stats()}


async def api_devices_impl() -> Dict[str, Any]:
    """查询当前在线设备列表 + 最近连接过的设备历史（前端轮询 / 调试用）。"""
    return {"devices": MANAGER.device_list(), "recent_devices": HISTORY.recent(),
            "stats": MANAGER.stats()}


async def api_command_impl(req: CommandRequest) -> Dict[str, Any]:
    """
    通过 HTTP 下发控制指令（内部走与 WebSocket 完全相同的转发逻辑）。
    返回 ok=False 时不抛 500，而是把原因交给调用方判断，便于前端统一处理。
    """
    if req.command not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail=f"指令不在白名单内：{req.command}")

    conn = MANAGER.get_device(req.device_id)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"设备 {req.device_id} 不在线")

    request_id = uuid.uuid4().hex[:12]
    ok = await MANAGER.send_to_device(req.device_id, {
        "type": "command",
        "command": req.command,
        "params": req.params,
        "request_id": request_id,
        "issued_at": now_iso(),
    })
    if not ok:
        raise HTTPException(status_code=502, detail="指令发送失败，设备连接可能已断开")

    if req.command in ("start", "start_detection"):
        conn.status = "busy"
    elif req.command in ("stop", "stop_detection", "restart"):
        conn.status = "idle"

    logger.info("HTTP 指令已下发 | device_id=%s | command=%s | request_id=%s",
                req.device_id, req.command, request_id)
    await MANAGER.broadcast_device_online(conn)
    return {"ok": True, "request_id": request_id, "device": conn.summary()}


@app.get("/health")
async def health() -> Dict[str, Any]:
    """独立运行时的健康检查入口。"""
    return await health_impl()


@app.get("/api/devices")
async def api_devices() -> Dict[str, Any]:
    """独立运行时的设备列表入口。"""
    return await api_devices_impl()


@app.post("/api/command")
async def api_command(req: CommandRequest) -> Dict[str, Any]:
    """独立运行时的 HTTP 指令入口。"""
    return await api_command_impl(req)


@app.get("/")
async def index() -> Dict[str, Any]:
    """根路径返回使用说明，方便现场用浏览器直接确认服务地址对不对。"""
    return {
        "service": "FusionLab AutoDrive 边缘设备接入服务",
        "device_ws": f"ws://<本机IP>:{CFG.port}/ws/edge?device_id=<设备ID>&token=<密钥>",
        "dashboard_ws": f"ws://<本机IP>:{CFG.port}/ws/dashboard?token=<控制端密钥>",
        "http_api": ["GET /health", "GET /api/devices", "POST /api/command"],
        "commands": sorted(ALLOWED_COMMANDS),
        **MANAGER.stats(),
    }


# ---------------------------------------------------------------------------
# 嵌入到平台（main.py 用这几个函数把边缘服务挂到同一个 FastAPI 实例上）
#   独立运行：python edge_ws_server.py  →  /ws/edge、/ws/dashboard
#   嵌入运行：main.edge_service.attach(app)  →  /ws/edge、/ws/edge/panel
# 两套入口复用同一份连接池，互不影响。
# ---------------------------------------------------------------------------


def configure(
    *,
    token: Optional[str] = None,
    device_tokens: Optional[Dict[str, str]] = None,
    dashboard_token: Optional[str] = None,
    dashboard_auth: Optional[Callable[[str], bool]] = None,
    heartbeat_timeout: Optional[float] = None,
    kick_duplicate: Optional[bool] = None,
) -> None:
    """在 import 之后、启动之前覆盖配置（None 表示保持原值）。"""
    if token is not None:
        CFG.default_token = token
    if device_tokens is not None:
        CFG.device_tokens = device_tokens
    if dashboard_token is not None:
        CFG.dashboard_token = dashboard_token
    if dashboard_auth is not None:
        CFG.dashboard_auth = dashboard_auth
    if heartbeat_timeout is not None:
        CFG.heartbeat_timeout = heartbeat_timeout
    if kick_duplicate is not None:
        CFG.kick_duplicate = kick_duplicate


def attach(
    app: FastAPI,
    *,
    device_path: str = "/ws/edge",
    panel_path: str = "/ws/edge/panel",
    api_prefix: str = "/api/edge",
) -> None:
    """
    把设备端 WS、控制端 WS 与 REST 接口注册到宿主 app。

    路径说明：
        device_path  边缘主板连接（device_id + token 鉴权）
        panel_path   浏览器工作台连接（登录会话鉴权）
        api_prefix   GET  {prefix}/devices、GET {prefix}/health、POST {prefix}/command

    注意：必须由宿主的 startup 钩子调用 start_service()，否则心跳看门狗不会运行，
    「TCP 已断但没发 close 帧」的僵尸连接不会被清理。
    """
    app.websocket(device_path)(handle_device_ws)
    app.websocket(panel_path)(handle_panel_ws)
    app.get(f"{api_prefix}/devices")(api_devices_impl)
    app.get(f"{api_prefix}/health")(health_impl)
    app.post(f"{api_prefix}/command")(api_command_impl)
    logger.info(
        "边缘接入服务已挂到宿主应用 | 设备端=%s | 控制端=%s | REST=%s/*",
        device_path, panel_path, api_prefix,
    )


_service_task: Optional[asyncio.Task] = None


async def start_service() -> None:
    """宿主 app 启动时调用：拉起 MySQL 写入器（若开启）与心跳看门狗。"""
    global _service_task
    await DB.start()
    if _service_task is None or _service_task.done():
        _service_task = spawn(heartbeat_watchdog(), "edge-heartbeat-watchdog")
    logger.info("边缘接入服务已就绪 | 当前在线设备 %d 台 | MySQL=%s",
                len(MANAGER.devices), "开启" if DB.available else "关闭")


async def stop_service() -> None:
    """宿主 app 关闭时调用：停止后台任务、断开所有设备连接。"""
    global _service_task
    if _service_task is not None:
        _service_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _service_task
        _service_task = None
    for conn in list(MANAGER.devices.values()):
        with contextlib.suppress(Exception):
            await conn.websocket.close(code=1001, reason="server shutdown")
    await DB.stop()
    logger.info("边缘接入服务已停止")


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------


def parse_device_tokens(raw: str) -> Dict[str, str]:
    """解析 --device-token "id1:token1,id2:token2"。"""
    result: Dict[str, str] = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise SystemExit(f"--device-token 格式错误：{item}（应为 device_id:token）")
        device_id, token = item.split(":", 1)
        result[device_id.strip()] = token.strip()
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FusionLab 边缘主板 WebSocket 接入服务",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # ---- 网络 ----
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，0.0.0.0 表示局域网可访问")
    parser.add_argument("--port", type=int, default=8081, help="监听端口")
    # ---- 鉴权 ----
    parser.add_argument("--token", default=os.environ.get("EDGE_TOKEN", "fusionlab-edge-token"),
                        help="设备全局密钥（未单独配置的设备使用）")
    parser.add_argument("--device-token", default=os.environ.get("EDGE_DEVICE_TOKENS", ""),
                        help='为设备单独配置密钥，格式 "jetson-nano:nano-secret,rk3588:rk-secret"')
    parser.add_argument("--dashboard-token", default=os.environ.get("EDGE_DASHBOARD_TOKEN", ""),
                        help="控制端密钥，留空则不校验控制端")
    # ---- 连接管理 ----
    parser.add_argument("--no-kick", action="store_true", help="重复 device_id 时拒绝新连接（默认踢旧连接）")
    parser.add_argument("--heartbeat-timeout", type=float, default=60.0, help="心跳超时秒数")
    # ---- 日志 ----
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default="logs/edge_ws_server.log", help="日志文件路径，传空字符串则只输出控制台")
    # ---- MySQL（可选）----
    parser.add_argument("--mysql", action="store_true", help="启用 MySQL 日志（设备事件 + 检测记录）")
    parser.add_argument("--mysql-host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.environ.get("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.environ.get("MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=os.environ.get("MYSQL_PASSWORD", "123456"))
    parser.add_argument("--mysql-database", default=os.environ.get("MYSQL_DATABASE", "fusionlab"))
    parser.add_argument("--mysql-queue", type=int, default=5000, help="MySQL 写入队列长度，满则丢弃")
    # ---- 其它 ----
    parser.add_argument("--reload", action="store_true", help="开发模式热重载（调试用）")
    return parser


def main() -> None:
    """解析参数 → 填充全局配置 → 启动 uvicorn。"""
    args = build_arg_parser().parse_args()

    CFG.host = args.host
    CFG.port = args.port
    CFG.default_token = args.token
    CFG.device_tokens = parse_device_tokens(args.device_token)
    CFG.dashboard_token = args.dashboard_token
    CFG.kick_duplicate = not args.no_kick
    CFG.heartbeat_timeout = args.heartbeat_timeout
    CFG.log_file = args.log_file or None
    CFG.log_level = args.log_level
    CFG.mysql_enabled = bool(args.mysql)
    CFG.mysql_host = args.mysql_host
    CFG.mysql_port = args.mysql_port
    CFG.mysql_user = args.mysql_user
    CFG.mysql_password = args.mysql_password
    CFG.mysql_database = args.mysql_database
    DB.queue = asyncio.Queue(maxsize=args.mysql_queue)

    setup_logging(CFG.log_level, CFG.log_file)
    logger.info("=" * 68)
    logger.info("FusionLab AutoDrive 边缘设备接入服务")
    logger.info("设备接入：ws://%s:%d/ws/edge?device_id=<ID>&token=<TOKEN>", args.host, args.port)
    logger.info("控制端  ：ws://%s:%d/ws/dashboard?token=<DASHBOARD_TOKEN>", args.host, args.port)
    logger.info("默认密钥：%s（答辩演示用，生产请用 --device-token 分设备下发）", CFG.default_token)
    logger.info("MySQL   ：%s", "已启用" if CFG.mysql_enabled else "未启用（仅日志）")
    logger.info("=" * 68)

    uvicorn.run(
        "edge_ws_server:app" if args.reload else app,
        host=CFG.host,
        port=CFG.port,
        reload=args.reload,
        log_level=CFG.log_level.lower(),
        ws_ping_interval=20,      # 协议层 ping，进一步保证长连接可探测
        ws_ping_timeout=20,
    )


if __name__ == "__main__":
    main()
