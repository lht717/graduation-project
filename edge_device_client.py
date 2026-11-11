#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FusionLab AutoDrive —— 边缘智能主板 WebSocket 客户端（Jetson / RK3588 / x86 通用）

数据流：
    USB 摄像头 ──▶ 采集线程（只保留最新帧）──▶ YOLO 推理（线程池，不阻塞事件循环）
                                                        │
                                                        ▼
                        检测结果 JSON ──WebSocket──▶ FastAPI 服务端 ──▶ 前端工作台
                                                        │
                                    控制指令 start / stop / switch_model
                                                        ▼
                                                    本客户端执行

对应需求：
    1. 主动连接 FastAPI WebSocket，URL 参数携带 device_id、token（含 name/vendor 便于工作台展示）；
    2. 读取 USB 摄像头，ultralytics YOLO 做目标检测；
    3. 检测结果（类别、置信度、框坐标）打包 JSON 上传；
    4. 监听后端指令，支持 start / stop / switch_model（同时兼容服务端白名单里的
       start_detection / stop_detection，以及 set_threshold / capture_snapshot / restart / ping）；
    5. 断线捕获异常 + 指数退避延时重连（1s → 2s → 4s … 最多 30s）；
    6. 依赖 websockets / opencv-python / ultralytics，注释完整，适合实物演示。

运行：
    # 实物演示（摄像头 0，默认 yolov8n.pt）
    python edge_device_client.py --server ws://192.168.1.20:8081/ws/edge \
        --device-id jetson-nano --token fusionlab-edge-token --camera 0

    # 无摄像头 / 无模型时联调链路（合成画面 + 假检测框，用于答辩前的通链自测）
    python edge_device_client.py --server ws://127.0.0.1:8081/ws/edge \
        --device-id jetson-nano --token fusionlab-edge-token --mock

    # 主板接显示器时本地预览检测框
    python edge_device_client.py --camera 0 --show

依赖安装：
    pip install websockets opencv-python ultralytics
    # Jetson 建议用 JetPack 自带 OpenCV；RK3588 建议装 rknn 版模型，思路相同，替换 Detector 即可
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import functools
import inspect
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import cv2
import numpy as np
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

try:  # websockets >= 15 才提供该异常，旧版本导入会失败
    from websockets.exceptions import InvalidProxy
except ImportError:  # pragma: no cover
    InvalidProxy = None  # type: ignore[assignment]

logger = logging.getLogger("edge-client")

