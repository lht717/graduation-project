# FusionLab 后端说明（FastAPI + MySQL）

> 面向毕业设计答辩与后续维护的后端交接文档。负责人：卓奕臻。

## 一、技术栈

| 项 | 选型 |
|---|---|
| Web 框架 | FastAPI 0.163 |
| ASGI 服务器 | Uvicorn 0.54 |
| 数据库 | MySQL 8.0（库名 `fusionlab`） |
| 驱动 | PyMySQL 1.2 + DBUtils 连接池 |
| 密码哈希 | bcrypt 5.0（兼容旧版固定盐 SHA256，登录时自动升级） |
| 数据校验 | Pydantic 2 |
| 测试 | pytest + httpx（TestClient） |

## 二、本地启动

### 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 2. 准备数据库

启动 MySQL（默认 `127.0.0.1:3306`），执行建表脚本：

```powershell
mysql -u root -p < schema.sql
```

### 3. 配置环境变量（可选，不填则用本地默认值）

| 环境变量 | 作用 | 默认值 |
|---|---|---|
| `FUSIONLAB_DB_HOST` | 数据库地址 | `127.0.0.1` |
| `FUSIONLAB_DB_PORT` | 数据库端口 | `3306` |
| `FUSIONLAB_DB_USER` | 数据库用户 | `root` |
| `FUSIONLAB_DB_PASSWORD` | 数据库密码 | `123456` |
| `FUSIONLAB_DB_NAME` | 数据库名 | `fusionlab` |
| `FUSIONLAB_CORS_ORIGINS` | 允许的前端来源（逗号分隔） | `http://127.0.0.1:8080,http://localhost:8080` |
| `FUSIONLAB_ADMIN_PASSWORD` | 预置管理员初始密码 | `admin123` |
| `FUSIONLAB_DEMO_PASSWORD` | 预置演示账号初始密码 | `fusionlab` |
| `FUSIONLAB_LOG_LEVEL` | 日志级别 | `INFO` |
| `FUSIONLAB_DISABLE_CARLA` | 置 `1` 禁用 CARLA/ONNX 仿真模块 | 空 |
| `EDGE_TOKEN` | 边缘设备接入密钥 | `fusionlab-edge-token` |

### 4. 启动后端

后端运行在独立 conda 环境 `fusionlab`（Python 3.12，与 CARLA 的 `carla` 环境隔离）。

方式一：双击项目根目录的 `start_backend.bat`（自动使用正确的解释器）。

方式二：命令行启动：

```powershell
C:\ProgramData\anaconda3\envs\fusionlab\python.exe main.py
```

监听 `0.0.0.0:8080`，浏览器访问 `http://127.0.0.1:8080/`。

> 注意：网站不能用双击 HTML（`file://`）方式打开，必须由后端服务提供静态资源；也不要在 Anaconda 的 `carla` 环境（Python 3.7）里启动后端，该环境缺少 bcrypt、DBUtils 等依赖。

### 5. 运行测试

```powershell
C:\ProgramData\anaconda3\envs\fusionlab\python.exe -m pytest tests/ -v
```

## 三、文件职责

| 文件 | 职责 |
|---|---|
| `main.py` | FastAPI 入口：认证、用户、班级、实验类型、实验数据、私信等业务接口；挂载静态资源与边缘/仿真模块 |
| `edge_ws_server.py` | 边缘主板 WebSocket 接入与工作台面板（`/ws/edge`、`/ws/edge/panel`、`/api/edge/*`） |
| `carla_runtime.py` | CARLA 仿真与 ONNX 推理（`/api/models`、`/ws`），模型缺失时自动跳过，不影响业务网页 |
| `edge_device_client.py` | 板端独立客户端脚本（单独运行，不在后端服务链路内） |
| `schema.sql` | 建库建表脚本 |
| `static/` | 前端静态资源（页面、JS、CSS、头像） |
| `tests/test_smoke.py` | 后端冒烟测试 |

## 四、数据库表

- `users`：账号、显示名、角色、启用状态、密码哈希、头像、班级
- `messages`：管理员与用户之间的私信
- `experiments`：实验运行记录（时长、速度、加速度、油门、朝向、帧率等）
- `classes`：班级信息（人数按 users 表自动统计同步）
- `experiment_types`：实验类型（名称唯一）

## 五、接口分组

### 认证
- `POST /api/auth/login` 登录（Pydantic 校验，返回 token）
- `GET /api/auth/me` 当前登录用户
- `POST /api/auth/logout` 退出登录

