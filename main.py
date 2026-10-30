import asyncio
import json
import queue
import numpy as np
import cv2
import carla
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from typing import Dict, List
from pathlib import Path
import uvicorn
import onnxruntime as ort
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------- CARLA 初始化 ----------
client = carla.Client('10.46.36.177', 2000)
client.set_timeout(10.0)
world = client.get_world()
blueprint_library = world.get_blueprint_library()

# ---------- ONNX 模型管理 ----------
# V0.6.4：模型不再写死。models/ 目录中的 ONNX 可由网页上传、列出并选择。
# 当前算法流水线仍分为 UFLD（车道线）与 YOLO（目标检测）两个槽位，因此新模型需与对应
# 的预处理/后处理接口兼容。
ufld_session = None
ufld_input_name = None
yolo_session = None
yolo_input_name = None
active_models = {"ufld": None, "yolo": None}

def _safe_model_name(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name or name != filename.strip():
        raise HTTPException(status_code=400, detail="模型文件名不合法")
    if not name.lower().endswith(".onnx"):
        raise HTTPException(status_code=400, detail="仅支持 .onnx 模型文件")
    return name

def _create_onnx_session(filename: str):
    name = _safe_model_name(filename)
    path = MODELS_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"模型不存在：{name}")
    try:
        return ort.InferenceSession(str(path)), name
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"ONNX 模型加载失败：{exc}")

def _load_initial_models():
    global ufld_session, ufld_input_name, yolo_session, yolo_input_name
    defaults = {"ufld": "ufld_culane.onnx", "yolo": "yolov5su.onnx"}
    for role, filename in defaults.items():
        path = MODELS_DIR / filename
        if not path.exists():
            print(f"[MODEL] default {role} model not found: {path}")
            continue
        try:
            session = ort.InferenceSession(str(path))
            if role == "ufld":
                ufld_session = session
                ufld_input_name = session.get_inputs()[0].name
            else:
                yolo_session = session
                yolo_input_name = session.get_inputs()[0].name
            active_models[role] = filename
            print(f"[MODEL] loaded default {role}: {filename}")
        except Exception as exc:
            print(f"[MODEL] failed to load {filename}: {exc}")

_load_initial_models()

# ---------- 会话管理 ----------
class ClientSession:
    def __init__(self):
        self.vehicle = None
        self.front_camera = None      # 前方摄像头（第一人称）
        self.rear_camera = None       # 后上方摄像头（第三人称）
        self.front_queue = queue.Queue(maxsize=5)   # 前方图像队列（线程安全）
        self.rear_queue = queue.Queue(maxsize=5)    # 后上方图像队列
        self.driving = False
        self.walkers = []          # 存储行人的 Actor
        self.walker_controllers = []  # 存储行人的控制器

sessions: Dict[int, ClientSession] = {}
session_counter = 0

# ---------- 获取可用车辆蓝图 ----------
def get_vehicle_blueprints():
    vehicles = blueprint_library.filter('vehicle.*')
    result = []
    for bp in vehicles:
        # 简单解析品牌和型号，例如 "vehicle.tesla.model3" -> Tesla Model3
        parts = bp.id.split('.')
        if len(parts) == 3:
            brand = parts[1].capitalize()
            model = parts[2].capitalize()
            display_name = f"{brand} {model}"
        else:
            display_name = bp.id
        result.append({
            "id": bp.id,
            "name": display_name
        })
    return result