# 版本兼容：JetPack 5 自带 Python 3.8，没有 asyncio.to_thread；
# create_task 的 name 参数在 3.7 也不支持。统一包一层，避免在板子上启动就报错。
async def run_in_thread(func, *args):
    """把阻塞调用（YOLO 推理 / 换模型）丢到线程池，事件循环继续收指令。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args))


def spawn(coro, name: str = ""):
    """创建后台任务；name 仅用于调试，老版本忽略。"""
    try:
        return asyncio.create_task(coro, name=name)
    except TypeError:
        return asyncio.create_task(coro)

# 断线类异常统一按「网络抖动」处理：只打一行告警，不打印 traceback
NETWORK_ERRORS: tuple = (ConnectionClosed, InvalidStatus, OSError, asyncio.TimeoutError, EOFError)
if InvalidProxy is not None:
    NETWORK_ERRORS = NETWORK_ERRORS + (InvalidProxy,)


# ---------------------------------------------------------------------------
# 配置：全部来自命令行，方便现场改参数不用改代码
# ---------------------------------------------------------------------------


@dataclass
class Config:
    server: str = "ws://127.0.0.1:8081/ws/edge"   # 服务端地址（不含查询参数）
    device_id: str = "jetson-nano"                # 设备唯一 ID，服务端连接池的 key
    token: str = "fusionlab-edge-token"           # 设备密钥，与服务端 --token 一致
    name: str = ""                                # 工作台展示名（可选）
    vendor: str = ""                              # 厂商（可选）
    device_no: str = ""                           # 设备编号（可选）

    camera: int = 0                               # USB 摄像头索引，/dev/video0 就是 0
    width: int = 640                              # 采集宽度
    height: int = 480                             # 采集高度

    model: str = "yolov8n.pt"                     # 初始权重（首次运行会自动下载）
    conf: float = 0.35                            # 置信度阈值
    iou: float = 0.45                             # NMS 的 IoU 阈值
    imgsz: int = 640                              # 推理输入尺寸
    device: str = ""                              # "cuda:0" / "cpu"，留空由 ultralytics 自动选
    fps: float = 5.0                              # 上报帧率上限（不要打满，否则服务端和前端都会被刷）
    autostart: bool = True                        # 连上就开始检测（实物演示免等指令；--no-autostart 可关）

    show: bool = False                            # 是否弹窗本地预览
    save_dir: str = "snapshots"                   # capture_snapshot 指令的保存目录
    mock: bool = False                            # 联调模式：合成画面 + 假检测

    # 缩略图回传：工作台的「边缘主板目标检测」面板用它当底图，把检测框叠在真实画面上。
    # 320 宽 / quality 65 时单帧约 15~25 KB，5fps 下约 100 KB/s，局域网完全够用；
    # 带宽紧张或只想看表格时用 --thumb-width 0 关掉。
    thumb_width: int = 320                        # 缩略图宽度（像素），0 = 不回传
    thumb_quality: int = 65                       # JPEG 质量，40~85 之间较平衡

    reconnect_min: float = 1.0                    # 首次重连等待秒数
    reconnect_max: float = 30.0                   # 退避上限
    log_level: str = "INFO"


CFG = Config()


def now_iso() -> str:
    """统一时间戳，便于和服务端日志对齐。"""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def encode_thumb(frame: np.ndarray, width: int, quality: int) -> str:
    """
    把当前帧压成小尺寸 JPEG 并转成 data URI，随检测结果一起上报。

    设计取舍：
      - 只传缩略图，不传原图。640×480 原图 JPEG 约 60~120 KB，5fps 就是 600 KB/s，
        局域网上行会被 YOLO 推理挤占；320 宽的缩略图约 15~25 KB，够看清目标位置。
      - 用 data URI（带 `data:image/jpeg;base64,` 前缀），前端可以直接赋给 Image.src，
        不需要再拼协议头，也不需要服务端做额外解码。
      - 宽高比保持原样，前端按 frame 尺寸映射 bbox 时不用额外换算比例。
    返回空串表示本次不回传（width<=0 或编码失败），此时前端退化为「只画框」。
    """
    if width <= 0 or frame is None or frame.size == 0:
        return ""
    try:
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return ""
        # 只在原图比目标更宽时才缩放，避免把小分辨率画面放大（放大既费流量又更糊）
        if w > width:
            target_h = max(1, int(round(h * width / float(w))))
            small = cv2.resize(frame, (width, target_h), interpolation=cv2.INTER_AREA)
        else:
            small = frame
        ok, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception as exc:  # noqa: BLE001  缩略图失败不能影响检测上报这条主链路
        logger.debug("缩略图编码失败，本帧改为不带图上报：%s", exc)
        return ""


def setup_logging(level: str = "INFO") -> None:
    """控制台日志：现场调试直接看终端即可，不需要落地文件（服务端才做持久化）。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # websockets 库在异常断链时会自己打一条带 traceback 的 ERROR 日志（如对端进程被杀时的 EOFError），
    # 实物演示时会把终端刷乱。断线原因由本客户端统一打日志，这里只保留致命错误。
    logging.getLogger("websockets").setLevel(logging.CRITICAL)


# ---------------------------------------------------------------------------
# 一、摄像头采集
# ---------------------------------------------------------------------------