### 用户资料（登录态）
- `POST /api/users/me/display-name` 修改显示名
- `POST /api/users/me/avatar` 更新头像（base64 或图片地址）
- `POST /api/users/me/password` 修改密码（校验当前密码）

### 管理员 · 用户管理
- `GET /api/admin/users` 用户列表
- `POST /api/admin/users` 新建用户
- `POST /api/admin/users/password/reset` 重置指定用户密码
- `PUT /api/admin/users/{username}/password` 修改用户密码
- `PATCH /api/admin/users/{username}` 编辑用户信息
- `PUT /api/admin/users/{username}/role` 提升为管理员
- `PUT /api/admin/users/{username}/status` 启用/停用管理员账号
- `DELETE /api/admin/users/{username}` 删除用户（连同其私信）

### 班级管理
- `GET/POST /api/admin/classes`；`PUT/DELETE /api/admin/classes/{id}`

### 实验类型
- `GET /api/experiment-types`（登录用户）
- `GET/POST /api/admin/experiment-types`；`PUT/DELETE /api/admin/experiment-types/{id}`

### 实验数据
- `GET /api/admin/experiments` 实验列表（管理员）
- `GET /api/users/me/experiments` 我的实验汇总
- `POST /api/experiments` 保存实验运行记录
- `POST /api/admin/experiments` 管理员新增实验
- `PUT/DELETE /api/admin/experiments/{id}`；`PUT /api/admin/experiments/{id}/status`

### 私信
- `GET /api/messages` 会话与可收件人
- `POST /api/messages` 发送私信（普通用户仅可与管理员互发）

### 边缘与仿真
- `/ws/edge`、`/ws/edge/panel`、`/api/edge/*`（边缘接入）
- `/api/models`、`/ws`（CARLA 仿真）

## 六、本轮已完成的后端加固

1. **修复空接口**：管理员重置密码接口原仅返回提示、未写库，已补全按行更新哈希。
2. **密码安全**：哈希由 SHA256 改为 bcrypt 慢哈希；旧哈希用户登录成功后自动升级；改密/重置/创建统一走慢哈希。
3. **持久化按行增删改**：去掉"全量删除再循环插入"的重建写法，改为按主键插入/更新/删除，避免重启丢数据与性能抖动。
4. **配置与 CORS 收敛**：数据库、初始密码、跨域来源全部走环境变量；CORS 不再用 `*` 通配，方法与请求头收为白名单。
5. **阻塞调用移出事件循环**：含阻塞 MySQL 调用的业务接口由 `async def` 改为普通 `def`，由 FastAPI 线程池调度，避免阻塞事件循环。
6. **连接池 / 日志 / 校验模型**：引入 DBUtils 连接池复用连接；登录成功/失败、权限拒绝写入结构化日志；登录接口接入 Pydantic 请求模型（非法入参自动 422）。
7. **工程化补全**：新增 `requirements.txt`、`tests/` 冒烟测试与本说明文档。

## 七、已知遗留与后续建议

> 以下为评审中识别、本轮未改动的点，供后续迭代参考，不影响当前业务运行。

- 登录暂无失败次数限流 / 账号锁定，建议加按账号 + IP 的失败计数与临时锁定。
- 头像仅校验前缀与大小，未校验图片魔数（文件头），建议补类型校验。
- 搜索关键字中的 `%`、`_` 未转义，LIKE 匹配可能被放大。
- 速度、油门等数值字段未做上下界约束。
- 时间字段当前为 `varchar`，建议后续改为 `datetime` 类型。
- 表间未建外键约束，一致性依赖应用层维护。
- 会话 token 无过期时间，建议加 TTL 与刷新机制。
- 启动时通过 `ALTER TABLE` 做列兼容，建议后续用正式数据库迁移工具（如 Alembic）。

### 建议的分层目录（后续重构路线）

当前业务接口集中在 `main.py` 单文件，后续可按职责拆分，降低耦合：

```
app/
├── main.py            # 应用入口、挂载路由与静态资源
├── routers/           # 按业务域拆分：auth / users / classes / experiments / messages
├── services/          # 业务逻辑、密码哈希、鉴权辅助
├── db/                # 连接池、SQL 与按行 CRUD
├── schemas/           # Pydantic 请求/响应模型
└── tests/
```

拆分时需注意：内存中的 `users`、`messages`、`auth_sessions` 为跨接口共享状态，建议先下沉到服务层再拆路由，避免循环导入。
