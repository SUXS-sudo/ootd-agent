# 衣序 · 真实衣橱穿搭 Agent

衣序（Yixu OOTD Agent）是一个基于用户真实衣橱进行穿搭决策的个人造型 Agent。

它不会凭空推荐用户没有的衣服，而是读取衣橱中的真实单品、衣物状态、天气、场合、活动量和个人偏好，先生成可执行的完整搭配候选，再由规则或大模型选出三套方案。

当前产品界面精简为四个主要入口：今天、衣橱、计划和我的。项目仍保留周计划、旅行胶囊、多场景换装、穿搭检查、试穿、购买判断和主动规划等扩展页面。

## Agent 是怎么工作的

```text
用户自然语言
    ↓
意图理解：提取想穿/不穿、颜色、场合、天气和舒适度约束
    ↓
衣橱过滤：排除待洗、借出、收纳、需修补及天气不适合的衣物
    ↓
候选组装：只使用数据库中真实存在的 item_id 组成完整套装
    ↓
搭配决策：规则评分或大模型综合判断
    ↓
结果校验：检查三套方案、硬约束、重复组合和虚构单品
    ↓
输出“最稳妥 / 更显比例 / 更有风格”三套方案
```

大模型不是面对整个衣橱随意生成答案。程序会先完成真实衣物白名单、状态过滤和候选组装，大模型只能从合法候选中选择，最终结果还会再次校验。

### 三种运行模式

| 模式 | 意图理解 | 搭配决策 | 适用场景 |
| --- | --- | --- | --- |
| `fast` | 本地规则 | 本地规则 | 响应最快，不调用大模型 |
| `balanced` | 本地规则 | 大模型排序；失败时规则回退 | 日常推荐，兼顾速度和理解能力 |
| `deep` | 大模型语义理解 | 大模型排序；失败时规则回退 | 复杂要求、多轮修改和细腻风格表达 |

前端“今天”页面可以直接切换模式。接口响应中的 `generated_by` 会标记本次结果来自 `model`、`rules` 或 `rules_fast`。

### 大模型使用位置

- `backend/app/intent.py`：Deep 模式下理解自然语言任务、实体、硬约束和软偏好。
- `backend/app/agent.py`：从合法候选中决定三套完整搭配，并生成具体理由和穿法建议。
- `backend/app/photo_analysis.py`：使用视觉模型分析用户上传的整身穿搭照片。
- `backend/app/wardrobe_analysis.py`：识别上传衣物的品类、名称、颜色和基础属性。
- `backend/app/tryon.py`：调用图片模型生成试穿结果，并执行输出质量检查。
- `backend/app/proactive.py`：在用户授权后生成主动规划建议。

项目通过 OpenAI 兼容接口调用模型，可接入支持 Chat Completions 的供应商。视觉理解与图片生成使用独立模型和接口。

## 当前功能

### 数字衣橱

- 单件或批量上传 JPG、PNG、WebP 衣物照片。
- 视觉模型识别名称、品类、颜色、季节、正式度和保暖度，用户确认后保存。
- 编辑衣物属性和可穿状态。
- 统计品类、颜色、使用率和闲置情况。
- 支持上装、下装、连衣裙、外套、鞋履、包袋和配饰。

### 今日推荐与对话造型

- 根据天气、场合、步行量和临时要求生成三套完整搭配。
- 支持锁定、替换、移除某件单品。
- 支持连续对话，例如“第二套保留鞋子，把上衣换得更休闲”。
- 记录采用、拒绝和穿着历史，让后续偏好逐步更新。
- 首次使用可选择喜欢/不喜欢的风格与衣类；长期画像保存在数据库，Redis 缓存推荐所需的画像、场景权重和短期会话，缓存不可用时自动回源。

### 规划与分析

- 一周穿搭计划及局部重排。
- 旅行胶囊衣橱。
- 同一天多场景最少换装方案。
- 衣橱搭配图谱和长期补缺建议。
- 购买前重复度、可搭配数量和闲置风险判断。
- 基于真实采用记录生成个人风格画像。

### 图片能力

- 上传整身照片进行配色、比例、层次和场合适配分析。
- 选择女模特并使用衣橱搭配生成试穿图。
- 临时照片默认在分析后删除；需要保留时必须由用户明确授权。

## 技术栈

