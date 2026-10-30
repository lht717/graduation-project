# FusionLab + autodrivesystem_v0.5 整合版（V0.6.4）

## 本版本定位

本版本继续保留 `autodrivesystem_v0.5` 已打通的 CARLA / AI 视觉链路，并在 FusionLab 实验工作台中增加 ONNX 模型库管理。

当前已真实打通的运行链路：

CARLA（B机） → 前视/第三人称摄像头 → UFLD + YOLO（B机 ONNX Runtime） → FastAPI WebSocket → FusionLab 浏览器工作台。

“虚实结合”模式仍为界面与流程预留，真实 Jetson / Edge Agent 链路后续接入。

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

## 其他保留能力

- FastAPI `/ws` WebSocket；
- CARLA 车辆蓝图查询、创建、开始/停止自动驾驶与销毁；
- 前视摄像头与第三人称摄像头；
- 速度、加速度、油门、航向实时状态；
- 虚实结合模式边缘主板列表及连接交互（当前仍为前端模拟）；
- AI处理画面在左、CARLA摄像头与行驶信息在右；
- 首页不再将产品限定为纯虚拟系统。

## 启动

在项目根目录运行：

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

默认访问：`http://<B机IP>:8080/`。

V0.6.4 对首页返回增加了 `no-cache` 响应头，以减少升级版本后浏览器仍显示旧页面的问题。
