# FusionLab + autodrivesystem_v0.5 整合版（V0.6.4）

## 本版本定位

本版本继续保留 `autodrivesystem_v0.5` 已打通的 CARLA / AI 视觉链路，并在 FusionLab 实验工作台中增加 ONNX 模型库管理。

当前已真实打通的运行链路：

CARLA（B机） → 前视/第三人称摄像头 → UFLD + YOLO（B机 ONNX Runtime） → FastAPI WebSocket → FusionLab 浏览器工作台。

“虚实结合”模式可通过独立 WebSocket 接入边缘主板；CARLA 仿真链路仍由原有 `/ws` 提供。

## V0.6.4 新增：模型上传、模型库与动态加载

实验工作台“AI 模型库”现在支持：

1. 从浏览器选择 `.onnx` 文件；
2. 在“保存文件名”中指定上传后文件名；
3. 上传模型并保存到项目 `models/` 文件夹；
4. 若文件名已存在，拒绝覆盖并提示“文件名已存在，请修改上传模型的文件名”；
5. 自动列出 `models/` 文件夹内的所有 ONNX 模型及文件大小；
6. 分别选择“车道线检测模型（UFLD兼容）”与“目标检测模型（YOLO兼容）”；
7. 点击“加载所选模型”后，无需重启 Uvicorn 即可切换模型；
8. 正在行驶时禁止切换模型，需先停止实验，以避免 CARLA 传感器线程与模型切换并发。

### 重要说明

当前算法流水线仍有两个不同的处理槽位：

- UFLD：预处理为 800×288，使用现有车道线后处理；
- YOLO：预处理为 640×640，使用现有 YOLO 后处理。

因此“上传成功”只代表文件是 ONNX Runtime 可读取的 ONNX 文件；要实际运行，还必须与对应槽位的输入/输出及后处理兼容。V0.6.4 暂不支持把任意 ONNX 模型自动识别成任意算法任务。

## 模型目录

`models/` 为服务器模型库。原 V0.5 默认模型如仍需使用，请放入：

- `models/ufld_culane.onnx`
- `models/yolov5su.onnx`

若存在这两个文件，服务启动时会自动加载；不存在时网页和服务仍可启动，之后可在网页上传并选择模型。

## 模型 API

- `GET /api/models`：列出 models 文件夹中的 ONNX 与当前激活模型；
- `POST /api/models/upload?filename=xxx.onnx`：上传模型，Body 为原始二进制；
- `POST /api/models/load`：加载所选 UFLD / YOLO 模型。

本版上传使用原始二进制 Body，不依赖 `python-multipart`。

## 虚实结合：边缘主板 WebSocket

工作台切换至“虚实结合”后会自动连接 `/ws/edge/panel`，与 CARLA `/ws` 相互独立、可同时工作。

- 页面控制端：`ws://<IP>:8080/ws/edge/panel?token=<登录 token>`（登录后自动订阅）
- 边缘主板：`ws://<IP>:8080/ws/edge?device_id=jetson-nano&token=<设备密钥>`；可选 `name`、`vendor`、`model`、`device_no` 用于设备卡片展示
- 页面控制按钮发送 `{"type":"command","command":"start"|"stop"|"switch_model","device_id":"jetson-nano","params":{}}`，后端只转发给选中的在线主板，并同步其空闲/使用中状态
- 主板上报检测 JSON 后，页面展示目标类别、置信度、边界框、模型名与上报帧率，并可展开查看原始 JSON

边缘主板收到控制消息后，应按设备协议启动或停止检测；检测结果以 JSON 文本帧持续上报。无设备连接时，页面控制按钮会保持禁用。

## 边缘主板接入（已并入 main.py，单端口 8080）

`edge_ws_server.py` 不再是独立进程，它的连接池、检测归一化与指令转发逻辑已通过 `attach()` 挂到 `main.py` 的同一个 FastAPI 实例上，页面与设备共用 8080 端口：