| 层级 | 实际使用技术 |
| --- | --- |
| Web | Vinext、Next.js 16、React 19、TypeScript、Vite、Tailwind CSS 4 |
| API | Python 3.12、FastAPI、Pydantic 2 |
| Agent | 规则约束、候选生成与评分、OpenAI SDK、结构化 JSON 校验 |
| 数据 | MySQL 8.4、Redis |
| 图片 | Cloudflare R2 对象存储 |
| 异步能力 | Celery、Redis、SSE 任务进度 |
| 部署 | 本地开发、Docker Compose、Cloudflare Worker/Sites 适配 |

## 快速开始

### 1. 安装环境

推荐使用项目提供的 Conda 环境：

```powershell
cd F:\Desktop\OOTD\ootd-agent
conda env create -f environment.yml
conda activate ootd-agent
```

环境已经存在时执行：

```powershell
conda activate ootd-agent
conda env update -f environment.yml
```

也可以分别安装依赖：

```powershell
npm.cmd install
python -m pip install -r backend\requirements.txt
```

### 2. 准备配置

```powershell
Copy-Item .env.example .env
```

最少需要确认以下配置：

```dotenv
DATABASE_URL=mysql+pymysql://ootd:ootd@localhost:3306/ootd?charset=utf8mb4
LANGGRAPH_CHECKPOINT_URL=mysql://ootd:ootd@localhost:3306/ootd_checkpoints?charset=utf8mb4
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=填写供应商实际支持的模型名
OPENAI_VISION_MODEL=填写支持图片输入的模型名
NEXT_PUBLIC_API_URL=http://localhost:8000
```

没有配置 `OPENAI_API_KEY` 时项目仍可运行，穿搭推荐会自动使用规则引擎；视觉识别、模型决策和图片试穿能力不可用或回退。

`SEED_DEMO_DATA=true` 只用于本地体验。生产环境会强制跳过演示用户和演示衣橱初始化；正式部署建议同时显式设置 `SEED_DEMO_DATA=false`。

### 3. 启动后端

打开第一个 PowerShell 窗口：

```powershell
conda activate ootd-agent
cd F:\Desktop\OOTD\ootd-agent\backend
python -m uvicorn app.main:app --reload --port 8000
```

后端地址：

- 健康检查：<http://localhost:8000/api/v1/health>
- API 文档：<http://localhost:8000/api/docs>
- OpenAPI JSON：<http://localhost:8000/api/openapi.json>

首次启动会自动创建 MySQL 表并写入基础演示数据。请先通过下方 Docker Compose 启动 MySQL，或连接已有的 MySQL 8.0.19+ 实例。

### 用户图片存储

用户图片存放在 Cloudflare R2 对象存储中，MySQL 保存图片元数据以及衣物与图片之间的关联。

MySQL 是图片链路的事实源，R2 只保存二进制对象。后端先在 `image_assets` 写入全局唯一的 `object_key` 和 `pending` 状态，提交成功后才向客户端签发该键的上传 URL；上传完成后通过 `HEAD` 校验对象和大小，再在同一个 MySQL 事务中把资源改为 `processing` 并创建引用它的衣物记录。`wardrobe_items.image_asset_id` 有唯一外键约束，一条图片资源最多对应一条衣物记录。资源状态按 `pending → processing → ready → pending_delete → deleted` 流转，定时对账任务会清理超时上传、重投处理中任务、检查 ready 对象以及重试待删除对象。R2 或 Redis 暂时不可用时，MySQL 状态仍保留，恢复后可以幂等补偿。

Redis 不保存衣物、图片、反馈或推荐结果的权威数据，只用作 cache-aside 缓存和 Celery 消息通道。画像、场景偏好和短期会话先提交 MySQL，再写入或失效 Redis；缓存未命中、连接失败或缓存过期时直接回源 MySQL。所有缓存都有 TTL，因此删除失败最多造成有限时间的旧读。Celery 任务使用 late ack、worker 丢失重投和幂等对象键；图片任务是否完成以 MySQL 的资源状态为准，不以 Redis/Celery result backend 为准，定时对账负责补投未完成任务。

Cloudflare R2 使用私有 Bucket，并通过以下环境变量配置：

```dotenv
STORAGE_BACKEND=r2
STORAGE_BUCKET=ootd-private
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY_ID=<access-key-id>
STORAGE_SECRET_ACCESS_KEY=<secret-access-key>
STORAGE_REGION=auto
```

Bucket CORS 只需允许 Web 域名使用 `PUT`、`GET` 和 `HEAD`，并允许 `Content-Type` 请求头。凭据只能配置在后端环境变量中，不能暴露给浏览器。

### 4. 启动前端

打开第二个 PowerShell 窗口：

```powershell
conda activate ootd-agent
cd F:\Desktop\OOTD\ootd-agent
npm.cmd run dev
```