def spawn_pedestrians(world, vehicle, num=5, radius=30.0, max_attempts=10):
    """
    在车辆周围生成行人，逐个尝试并处理碰撞。
    返回 (walker_actors, controller_actors)
    """
    walker_bps = world.get_blueprint_library().filter('walker.pedestrian.*')
    if not walker_bps:
        print("没有找到行人蓝图")
        return [], []

    controller_bp = world.get_blueprint_library().find('controller.ai.walker')
    if not controller_bp:
        print("没有找到行人控制器蓝图")
        return [], []

    vehicle_loc = vehicle.get_location()
    walker_actors = []
    controller_actors = []

    for _ in range(num):
        walker = None
        for attempt in range(max_attempts):
            # 尝试在车辆附近随机导航点
            location = world.get_random_location_from_navigation()
            if location is not None and location.distance(vehicle_loc) <= radius:
                spawn_point = carla.Transform(location + carla.Location(z=0.5))  # 稍微抬高避免嵌入地面
            else:
                # 导航点不可用或太远，则在车辆前方随机偏移
                angle = np.random.uniform(0, 2 * np.pi)
                offset = carla.Location(x=radius * np.cos(angle), y=radius * np.sin(angle), z=0.5)
                spawn_point = carla.Transform(vehicle_loc + offset)

            # 逐个生成
            bp = np.random.choice(walker_bps)
            if bp.has_attribute('is_invincible'):
                bp.set_attribute('is_invincible', 'false')
            walker = world.try_spawn_actor(bp, spawn_point)
            if walker is not None:
                break  # 生成成功

        if walker is None:
            print("行人生成失败：尝试多次仍碰撞")
            continue

        # 为该行人生成控制器
        controller = world.try_spawn_actor(controller_bp, carla.Transform(), walker)
        if controller is None:
            walker.destroy()
            print("行人控制器生成失败")
            continue

        # 启动AI
        controller.start()
        dest = world.get_random_location_from_navigation()
        if dest is not None:
            controller.go_to_location(dest)
        controller.set_max_speed(1.0 + np.random.random() * 1.0)

        walker_actors.append(walker)
        controller_actors.append(controller)

    print(f"成功生成行人 {len(walker_actors)} 个")
    return walker_actors, controller_actors