class UsbCamera:
    """
    USB 摄像头采集器。

    为什么用独立线程：cv2.VideoCapture.read() 是阻塞调用，几毫秒到几十毫秒，
    直接放在 asyncio 事件循环里会卡住 WebSocket 收发。这里开一个后台线程持续读，
    只保留「最新一帧」（环形覆盖），推理慢的时候画面不会越积越旧。
    """

    def __init__(self, index: int, width: int, height: int) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._cap: Optional[cv2.VideoCapture] = None
        self._latest: Optional[np.ndarray] = None   # 最新一帧（BGR）
        self._lock = threading.Lock()               # 保护 _latest 的读写
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.frame_count = 0                        # 累计采集帧数
        self.fail_count = 0                         # 连续读取失败次数

    # ---------------- 打开设备 ----------------
    def open(self) -> bool:
        # Windows 用 DirectShow 打开更快；Linux（Jetson/RK3588）用 V4L2
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_V4L2
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened() and backend != 0:
            # 某些平台/驱动不认指定 backend，退回默认实现
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            logger.error("摄像头打开失败：index=%s（检查 USB 连接或 --camera 参数）", self.index)
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # 只缓存 1 帧，天然降低延迟
        # MJPG 编码在 USB2.0 下带宽更省，640x480@30fps 更稳（部分摄像头不支持会自动忽略）
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("摄像头已打开：index=%s 分辨率=%dx%d", self.index, real_w, real_h)

        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()
        return True

    # ---------------- 采集线程 ----------------
    def _loop(self) -> None:
        while self._running:
            cap = self._cap
            if cap is None:
                time.sleep(0.1)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                self.fail_count += 1
                # 连续失败（拔线/驱动挂掉）尝试重开，最多每 1 秒试一次
                if self.fail_count % 50 == 0:
                    logger.warning("摄像头连续读取失败 %d 次，尝试重新打开 …", self.fail_count)
                    cap.release()
                    time.sleep(0.5)
                    backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_V4L2
                    new_cap = cv2.VideoCapture(self.index, backend)
                    if new_cap.isOpened():
                        self._cap = new_cap
                        logger.info("摄像头已恢复")
                time.sleep(0.02)
                continue

            self.fail_count = 0
            self.frame_count += 1
            with self._lock:
                self._latest = frame

    # ---------------- 取帧 ----------------
    def read(self) -> Optional[np.ndarray]:
        """返回最新一帧的副本（copy 是必要的：推理/画框会改动数组，不能和采集线程抢同一块内存）。"""
        with self._lock:
            if self._latest is None:
                return None
            return self._latest.copy()

    def close(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("摄像头已释放（累计采集 %d 帧）", self.frame_count)


class MockCamera:
    """联调用的合成摄像头：生成带移动色块的画面，接口与 UsbCamera 完全一致。"""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.frame_count = 0

    def open(self) -> bool:
        logger.warning("【联调模式】使用合成画面代替真实摄像头")
        return True

    def read(self) -> Optional[np.ndarray]:
        self.frame_count += 1
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        # 一个随时间移动的方块，模拟画面里有运动目标
        x = int((self.width - 120) * (0.5 + 0.5 * np.sin(self.frame_count / 20.0)))
        cv2.rectangle(img, (x, 150), (x + 120, 270), (0, 200, 255), -1)
        cv2.putText(img, "MOCK CAMERA", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        return img

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# 二、YOLO 检测器
# ---------------------------------------------------------------------------


class YoloDetector:
    """
    ultralytics YOLO 封装。

    - 推理是同步 CPU/GPU 密集操作，调用方必须放到线程池（run_in_thread）里执行；
    - 换模型（switch_model）与推理共用一把线程锁，避免「模型正在换、推理还在用」的竞态；
    - 换模型失败时保留旧模型继续工作，不让一次误操作中断演示。
    """

    def __init__(self, weights: str, conf: float, iou: float, imgsz: int, device: str = "") -> None:
        self.weights = weights
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.device = device or None
        self._model = None
        self._lock = threading.Lock()
        self.model_name = os.path.basename(weights)

    # ---------------- 加载 ----------------
    def load(self) -> None:
        """首次加载（会触发权重下载，Jetson 上第一次可能要等十几秒）。"""
        from ultralytics import YOLO  # 延迟导入：没装 ultralytics 时也能先看 --help

        logger.info("正在加载模型 %s …", self.weights)
        t0 = time.time()
        model = YOLO(self.weights)
        # 预热一次：把 cuDNN / TensorRT 的初始化开销放到启动阶段，避免第一帧超时
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        model.predict(source=dummy, imgsz=self.imgsz, verbose=False, device=self.device)
        self._model = model
        logger.info("模型加载完成：%s（耗时 %.1fs）", self.weights, time.time() - t0)

    # ---------------- 推理 ----------------
    def infer(self, frame: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
        """
        对单帧做检测，返回 (检测列表, 推理耗时毫秒)。
        检测列表元素：{"class_id":int, "class_name":str, "confidence":float, "bbox":[x1,y1,x2,y2]}
        """
        with self._lock:
            model = self._model
            if model is None:
                return [], 0.0
            t0 = time.time()
            results = model.predict(
                source=frame,
                conf=self.conf,
                iou=self.iou,
                imgsz=self.imgsz,
                device=self.device,
                verbose=False,
            )
        cost_ms = (time.time() - t0) * 1000.0

        detections: List[Dict[str, Any]] = []
        if not results:
            return detections, cost_ms
        result = results[0]
        names = result.names or {}
        boxes = result.boxes
        if boxes is None:
            return detections, cost_ms

        # xyxy 是绝对像素坐标，直接给前端画框最方便（前端按 frame.width/height 缩放）
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy().astype(int)
        for i in range(len(xyxy)):
            detections.append({
                "class_id": int(clss[i]),
                "class_name": str(names.get(int(clss[i]), clss[i])),
                "confidence": round(float(confs[i]), 4),
                "bbox": [round(float(v), 1) for v in xyxy[i][:4]],
            })
        # 置信度高的排前面，前端「Top 目标」直接取第一条
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections, cost_ms

    # ---------------- 换模型 ----------------
    def switch_model(self, weights: str) -> str:
        """切换权重文件；成功返回新模型名，失败抛异常（调用方回执 ok=False）。"""
        from ultralytics import YOLO

        with self._lock:
            logger.info("切换模型：%s → %s …", self.model_name, weights)
            new_model = YOLO(weights)
            self._model = new_model          # 只有加载成功才替换，失败不影响旧模型
            self.weights = weights
            self.model_name = os.path.basename(weights)
        logger.info("模型切换完成：%s", self.model_name)
        return self.model_name

    def set_conf(self, conf: float) -> None:
        """调阈值：推理线程每帧都会读 self.conf，直接赋值即可。"""
        self.conf = max(0.01, min(float(conf), 0.99))


class MockDetector:
    """联调用假检测器：返回两个随时间移动的框，接口与 YoloDetector 一致。"""

    def __init__(self) -> None:
        self.conf = 0.35
        self.model_name = "mock-yolo"
        self._t = 0

    def load(self) -> None:
        logger.warning("【联调模式】使用模拟检测结果，不加载真实 YOLO 模型")

    def infer(self, frame: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
        self._t += 1
        h, w = frame.shape[:2]
        x = int((w - 120) * (0.5 + 0.5 * np.sin(self._t / 20.0)))
        return [
            {"class_id": 2, "class_name": "car", "confidence": 0.91, "bbox": [x, 150, x + 120, 270]},
            {"class_id": 0, "class_name": "person", "confidence": 0.78,
             "bbox": [w // 2, h // 3, w // 2 + 60, h - 40]},
        ], 8.0

    def switch_model(self, weights: str) -> str:
        logger.info("【联调模式】假装切换模型 → %s", weights)
        self.model_name = os.path.basename(weights)
        return self.model_name

    def set_conf(self, conf: float) -> None:
        self.conf = float(conf)


# ---------------------------------------------------------------------------
# 三、WebSocket 客户端主体
# ---------------------------------------------------------------------------


class EdgeClient:
    """边缘主板侧客户端：连接 / 采集推理上传 / 指令处理 / 断线重连。"""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.camera: Any = MockCamera(cfg.width, cfg.height) if cfg.mock else UsbCamera(cfg.camera, cfg.width, cfg.height)
        if cfg.mock:
            self.detector: Any = MockDetector()
        else:
            self.detector = YoloDetector(cfg.model, cfg.conf, cfg.iou, cfg.imgsz, cfg.device)

        self.running = False          # start / stop 控制：是否处于检测上报状态
        self._ws: Optional[Any] = None
        self._send_lock = asyncio.Lock()   # WebSocket 不允许并发 send，统一在这里串行化
        self._seq = 0                      # 上报序号，便于丢帧排查
        self._sent = 0                     # 累计成功上报帧数
        self._total_dets = 0               # 累计检测到的目标数
        self._thumb_bytes = 0              # 最近一帧缩略图的字节数（日志里看带宽用）
        self._last_frame: Optional[np.ndarray] = None
        self._shutdown = False

    # ---------------- URL 组装 ----------------
    def build_url(self) -> str:
        """device_id / token 放在查询参数里，与服务端握手鉴权逻辑对应。"""
        params: Dict[str, str] = {"device_id": self.cfg.device_id, "token": self.cfg.token}
        for key in ("name", "vendor", "device_no"):
            value = getattr(self.cfg, key)
            if value:
                params[key] = value
        sep = "&" if "?" in self.cfg.server else "?"
        return f"{self.cfg.server}{sep}{urlencode(params)}"

    def _safe_url(self) -> str:
        """日志里不打印明文 token。"""
        return self.cfg.server

    # ---------------- 发送封装 ----------------
    async def send_json(self, payload: Dict[str, Any]) -> bool:
        ws = self._ws
        if ws is None:
            return False
        text = json.dumps(payload, ensure_ascii=False)
        try:
            async with self._send_lock:
                await ws.send(text)
            return True
        except ConnectionClosed:
            return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("发送失败：%s", exc)
            return False

    # ---------------- 连接参数 ----------------
    @staticmethod
    def _connect_kwargs() -> Dict[str, Any]:
        """
        WebSocket 握手参数。
        注意 proxy=False：websockets >= 15 默认会读取系统代理环境变量，
        而边缘设备是要直连局域网里的服务端；若本机开了 HTTP_PROXY，
        连接会被代理拦下并报 "proxy rejected connection: HTTP 502"。
        这里显式关闭代理（旧版本没有该参数，用 inspect 判断后再传）。
        """
        kwargs: Dict[str, Any] = {
            "ping_interval": 20,   # 协议层心跳：20s 一次 ping，能及早发现半开连接
            "ping_timeout": 20,
            "open_timeout": 10,
            "max_queue": 64,
        }
        if "proxy" in inspect.signature(websockets.connect).parameters:
            kwargs["proxy"] = None
        return kwargs

    # ---------------- 单个连接会话 ----------------
    async def session(self) -> None:
        url = self.build_url()
        logger.info("正在连接服务端：%s（device_id=%s）", self._safe_url(), self.cfg.device_id)

        # 连接前记住「断线前是否在跑」，重连成功后恢复，避免每掉一次线都要重新点 start
        self.running = self.running or self.cfg.autostart

        async with websockets.connect(url, **self._connect_kwargs()) as ws:
            self._ws = ws
            logger.info("连接成功，等待服务端 welcome …")

            # 首包是服务端的 welcome（含心跳要求、可用指令），读到更好排错；读不到也不影响主流程
            try:
                hello_raw = await asyncio.wait_for(ws.recv(), timeout=5)
                hello = json.loads(hello_raw)
                if isinstance(hello, dict) and hello.get("type") == "welcome":
                    logger.info(
                        "服务端已就绪：server_time=%s 心跳间隔=%s 秒 可用指令=%s",
                        hello.get("server_time"), hello.get("heartbeat_interval"),
                        ",".join(hello.get("commands", [])),
                    )
            except (asyncio.TimeoutError, json.JSONDecodeError):
                logger.debug("未收到 welcome，直接进入主循环")

            sender = spawn(self._detect_loop(), "detect-loop")
            receiver = spawn(self._recv_loop(), "recv-loop")
            try:
                # 任意一个任务结束（断开 / 发送失败）就退出本次会话，交给外层重连
                done, pending = await asyncio.wait(
                    {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                # 把真实异常抛给外层，日志里才看得到断开原因
                for task in done:
                    exc = task.exception()
                    if exc is not None:
                        raise exc
            finally:
                self._ws = None
                # 注意：不重置 self.running，断线重连后继续按断线前的状态工作

    # ---------------- 采集 + 推理 + 上传 ----------------
    async def _detect_loop(self) -> None:
        interval = 1.0 / max(self.cfg.fps, 0.5)
        while True:
            t_start = time.time()

            if not self.running:
                # 未 start 时保持空转（只休眠，不推理），随时可以被指令唤醒
                await asyncio.sleep(0.05)
                continue

            frame = self.camera.read()
            if frame is None:
                logger.debug("暂无可用画面，等待摄像头 …")
                await asyncio.sleep(0.05)
                continue

            self._last_frame = frame
            # 关键：推理放到线程池，事件循环继续处理 WebSocket 指令
            detections, cost_ms = await run_in_thread(self.detector.infer, frame)

            self._seq += 1
            self._total_dets += len(detections)
            payload = {
                "type": "detection",
                "device_id": self.cfg.device_id,
                "model": getattr(self.detector, "model_name", self.cfg.model),
                "count": len(detections),
                "detections": detections,
                # 帧尺寸给前端换算框坐标用（不同摄像头分辨率不一样）
                "frame": {"width": int(frame.shape[1]), "height": int(frame.shape[0])},
                "infer_ms": round(cost_ms, 1),
                "seq": self._seq,
                "timestamp": now_iso(),
            }
            # 缩略图同样丢线程池：编码虽然只有几毫秒，但弱一点的板子上会卡住收指令的协程
            if self.cfg.thumb_width > 0:
                thumb = await run_in_thread(
                    encode_thumb, frame, self.cfg.thumb_width, self.cfg.thumb_quality
                )
                if thumb:
                    payload["thumb"] = thumb
                    self._thumb_bytes = len(thumb)
            ok = await self.send_json(payload)
            if not ok:
                logger.warning("上报失败，连接已不可用，退出本次会话等待重连")
                return

            self._sent += 1
            # 每 50 帧打一条摘要，避免 5fps 把终端刷满
            if self._sent % 50 == 1:
                top = detections[0] if detections else None
                logger.info(
                    "已上报 %d 帧 | 本帧 %d 目标 | 推理 %.0fms | 缩略图 %.1f KB | %s",
                    self._sent, len(detections), cost_ms, self._thumb_bytes / 1024.0,
                    f"top={top['class_name']}({top['confidence']:.2f})" if top else "无目标",
                )

            if self.cfg.show:
                self._preview(frame, detections)

            # 限速：保证「推理 + 上传 + 等待」总周期不小于 1/fps
            elapsed = time.time() - t_start
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)

    def _preview(self, frame: np.ndarray, detections: List[Dict[str, Any]]) -> None:
        """本地预览窗口（主板接 HDMI 显示器时用），无 GUI 环境会自动跳过。"""
        try:
            canvas = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(canvas, f"{det['class_name']} {det['confidence']:.2f}",
                            (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imshow("FusionLab Edge", canvas)
            cv2.waitKey(1)
        except Exception as exc:  # noqa: BLE001 - 无 GUI 时不影响主流程
            logger.debug("本地预览不可用：%s", exc)
            self.cfg.show = False

    # ---------------- 接收下行指令 ----------------
    async def _recv_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return
        async for raw in ws:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("收到非 JSON 消息，已忽略：%s", str(raw)[:120])
                continue
            if not isinstance(message, dict):
                continue
            try:
                await self._on_message(message)
            except Exception as exc:  # noqa: BLE001
                # 单条指令处理失败（例如抓拍磁盘满）不应把整条连接搞断，记日志后继续收下一帧指令
                logger.exception("处理下行消息失败（连接保持）：%s", exc)

    async def _on_message(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")

        if msg_type == "pong":
            return
        if msg_type == "command":
            await self._handle_command(message)
            return
        if msg_type == "error":
            logger.error("服务端返回错误：%s", message.get("message"))
            return
        logger.debug("忽略未知消息类型：%s", msg_type)

    async def _handle_command(self, message: Dict[str, Any]) -> None:
        """
        指令分发。兼容两套命名：
            start / start_detection      启动检测
            stop  / stop_detection       停止检测
            switch_model                 切换权重（params.model 或 params.name）
            set_threshold                调置信度（params.conf / params.value）
            capture_snapshot             保存当前帧到本地
            restart                      重置计数并重新开始
            ping                         链路探测
        """
        command = str(message.get("command") or "").strip()
        params = message.get("params") or {}
        request_id = message.get("request_id")

        logger.info("收到指令：%s | params=%s | request_id=%s", command, params, request_id)

        if command in ("start", "start_detection"):
            self.running = True
            await self._ack(command, request_id, ok=True, message="检测已启动",
                            extra={"state": "running"})
            return

        if command in ("stop", "stop_detection"):
            self.running = False
            await self._ack(command, request_id, ok=True,
                            message=f"检测已停止（本次共上报 {self._sent} 帧）",
                            extra={"state": "stopped"})
            return

        if command == "switch_model":
            weights = str(params.get("model") or params.get("name") or "").strip()
            if not weights:
                await self._ack(command, request_id, ok=False, message="缺少 params.model")
                return
            # 换模型可能耗时几秒（要读权重），必须放线程池，否则期间 WebSocket 会假死
            try:
                new_name = await run_in_thread(self.detector.switch_model, weights)
                await self._ack(command, request_id, ok=True, message=f"模型已切换为 {new_name}",
                                extra={"model": new_name})
            except Exception as exc:  # noqa: BLE001 - 权重不存在 / 格式不对
                logger.error("切换模型失败：%s", exc)
                await self._ack(command, request_id, ok=False, message=f"切换失败：{exc}")
            return

        if command == "set_threshold":
            value = params.get("conf", params.get("value", params.get("threshold")))
            try:
                self.detector.set_conf(float(value))
                await self._ack(command, request_id, ok=True,
                                message=f"置信度阈值已设为 {self.detector.conf:.2f}")
            except (TypeError, ValueError):
                await self._ack(command, request_id, ok=False, message="阈值参数不合法")
            return

        if command == "capture_snapshot":
            path = self._save_snapshot()
            await self._ack(command, request_id, ok=bool(path),
                            message="已保存抓拍" if path else "当前没有可用画面",
                            extra={"path": path} if path else None)
            return

        if command == "restart":
            self.running = False
            self._seq = 0
            self._sent = 0
            self.running = True
            await self._ack(command, request_id, ok=True, message="检测流程已重启")
            return

        if command == "ping":
            await self.send_json({"type": "pong", "device_id": self.cfg.device_id, "timestamp": now_iso()})
            return

        # 白名单内的未知指令，也要回执，避免前端一直转圈
        await self._ack(command, request_id, ok=False, message=f"本设备不支持指令：{command}")

    async def _ack(self, command: str, request_id: Optional[str], ok: bool = True,
                   message: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        """
        指令回执。服务端会把它转成 type=command_ack 广播给前端，
        页面据此显示「指令已执行 / 执行失败原因」。
        """
        payload: Dict[str, Any] = {
            "type": "command_ack",
            "device_id": self.cfg.device_id,
            "command": command,
            "request_id": request_id,
            "ok": ok,
            "message": message,
            "timestamp": now_iso(),
        }
        if extra:
            payload.update(extra)
        await self.send_json(payload)

    def _save_snapshot(self) -> Optional[str]:
        """把最近一帧存成 jpg，用于答辩演示「抓拍留证」。"""
        frame = self._last_frame
        if frame is None:
            return None
        os.makedirs(self.cfg.save_dir, exist_ok=True)
        name = f"{self.cfg.device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
        path = os.path.join(self.cfg.save_dir, name)
        # 注意：cv2.imwrite 返回单个 bool（不是 (ok, buf) 元组，后者是 imencode）
        ok = cv2.imwrite(path, frame)
        if not ok:
            logger.error("抓拍保存失败：%s", path)
            return None
        logger.info("抓拍已保存：%s", path)
        return path

    # ---------------- 断线重连主循环 ----------------
    async def run_forever(self) -> None:
        """外层守护：连上 → 跑会话 → 断了等一会儿 → 再连，指数退避。"""
        delay = self.cfg.reconnect_min
        attempt = 0

        while not self._shutdown:
            started_at = time.time()
            attempt += 1
            try:
                if attempt > 1:
                    logger.info("第 %d 次重连尝试 …", attempt - 1)
                await self.session()
                logger.warning("与服务端的会话已结束（正常关闭或对端下线）")
            except InvalidStatus as exc:
                # 握手阶段被拒（例如 404 路径错、token 被服务端直接 403）
                logger.error("握手被服务端拒绝：%s（检查 --server 路径与 token）", exc)
            except ConnectionClosed as exc:
                logger.warning("连接断开：code=%s reason=%s", exc.code, exc.reason or "-")
            except NETWORK_ERRORS as exc:
                # 包括 EOFError（对端进程被杀）、代理拦截、连接被拒等
                logger.warning("连接不可用：%s（服务端未启动 / 局域网不通 / 代理拦截）", exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 任何异常都不能让进程退出
                logger.exception("会话异常：%s", exc)

            if self._shutdown:
                break

            # 会话稳定运行超过 30 秒，视为「连上过」，退避时间归零
            if time.time() - started_at > 30:
                delay = self.cfg.reconnect_min
                attempt = 0

            logger.info("%.1f 秒后重连（device_id=%s）", delay, self.cfg.device_id)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            delay = min(delay * 2, self.cfg.reconnect_max)

    # ---------------- 资源释放 ----------------
    def startup(self) -> bool:
        """打开摄像头 + 加载模型；任一步失败直接退出，避免带着半残状态上演示台。"""
        if not self.camera.open():
            return False
        try:
            self.detector.load()
        except ImportError:
            logger.error("未安装 ultralytics：pip install ultralytics（或先用 --mock 联调链路）")
            self.camera.close()
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("模型加载失败：%s", exc)
            self.camera.close()
            return False
        return True

    def shutdown(self) -> None:
        self._shutdown = True
        self.running = False
        self.camera.close()
        with contextlib.suppress(Exception):
            cv2.destroyAllWindows()
        logger.info("客户端已退出（累计上报 %d 帧 / %d 个目标）", self._sent, self._total_dets)


# ---------------------------------------------------------------------------
# 四、命令行入口
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="FusionLab 边缘智能主板 WebSocket 客户端（USB 摄像头 + YOLO 检测上传）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # 连接
    p.add_argument("--server", default=CFG.server, help="服务端 WebSocket 地址（不带查询参数）")
    p.add_argument("--device-id", default=CFG.device_id, help="设备唯一 ID，需在服务端白名单/连接池中唯一")
    p.add_argument("--token", default=os.environ.get("EDGE_TOKEN", CFG.token), help="设备密钥")
    p.add_argument("--name", default="", help="工作台展示名，如 Jetson Nano")
    p.add_argument("--vendor", default="", help="厂商，如 NVIDIA")
    p.add_argument("--device-no", default="", help="设备编号，如 Edge-01")
    # 摄像头
    p.add_argument("--camera", type=int, default=CFG.camera, help="USB 摄像头索引（/dev/video0 对应 0）")
    p.add_argument("--width", type=int, default=CFG.width)
    p.add_argument("--height", type=int, default=CFG.height)
    p.add_argument("--show", action="store_true", help="弹窗本地预览检测结果")
    # 模型
    p.add_argument("--model", default=CFG.model, help="初始权重文件，如 yolov8n.pt")
    p.add_argument("--conf", type=float, default=CFG.conf, help="置信度阈值")
    p.add_argument("--iou", type=float, default=CFG.iou, help="NMS IoU 阈值")
    p.add_argument("--imgsz", type=int, default=CFG.imgsz, help="推理输入尺寸")
    p.add_argument("--device", default="", help='推理设备："cuda:0" / "cpu"，留空自动选')
    p.add_argument("--fps", type=float, default=CFG.fps, help="上报帧率上限")
    p.add_argument("--no-autostart", dest="autostart", action="store_false",
                   help="连接后不自动开始检测，等待前端下发 start 指令")
    # 其它
    p.add_argument("--save-dir", default=CFG.save_dir, help="capture_snapshot 抓拍保存目录")
    p.add_argument("--mock", action="store_true", help="联调模式：合成画面 + 假检测（无摄像头/无权重时用）")
    # 缩略图：工作台用它在画面上叠检测框
    p.add_argument("--thumb-width", type=int, default=CFG.thumb_width,
                   help="回传缩略图宽度（像素），0 表示只传检测 JSON 不带图")
    p.add_argument("--thumb-quality", type=int, default=CFG.thumb_quality,
                   help="缩略图 JPEG 质量，越大越清晰也越费流量")
    p.add_argument("--reconnect-min", type=float, default=CFG.reconnect_min, help="首次重连等待秒数")
    p.add_argument("--reconnect-max", type=float, default=CFG.reconnect_max, help="重连退避上限秒数")
    p.add_argument("--log-level", default=CFG.log_level, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # 把参数灌进全局配置（dataclass 集中管理，避免到处传参）
    for key, value in vars(args).items():
        setattr(CFG, key, value)

    setup_logging(CFG.log_level)
    logger.info("=" * 66)
    logger.info("FusionLab 边缘客户端 | device_id=%s | 服务端=%s", CFG.device_id, CFG.server)
    logger.info("摄像头=%s | 模型=%s | 上报 %.1f fps | 模式=%s",
                CFG.camera, CFG.model, CFG.fps, "联调(mock)" if CFG.mock else "实物")
    logger.info("缩略图=%s（工作台据此在画面上叠加检测框）",
                f"{CFG.thumb_width}px / q{CFG.thumb_quality}" if CFG.thumb_width > 0 else "关闭")
    logger.info("=" * 66)

    client = EdgeClient(CFG)
    if not client.startup():
        return 1

    try:
        asyncio.run(client.run_forever())
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在退出 …")
    finally:
        client.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