根据终端输出打开前端地址，通常为 <http://localhost:3000>。Windows 下推荐使用 `npm.cmd`，避免 PowerShell 执行策略拦截 `npm.ps1`。

## 真实衣服图片接入

### 方法一：在页面上传

打开“衣橱 → 添加衣服”，可以一次选择多张真实衣物图片。前端会进行基础背景处理，后端视觉模型会尝试识别属性；确认后图片存放在 Cloudflare R2 对象存储中，衣物信息保存至 MySQL。

这是普通用户使用时推荐的方式。

### 方法二：批量放入项目文件夹

用于准备演示衣橱时，将真实商品图放入：

```text
public/clothes/
```

图片文件名必须与 [衣橱真实商品图-生图提示词.md](docs/image-generation/衣橱真实商品图-生图提示词.md) 中的名称一致，例如：

```text
米白色罗纹圆领短款针织衫.png
雾霾蓝挺括棉质长袖衬衫.png
深靛蓝高腰直筒牛仔裤.png
```

然后执行：

```powershell
cd F:\Desktop\OOTD\ootd-agent\backend
$env:PYTHONPATH='.'
python scripts\sync_real_wardrobe_images.py
```

同步脚本根据提示词清单中的分类、顺序和文件名更新数据库，不会为缺少真实图片的衣物创建矢量占位图。

如需先把演示衣橱扩充到每类 50 件：

```powershell
cd F:\Desktop\OOTD\ootd-agent\backend
$env:PYTHONPATH='.'
python scripts\expand_demo_wardrobe.py
python scripts\sync_real_wardrobe_images.py
```

当前仓库只对已经放入 `public/clothes/` 的真实图片建立图片绑定，其余演示衣物允许暂时无图。

## 测试

### 前端构建与结构测试

```powershell
cd F:\Desktop\OOTD\ootd-agent
npm.cmd test
```

单独构建或检查代码：

```powershell
npm.cmd run build
npm.cmd run lint
npm.cmd run check
```

### 后端测试

```powershell
cd F:\Desktop\OOTD\ootd-agent\backend
$env:PYTHONPATH='.'
python -m pytest tests -q
```

测试覆盖 API、身份认证、意图理解、衣物状态过滤、锁定单品、搭配排序、回答校验以及 V2/V3 规划接口。

### 离线质量评测

```powershell
cd F:\Desktop\OOTD\ootd-agent
python tests\evals\run_evals.py
python tests\evals\evaluate_intents.py --mode rules
```

推荐评测需要满足：不存在不可用衣物、虚构 `item_id` 和拒绝颜色泄漏；规则意图测试需要通过冻结数据集。

个性化评测还会执行通用排序与反馈排序的消融对照。系统把采用、拒绝和明确替换转换成单品、品类、颜色与风格亲和度，按 90 天半衰期衰减；同场景证据完整计入，跨场景证据仅按四分之一计入。个性化对总分的影响随有效样本量增长且上限为 35%，因此冷启动不会覆盖天气、场合和可穿状态等通用规则。

每次推荐响应的 `evidence_pack[].dimensions` 会按评分维度返回 `claim`、事实依据、来源单品、计算方法和证据置信度。持久化后的证据可通过 `GET /api/v1/outfits/{outfit_id}/evidence` 读取。这里的置信度描述证据完整度，不代表统计校准后的采用概率。

### V2 Pairwise 学习排序

每次推荐会保存不可变的决策快照与所有候选曝光，包括请求上下文、特征版本、候选生成版本、排名模型版本、展示位置和策略选择概率。采用、局部替换、整套拒绝与撤销分别映射为不同强度奖励。`POST /api/v1/personalization/train` 按推荐批次做时间顺序 70/30 切分，用同一批展示候选中的相对偏好训练线性 Bradley-Terry 排序器，并报告测试集 Pairwise Accuracy、Pairwise Log Loss 与 NDCG@3。代理专家反馈按 0.35 权重训练。模型通过 `GET /api/v1/personalization/models` 查询，旧模型会保留为可复现版本。

### V3 质量门槛 Thompson Sampling 与反事实

用户通过稳定哈希进入 `pairwise_control` 或 `thompson_sampling` 实验组，分组结果持久化且不会随请求改变。Thompson Sampling 从对应场景的对角高斯后验采样，但只允许在通过真实衣橱、天气、场合与明确偏好硬约束，并且基础分距当前最优不超过 10% 的候选中探索；线上探索概率默认为 5%。系统记录真实策略选择概率，反馈用于更新后验精度、奖励和后验均值；近期与长期反馈差异达到阈值时记录偏好漂移事件。