# ---------- 摄像头回调（同步） ----------
# def make_camera_callback(session_id, camera_type):
#     def camera_callback(image):
#         session = sessions.get(session_id)
#         if session and session.driving:
#             # 转换图像
#             array = np.frombuffer(image.raw_data, dtype=np.uint8)
#             array = array.reshape((image.height, image.width, 4))[:, :, :3]  # BGRA -> BGR
#             # 可在此处添加车道线检测等算法
#             ret, jpeg = cv2.imencode('.jpg', array, [cv2.IMWRITE_JPEG_QUALITY, 70])
#             if ret:
#                 data = jpeg.tobytes()
#                 if camera_type == 'front':
#                     q = session.front_queue
#                 else:
#                     q = session.rear_queue
#                 try:
#                     q.put_nowait(data)
#                 except queue.Full:
#                     try:
#                         q.get_nowait()
#                         q.put_nowait(data)
#                     except Exception:
#                         pass
#     return camera_callback
def make_camera_callback(session_id, camera_type):
    def camera_callback(image):
        session = sessions.get(session_id)
        if session and session.driving:
            # 帧计数（使用函数属性保存状态）
            if not hasattr(camera_callback, "frame_count"):
                camera_callback.frame_count = 0
            camera_callback.frame_count += 1
            if camera_callback.frame_count % 4 != 0:
                # 奇数帧只发送原始图像，不进行检测
                # 仍需要编码并发送
                pass
            else:
                # 偶数帧执行检测
                outputs = None
                # 转换图像：BGRA -> BGR
                array = np.frombuffer(image.raw_data, dtype=np.uint8)
                array = array.reshape((image.height, image.width, 4))[:, :, :3]
                array = array.copy()

                # 对前方摄像头进行 UFLD 车道线检测
                if camera_type == 'front':
                    # UFLD 车道线检测（若已加载对应模型）
                    if ufld_session is not None and ufld_input_name:
                        try:
                            input_tensor = preprocess_ufld(array)
                            outputs = ufld_session.run(None, {ufld_input_name: input_tensor})
                            culane_row_anchor = [121, 131, 141, 150, 160, 170, 180, 189, 199, 209,
                                                219, 228, 238, 248, 258, 267, 277, 287]
                            lanes = postprocess_ufld(outputs[0], (image.height, image.width),
                                                     culane_row_anchor, griding_num=200, conf_thresh=10.0)
                            array = draw_ufld_lanes(array, lanes, color=(0, 255, 0), thickness=3)
                        except Exception as e:
                            print(f"UFLD inference error: {e}")

                    # YOLO 目标检测（若已加载对应模型）
                    if yolo_session is not None and yolo_input_name:
                        try:
                            yolo_input_tensor, r, left, top = preprocess_yolo(array)
                            yolo_outputs = yolo_session.run(None, {yolo_input_name: yolo_input_tensor})
                            detections = postprocess_yolo(yolo_outputs, r, left, top,
                                                        (image.height, image.width),
                                                        conf_thres=0.45, iou_thres=0.45)
                            array = draw_yolo_detections(array, detections)
                        except Exception as e:
                            print(f"YOLO inference error: {e}")
            

            # 编码为 JPEG 并发送
            ret, jpeg = cv2.imencode('.jpg', array, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                data = jpeg.tobytes()
                if camera_type == 'front':
                    q = session.front_queue
                else:
                    q = session.rear_queue
                try:
                    q.put_nowait(data)
                except queue.Full:
                    try:
                        q.get_nowait()
                        q.put_nowait(data)
                    except Exception:
                        pass
            
    return camera_callback

# ---------- YOLO 预处理 ----------
def letterbox(img, new_shape=(640, 640), color=(114, 114, 114)):
    """保持长宽比缩放并填充到正方形"""
    shape = img.shape[:2]  # 高, 宽
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw = (new_shape[1] - new_unpad[0]) / 2
    dh = (new_shape[0] - new_unpad[1]) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return img, r, left, top

def preprocess_yolo(img_bgr):
    """输入 BGR 图像，输出 YOLO 输入张量及缩放信息"""
    img, r, left, top = letterbox(img_bgr, (640, 640))
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_tensor = img_rgb.transpose(2, 0, 1)[None, :, :, :].astype(np.float32) / 255.0
    return img_tensor, r, left, top

def nms(boxes, scores, iou_thres):
    """
    简单 NMS，输入 boxes 为 [[x1,y1,x2,y2],...], scores 为 [score,...]
    返回保留的框索引列表
    """
    if len(boxes) == 0:
        return []

    # 按分数降序排序
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep = []

    while order:
        current = order[0]
        keep.append(current)
        if len(order) == 1:
            break
        rest = order[1:]
        filtered = []
        for idx in rest:
            # 计算 IoU
            x1 = max(boxes[current][0], boxes[idx][0])
            y1 = max(boxes[current][1], boxes[idx][1])
            x2 = min(boxes[current][2], boxes[idx][2])
            y2 = min(boxes[current][3], boxes[idx][3])
            inter_w = max(0, x2 - x1)
            inter_h = max(0, y2 - y1)
            inter = inter_w * inter_h
            area1 = (boxes[current][2] - boxes[current][0]) * (boxes[current][3] - boxes[current][1])
            area2 = (boxes[idx][2] - boxes[idx][0]) * (boxes[idx][3] - boxes[idx][1])
            iou = inter / float(area1 + area2 - inter + 1e-6)
            if iou <= iou_thres:
                filtered.append(idx)
        order = filtered
    return keep

# ---------- YOLO 后处理 ----------
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair',
    'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote',
    'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book',
    'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]

INTERESTED_CLASSES = {0, 2, 5, 7, 9, 11}  # person, car, bus, truck, traffic light, stop sign

def postprocess_yolo(outputs, r, left, top, original_shape, conf_thres=0.25, iou_thres=0.45):
    predictions = outputs[0]  # (84, 8400)
    predictions = predictions.T  # (8400, 84)

    boxes = []
    scores = []
    class_ids = []

    for pred in predictions:
        cx, cy, w, h = pred[:4]
        class_scores = pred[4:]
        class_id = int(np.argmax(class_scores))
        conf = float(class_scores[class_id])
        if conf < conf_thres:
            continue

        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2

        # 映射回原始图像坐标
        x1 = (x1 - left) / r
        y1 = (y1 - top) / r
        x2 = (x2 - left) / r
        y2 = (y2 - top) / r

        # 限制范围
        x1 = max(0, min(x1, original_shape[1]))
        y1 = max(0, min(y1, original_shape[0]))
        x2 = max(0, min(x2, original_shape[1]))
        y2 = max(0, min(y2, original_shape[0]))

        boxes.append([x1, y1, x2, y2])
        scores.append(conf)
        class_ids.append(class_id)

    # 自定义 NMS（纯 Python 实现，避免类型问题）
    keep_indices = nms(boxes, scores, iou_thres)

    detections = []
    for i in keep_indices:
        detections.append({
            'bbox': boxes[i],
            'score': scores[i],
            'class_id': class_ids[i]
        })
    return detections

def draw_yolo_detections(img_bgr, detections):
    """在图像上绘制检测框和标签"""
    for det in detections:
        class_id = det['class_id']
        if class_id not in INTERESTED_CLASSES:
            continue
        x1, y1, x2, y2 = det['bbox']
        conf = det['score']
        label = f"{COCO_CLASSES[class_id]}: {conf:.2f}"
        # 画框
        cv2.rectangle(img_bgr, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        # 画标签背景
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img_bgr, (int(x1), int(y1) - th - 4), (int(x1) + tw, int(y1)), (0, 255, 0), -1)
        cv2.putText(img_bgr, label, (int(x1), int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    return img_bgr

# UFLD 预处理
def preprocess_ufld(img_bgr):
    """
    输入 BGR 图像 (H, W, 3)，输出预处理后的张量 (1, 3, 288, 800)
    """
    # 调整尺寸到 288x800 (高288，宽800)
    img_resized = cv2.resize(img_bgr, (800, 288))
    # BGR -> RGB
    img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
    # 归一化
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    img_normalized = (img_rgb.astype(np.float32) / 255.0 - mean) / std
    # HWC -> CHW，增加 batch 维度
    img_tensor = img_normalized.transpose(2, 0, 1)[None, :, :, :]
    return img_tensor.astype(np.float32)

# UFLD 后处理：从输出 logits 中提取车道线点
def postprocess_ufld(output, original_shape, row_anchor, griding_num=200, conf_thresh=5.0):
    out = output[0]  # (201, 18, 4)
    out = out[:griding_num, :, :]  # (200, 18, 4)
    img_h, img_w = original_shape[:2]

    # 缩放因子：模型输入为 288x800
    scale_y = img_h / 288.0
    scale_x = img_w / 800.0

    lanes = []
    for lane_idx in range(out.shape[2]):
        lane_points = []
        for row_idx in range(out.shape[1]):
            y_model = row_anchor[row_idx]
            y = y_model * scale_y
            scores = out[:, row_idx, lane_idx]
            max_idx = np.argmax(scores)
            max_score = scores[max_idx]
            if max_score < conf_thresh:
                continue
            x_model = (max_idx + 0.5) * (800.0 / griding_num)
            x = x_model * scale_x
            lane_points.append((x, y, float(max_score)))
        if len(lane_points) > 2:
            lanes.append(lane_points)
    return lanes

# 绘制车道线
def draw_ufld_lanes(img_bgr, lanes, color=(0, 255, 0), thickness=3):
    # 按点数从多到少排序，只取前 2 条
    lanes = sorted(lanes, key=lambda l: len(l), reverse=True)[:2]
    for lane in lanes:
        if len(lane) < 2:
            continue
        # 提取 x, y 并做简单平滑（例如滑动平均）
        pts = np.array([(p[0], p[1]) for p in lane], dtype=np.float32)
        # 对 x 坐标进行平滑
        window = 5
        if len(pts) >= window:
            kernel = np.ones(window) / window
            pts[:, 0] = np.convolve(pts[:, 0], kernel, mode='same')
        pts = pts.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img_bgr, [pts], False, color, thickness)
    return img_bgr

# ---------- 图像发送任务（每个摄像头独立） ----------
async def image_sender(websocket: WebSocket, session_id: int, camera_type: str):
    session = sessions[session_id]
    loop = asyncio.get_event_loop()
    # 选择对应的队列
    if camera_type == 'front':
        q = session.front_queue
        prefix = b'\x00'  # 二进制前缀标识：0 表示前方摄像头
    else:
        q = session.rear_queue
        prefix = b'\x01'  # 1 表示后上方摄像头

    while True:
        if session.driving:
            # 阻塞获取图像（在默认线程池中执行，避免卡住事件循环）
            image_bytes = await loop.run_in_executor(None, q.get)
            # 发送：前缀 + JPEG数据
            await websocket.send_bytes(prefix + image_bytes)
        else:
            await asyncio.sleep(0.01)

# ---------- 仪表盘数据发送任务 ----------
async def status_sender(websocket: WebSocket, session_id: int):
    session = sessions[session_id]
    while True:
        if session.vehicle and session.driving:
            vehicle = session.vehicle
            # 获取速度 (m/s)，转换为 km/h
            velocity = vehicle.get_velocity()
            speed_kmh = 3.6 * (velocity.x**2 + velocity.y**2 + velocity.z**2)**0.5
            print(f"Speed: {speed_kmh}")
            # 获取加速度
            acceleration = vehicle.get_acceleration()
            accel_mag = (acceleration.x**2 + acceleration.y**2 + acceleration.z**2)**0.5
            # 获取控制（油门）
            control = vehicle.get_control()
            throttle = control.throttle
            # 获取朝向（yaw 角度）
            transform = vehicle.get_transform()
            yaw = transform.rotation.yaw
            # 归一化到 0~360
            yaw = yaw % 360

            status = {
                "speed": round(speed_kmh, 1),
                "acceleration": round(accel_mag, 2),
                "throttle": round(throttle, 2),
                "yaw": round(yaw, 1)
            }
            await websocket.send_text(json.dumps({"type": "status", "data": status}))

            # status = {"speed": 30.0, "acceleration": 1.0, "throttle": 0.5, "yaw": 45.0}
            # await websocket.send_text(json.dumps({"type": "status", "data": status}))

        await asyncio.sleep(0.1)  # 10 Hz

# ---------- 模型管理 API ----------
@app.get("/api/models")
async def list_models():
    items = []
    for path in sorted(MODELS_DIR.glob("*.onnx"), key=lambda p: p.name.lower()):
        stat = path.stat()
        items.append({
            "name": path.name,
            "size": stat.st_size,
            "active_roles": [role for role, name in active_models.items() if name == path.name],
        })
    return {"models": items, "active": active_models}

@app.post("/api/models/upload")
async def upload_model(request: Request, filename: str):
    name = _safe_model_name(filename)
    target = MODELS_DIR / name
    if target.exists():
        raise HTTPException(status_code=409, detail="文件名已存在，请修改上传模型的文件名")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    # 原型阶段设置 500MB 上限，避免误上传超大文件占满磁盘
    if len(data) > 500 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="模型文件超过 500MB 上限")
    target.write_bytes(data)
    # 只做 ONNX 可解析性检查；不自动绑定算法角色
    try:
        test_session = ort.InferenceSession(str(target))
        input_info = [{"name": x.name, "shape": x.shape, "type": x.type} for x in test_session.get_inputs()]
        output_info = [{"name": x.name, "shape": x.shape, "type": x.type} for x in test_session.get_outputs()]
    except Exception as exc:
        
        if target.exists():
            target.unlink()
        raise HTTPException(status_code=400, detail=f"文件不是可加载的 ONNX 模型：{exc}")
    return {"ok": True, "name": name, "size": len(data), "inputs": input_info, "outputs": output_info}

@app.post("/api/models/load")
async def load_models(request: Request):
    global ufld_session, ufld_input_name, yolo_session, yolo_input_name
    # 为避免运行中的 CARLA 传感器线程与模型切换并发，先要求停止行驶。
    if any(s.driving for s in sessions.values()):
        raise HTTPException(status_code=409, detail="请先停止实验运行，再切换模型")
    payload = await request.json()
    ufld_name = payload.get("ufld_model")
    yolo_name = payload.get("yolo_model")

    new_ufld_session = ufld_session
    new_ufld_input = ufld_input_name
    new_yolo_session = yolo_session
    new_yolo_input = yolo_input_name
    new_active = dict(active_models)

    if ufld_name:
        session, name = _create_onnx_session(ufld_name)
        new_ufld_session = session
        new_ufld_input = session.get_inputs()[0].name
        new_active["ufld"] = name
    if yolo_name:
        session, name = _create_onnx_session(yolo_name)
        new_yolo_session = session
        new_yolo_input = session.get_inputs()[0].name
        new_active["yolo"] = name

    # 所有待加载模型均成功后再一次性切换，避免部分更新。
    ufld_session = new_ufld_session
    ufld_input_name = new_ufld_input
    yolo_session = new_yolo_session
    yolo_input_name = new_yolo_input
    active_models.update(new_active)
    return {"ok": True, "active": active_models}

# ---------- WebSocket 端点 ----------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global session_counter
    await websocket.accept()
    session_id = session_counter
    session_counter += 1
    session = ClientSession()
    sessions[session_id] = session

    # 启动图像发送任务（两个摄像头）
    front_sender = asyncio.create_task(image_sender(websocket, session_id, 'front'))
    rear_sender = asyncio.create_task(image_sender(websocket, session_id, 'rear'))
    # 启动仪表盘数据发送任务
    status_task = asyncio.create_task(status_sender(websocket, session_id))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "get_vehicle_blueprints":
                # 返回可用车辆列表
                blueprints = get_vehicle_blueprints()
                await websocket.send_text(json.dumps({"type": "blueprints", "data": blueprints}))

            elif action == "create_vehicle":
                # 获取指定的蓝图 ID
                blueprint_id = msg.get("blueprint_id", "vehicle.tesla.model3")
                vehicle_bp = blueprint_library.find(blueprint_id)
                if not vehicle_bp:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid blueprint ID"}))
                    continue

                spawn_points = world.get_map().get_spawn_points()
                if not spawn_points:
                    await websocket.send_text(json.dumps({"type": "error", "message": "No spawn points available"}))
                    continue

                # 选择出生点（轮流分配）
                spawn_point = spawn_points[session_id % len(spawn_points)]
                vehicle = world.spawn_actor(vehicle_bp, spawn_point)
                session.vehicle = vehicle

                # 创建前方摄像头（第一人称，安装在车头前方）
                front_camera_bp = blueprint_library.find('sensor.camera.rgb')
                front_camera_bp.set_attribute('image_size_x', '800')
                front_camera_bp.set_attribute('image_size_y', '600')
                front_camera_bp.set_attribute('fov', '90')
                front_camera_transform = carla.Transform(carla.Location(x=1.5, z=1.5))
                front_camera = world.spawn_actor(front_camera_bp, front_camera_transform, attach_to=vehicle)
                session.front_camera = front_camera
                front_camera.listen(make_camera_callback(session_id, 'front'))

                # 创建后上方摄像头（第三人称，用于观察车辆整体）
                rear_camera_bp = blueprint_library.find('sensor.camera.rgb')
                rear_camera_bp.set_attribute('image_size_x', '800')
                rear_camera_bp.set_attribute('image_size_y', '600')
                rear_camera_bp.set_attribute('fov', '100')
                # 位置在车辆后方上方，并旋转使摄像头朝向车辆
                rear_camera_transform = carla.Transform(
                    carla.Location(x=-6.0, z=4.0),
                    carla.Rotation(pitch=-30.0)  # 向下倾斜一定角度
                )
                rear_camera = world.spawn_actor(rear_camera_bp, rear_camera_transform, attach_to=vehicle)
                session.rear_camera = rear_camera
                rear_camera.listen(make_camera_callback(session_id, 'rear'))

                # 返回成功消息，包含车辆 ID
                await websocket.send_text(json.dumps({"type": "vehicle_created", "vehicle_id": vehicle.id}))

            elif action == "start_driving":
                if session.vehicle:
                    # 使用非默认端口 9000 启动交通管理器，避免与 Web 服务冲突（如果 Web 服务用 8080 则无冲突）
                    session.vehicle.set_autopilot(True, 9000)
                    session.driving = True
                    # 生成行人（如果尚未生成）
                    if not session.walkers:
                        try:
                            walker_actors, controller_actors = spawn_pedestrians(world, session.vehicle)
                            session.walkers = walker_actors
                            session.walker_controllers = controller_actors
                        except Exception as e:
                            print(f"行人生成异常: {e}")
                            # 即使失败也不影响驾驶
                    await websocket.send_text(json.dumps({"type": "status", "message": "driving_started"}))

            elif action == "stop_driving":
                if session.vehicle:
                    session.vehicle.set_autopilot(False)
                    session.driving = False
                    await websocket.send_text(json.dumps({"type": "status", "message": "driving_stopped"}))

            elif action == "destroy_vehicle":
                if session.walker_controllers:
                    for controller in session.walker_controllers:
                        controller.stop()
                        controller.destroy()
                    session.walker_controllers = []
                if session.walkers:
                    for walker in session.walkers:
                        walker.destroy()
                    session.walkers = []
                # 销毁所有传感器和车辆
                if session.front_camera:
                    session.front_camera.stop()
                    session.front_camera.destroy()
                if session.rear_camera:
                    session.rear_camera.stop()
                    session.rear_camera.destroy()
                if session.vehicle:
                    session.vehicle.destroy()
                session.front_camera = None
                session.rear_camera = None
                session.vehicle = None
                session.driving = False
                await websocket.send_text(json.dumps({"type": "status", "message": "vehicle_destroyed"}))

    except WebSocketDisconnect:
        print(f"Client {session_id} disconnected")
    finally:
        # 取消所有任务
        front_sender.cancel()
        rear_sender.cancel()
        status_task.cancel()
        # 清理资源
        # 销毁行人控制器和行人
        if session.walker_controllers:
            for controller in session.walker_controllers:
                controller.stop()
                controller.destroy()
            session.walker_controllers = []
        if session.walkers:
            for walker in session.walkers:
                walker.destroy()
            session.walkers = []
        if session.front_camera:
            session.front_camera.stop()
            session.front_camera.destroy()
        if session.rear_camera:
            session.rear_camera.stop()
            session.rear_camera.destroy()
        if session.vehicle:
            session.vehicle.destroy()
        sessions.pop(session_id, None)

# ---------- 静态文件服务 ----------
@app.get("/")
async def get():
    from fastapi.responses import FileResponse
    return FileResponse(str(STATIC_DIR / "index.html"), headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

if __name__ == "__main__":
    # 使用 8080 端口，避免与 CARLA Traffic Manager 默认 8000 冲突
    uvicorn.run(app, host="0.0.0.0", port=8080)