| 入口 | 地址 | 说明 |
|---|---|---|
| 边缘主板 | `ws://<IP>:8080/ws/edge?device_id=jetson-nano&token=<设备密钥>` | 必须带设备密钥，默认 `fusionlab-edge-token`（可用环境变量 `EDGE_TOKEN` 覆盖） |
| 页面工作台 | `ws://<IP>:8080/ws/edge/panel?token=<登录 token>` | 复用平台登录会话，无需另配密钥 |
| REST | `GET /api/edge/devices`、`GET /api/edge/health`、`POST /api/edge/command` | 调试与脚本调用 |

启动只有一条命令（默认端口 8080）：

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

主板客户端（`edge_device_client.py`）连接平台：

```bash
# 实物：摄像头 0 + YOLO
python edge_device_client.py --server ws://192.168.1.20:8080/ws/edge \
    --device-id jetson-nano --token fusionlab-edge-token --camera 0 --show

# 联调：无摄像头/无权重时先用合成画面通链
python edge_device_client.py --server ws://127.0.0.1:8080/ws/edge --mock
```

单独运行 `edge_ws_server.py`（8081）仍然可用，适合不启动平台、只做设备接入测试的场景。

协议约定：

- 设备 → 服务端：`{"type":"detection","count":2,"detections":[{"class_id":2,"class_name":"car","confidence":0.95,"bbox":[10,20,120,180]}],"frame":{"width":640,"height":480},"model":"yolov8n.pt","infer_ms":12.3,"seq":17}`，其中 `frame` 供前端按原始分辨率缩放框坐标；
- 缩略图（可选）：设备可在检测帧里附 `thumb` 字段，内容为 `data:image/jpeg;base64,...`（客户端默认 320px 宽 / JPEG 质量 65，`--thumb-width 0` 关闭）。服务端校验前缀与大小后原样转发，并会从 `raw` 原始报文与 MySQL 落库中剔除该字段，避免流量与存储翻倍；**虚实结合模式下，主板上传的画面会直接铺满左侧「AI 感知识别」画布，检测框由前端按 `frame` 尺寸 1:1 叠加**（虚拟仿真模式该画布仍显示 CARLA 前视感知结果，两者不会互相覆盖）；
- 服务端 → 设备：`{"type":"command","command":"start"|"stop"|"switch_model","params":{"model":"yolov8s.pt"},"request_id":"..."}`，握手后先下发 `welcome`；
- 设备回执：`{"type":"command_ack","payload":{"ok":true,"command":"start","message":"检测已启动"}}`，服务端转成 `command_ack` 广播给前端；
- 事件：`device_list`（握手快照）、`device_online`、`device_offline`（带 `reason`）都附全量设备列表。

## 前端构建与部署

前端源码在 `frontend/`（Vue 3 + Vite），`static/` 是 FastAPI 实际托管的构建产物：

```bash
cd frontend
npm install        # 首次
npm run build      # 产物在 frontend/dist
cp -r dist/* ../static/    # 部署到 FastAPI 托管目录
```

## 新增页面：个人中心与私信

前端已按模块拆分到 `static/js/` 并采用 hash 路由，在原有实验流程之外新增两个页面：**个人中心（`#profile`）**，用于查看账号（学号）、角色与注册时间，并可修改自定义名称和登录密码；**私信（`#message`）**，用于查看收件箱列表与消息详情，支持手动刷新。

## 其他保留能力

- FastAPI `/ws` WebSocket；
- CARLA 车辆蓝图查询、创建、开始/停止自动驾驶与销毁；
- 前视摄像头与第三人称摄像头；
- 速度、加速度、油门、航向实时状态；
- 虚实结合模式通过独立 WebSocket 接入边缘主板并实时展示目标检测 JSON；
- AI处理画面在左、CARLA摄像头与行驶信息在右；
- 首页不再将产品限定为纯虚拟系统。

## 启动

在项目根目录运行：

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

默认访问：`http://<B机IP>:8080/`。

V0.6.4 对首页返回增加了 `no-cache` 响应头，以减少升级版本后浏览器仍显示旧页面的问题。