- `GET /api/v1/personalization/experiment`：当前实验组；
- `GET /api/v1/personalization/drift`：偏好漂移事件；
- `POST /api/v1/outfits/{outfit_id}/counterfactual`：固定其他特征进行局部反事实重算；
- `GET /api/v1/outfits/{outfit_id}/evidence`：规则证据、模型版本、策略版本与真实特征贡献。

运行 V2/V3 独立质量门槛：

```powershell
python tests\evals\evaluate_decisioning.py
```

需要在没有真实反馈时验证完整数据链路，可运行 `python backend/scripts/seed_proxy_decisions.py`。脚本通过真实推荐 API 生成 24 个场景，由固定造型师准则选出代理优胜方案，并以 `expert_proxy` 来源和 0.35 训练权重保存；它不会写入穿着历史、真实采用率或在线 Bandit。真实用户反馈始终使用 `user_feedback` 来源和完整权重。

### 真实视觉与试穿接口测试

需要配置可用的视觉模型或图片模型：

```powershell
cd F:\Desktop\OOTD\ootd-agent\backend
$env:PYTHONPATH='.'
python scripts\test_vision_live.py
python scripts\test_tryon_live.py
```

这两个脚本会产生真实模型调用，不属于默认离线测试。

## Docker 完整环境

需要 MySQL、Redis、Celery Worker 和调度器时：

```powershell
cd F:\Desktop\OOTD\ootd-agent
Copy-Item .env.example .env
docker compose -f platform\docker\docker-compose.yml up --build
```

停止服务：

```powershell
docker compose -f platform\docker\docker-compose.yml down
```

项目统一使用 MySQL；本地开发可仅启动 Compose 中的 `mysql` 服务，再分别运行 FastAPI 与前端。

## 目录结构

```text
ootd-agent/
├─ app/                         Web 页面、组件和前端 API 封装
├─ backend/app/                 FastAPI、Agent、推荐、规划与数据模型
├─ backend/scripts/             衣橱同步、扩充和真实模型测试脚本
├─ backend/tests/               后端自动化测试
├─ backend/generated/           用户上传及模型生成的运行时图片
├─ public/clothes/              项目内真实商品图
├─ docs/                        文档索引、当前指南、历史方案和提示词
├─ platform/                    Docker 和 Cloudflare Sites 前端托管适配
├─ tests/evals/                 离线推荐及意图评测
├─ environment.yml              Conda 环境定义
└─ package.json                 Web 脚本和依赖
```

所有文档见 [docs/README.md](docs/README.md)，更详细的实现说明见 [当前版本实现指南](docs/guides/current-implementation.md)。

## 天气与 Outlook 日历

- 实时天气使用 Open-Meteo，无需 API Key；“今天”和“计划”页会按城市读取温度、体感温度及降雨概率。
- Outlook 日历通过 Microsoft Graph 只读接入。在 Microsoft Entra 中注册 Web 应用，将重定向地址设为 `http://localhost:8000/api/v1/integrations/outlook/callback`，创建 Client Secret，然后在 `.env` 填写 `MICROSOFT_CLIENT_ID` 和 `MICROSOFT_CLIENT_SECRET`。
- Microsoft 权限使用委托权限 `Calendars.Read`，用户可在“我的 → 提醒与数据授权”中连接或撤回。访问令牌与刷新令牌在本地数据库中加密保存。

## 当前限制

- 演示衣橱数据可以扩展到每类 50 件，但真实商品图仍需逐步补充，未补图条目不会伪装成不同商品。
- `balanced` 和 `deep` 的实际效果取决于模型供应商的结构化 JSON 能力和响应速度。
- Outlook 日历需要项目部署者自行提供 Microsoft Entra 应用凭据。
- 本地与生产环境均使用 MySQL；生产环境必须替换示例账号密码，并使用托管密钥或环境变量注入凭据。
- 图片试穿是生成结果，不能代替真实尺码和上身效果判断。

## 设计底线

- 推荐结果只能引用当前用户衣橱里真实存在的 `item_id`。
- 待洗、清洗中、借出、收纳和需要修补的衣物不会进入可穿候选。
- 用户明确提出的“必须、不要、保留”优先于默认偏好。
- 大模型只能选择程序提供的合法完整候选，不能跨候选拼接或发明单品。
- 反馈采用小步学习，单次拒绝不会直接覆盖长期偏好。
- 照片分析不推断体重、健康、三围或敏感身份信息。
- 主动能力必须检查用户授权范围并记录敏感数据访问日志。
