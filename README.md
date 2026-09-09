# 机械臂错误反馈与反思框架：初步原型

对应论文：**基于错误反馈与智能反思的机械臂决策自修正机制研究**。

这是一个能够实际运行的 Python 原型，验证“动作 → 反馈 → 诊断 → 反思 → 参数修正 → 再次验证”的代码组织和 JSON 信息传递。默认使用确定性模拟适配器和规则反思器，无需 API Key，不访问网络，不连接机械臂。

**边界：** 默认演示不使用真实物理引擎；低速能否成功是测试场景预设条件，不是物理仿真结论或论文实验结果。初始任务与抓取动作固定，尚未实现通用 ReAct 任务规划、真机执行、持久化经验检索或 22 类完整协议。消息为设计计划的 v0.1 子集。

## 1. 直接运行

本机 PowerShell：

```powershell
cd 'C:\Users\叶立恒\Desktop\app\thesis-reflection-prototype'
.\run_demo.ps1
```

脚本优先使用本机 Codex 的 Python 环境，已用其中的 Python 3.12 与 Pydantic 2.13.5 验证。运行时不会自动安装依赖。

其他环境建议 Python 3.11+：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m reflection demo
```

可替换下文的 `python` 为你的虚拟环境解释器。

```powershell
python -m reflection demo --scenario slip
python -m reflection demo --scenario success
python -m reflection demo --scenario persistent
python -m reflection demo --scenario missing
python -m reflection demo --scenario slip --max-reflections 0
```

| 场景 | 行为 |
|---|---|
| slip | 0.08 m/s 时模拟滑落，反思建议改为 0.03 m/s，第二次测试通过 |
| success | 第一次即成功，不调用反思 |
| persistent | 修正后仍失败；规则反思器没有新证据支持的修改，因此停止 |
| missing | 缺少位姿证据；反馈为 unknown，无法确认成功，停止 |
| max-reflections=0 | 第一次失败后记录预算耗尽，不调用反思 |

每次默认创建独立 `runs/<时间-随机ID>/`，包含：

- `manifest.json`：原型版本、场景、反思器类型、运行 ID 和预算。
- `events.jsonl`：逐行保存全部中间消息，包括输入上下文、反馈、反思与修正。
- `summary.json`：最终状态、试验次数、反思次数和最终动作。

`--output <目录>` 可以指定输出位置；已有 `events.jsonl` 会拒绝覆盖。预期任务失败/停止属于正常实验结果，命令退出 0；组件错误或无效命令退出 2。判断任务是否成功请读取 summary.status。

## 2. 代码从哪里读起

| 文件 | 主要作用 |
|---|---|
| reflection/engine.py | `ReflectionLoop.run()` 串联整个闭环；`run_demo()` 创建演示运行 |
| reflection/contracts.py | 用 Pydantic 定义状态、动作、证据、反馈、诊断、反思、结果和事件 |
| reflection/adapters.py | `Simulator` 接口与离线 `DemoSimulator` |
| reflection/reflectors.py | `Reflector` 接口与离线规则基线 |
| reflection/http_reflector.py | 通过 HTTP 调用 Chat Completions 兼容模型接口 |
| reflection/policy.py | 判断结果、诊断、校验并应用修正 |
| reflection/storage.py | JSONL 写入、日志回放验证 |
| reflection/__main__.py | demo / replay / schemas 命令入口 |
| tests/ | 闭环、版本、证据、预算与 HTTP 接口测试 |

建议阅读顺序：`contracts.py → engine.py → adapters.py → reflectors.py → policy.py`。

内部的实际传递方式：

```python
# 都是 Python 对象，不需要每次函数调用都 json.dumps()
feedback = simulator.preview(action, state)
diagnosis = diagnose(feedback)
proposal = reflector.reflect(action, feedback)
new_action = apply_correction(action, proposal, feedback)

# 写入日志时，EventStore 使用 model_dump_json()
# HTTP 模型返回时，使用 Reflection.model_validate_json()
```

```text
固定初始状态 State
    ↓
动作 Action v1 → DemoSimulator.preview() → Feedback + Evidence
                                             ↓
                                 Verifier 判定与 Diagnosis
                                             ↓
                          Reflector.reflect(action, feedback)
                                             ↓
                                      Reflection 提案
                                             ↓
                      apply_correction()：版本、证据、参数校验
                                             ↓
动作 Action v2 → 从相同初始状态重新测试 → Outcome
```

注意：`diagnose()` 目前输出固定候选假设供审计；反思接口使用 action+feedback，HTTP 模型依据这份反馈自行分析。诊断器是初步规则实现，不是已验证的因果模型。

## 3. 这些中间信息分别是什么

- State：环境类型、状态 ID、对象 ID、夹持状态、时间戳、坐标系。
- Action：动作 ID、版本、引用的初始状态、技能、目标和抬升速度。
- Evidence：观测现象、数值、单位、判定阈值、来源和证据 ID。
- Feedback：动作关联、动作前后状态、成功/失败/未知、错误码和证据。
- Diagnosis：错误现象、原因候选、证据引用和未知信息。
- Reflection：原因假设、简短理由、证据引用、参数旧值与建议新值。
- Outcome：演示结果、试验次数、反思次数和最终动作。

这些业务消息共同包含在 Event 信封中：schema_version、event_id、run_id、sequence、emitted_at、parent_event_ids、event_type、payload。首版为单调度器，所以用线性事件父链；业务引用另外保留在 payload 中。

数值阈值是演示配置，不能用作真实设备安全限值。消息数值禁止 NaN/Infinity；未知字段拒绝进入业务消息。JSON Schema 导出：

```powershell
python -m reflection schemas --output schemas
```

Event 的 payload 目前为字典，导出的 Event Schema 不会按事件类型自动分派；关键业务对象在运行时通过各自的 Pydantic 类型校验。下一版可将完整事件集合做成带判别字段的联合类型。

## 4. 验证与回放

```powershell
python -m unittest discover -s tests -v
python -m reflection replay runs/<某次运行>/events.jsonl
```

回放仅检查事件结构、运行 ID、序号、事件重复、因果父引用和终态，并展示保存结果。不会重跑仿真、调用模型或发送机器人命令。它尚不负责验证所有业务引用、日志防篡改或重新计算结果。

当前约束包括：

- 模型只能建议改 `lift_speed_m_s`，不能修改传感器数据或控制权限。
- 修改必须引用当前动作版本、当前反馈和真实存在的证据。
- 旧值不符、越界、空修改和循环候选会被拒绝。
- 每次修改增加动作版本，并重新预演；不复用旧版通过结果。
- 缺失夹持力为 null；不将滑落直接解释成已证实的夹持力不足。
- 位姿缺失不能确认成功；其他物体的结果不能充当当前对象反馈。
- 次数预算使闭环有界；LLM 网络请求设超时，不进行无限自动重试。

## 5. 接入真实大模型

选择支持 Chat Completions 请求结构及 `response_format: json_object` 的服务。设置环境变量后才会向指定服务发送 action 和 feedback：

```powershell
$env:REFLECTION_API_URL = 'https://你的服务地址/v1/chat/completions'
$env:REFLECTION_MODEL = '你的模型名称'
# 通过当前终端/密钥管理工具设置 REFLECTION_API_KEY，勿写入代码或提交文件。
python -m reflection demo --scenario slip --reflector http
```

本地模型可使用 `http://127.0.0.1:端口/v1/chat/completions`。远程接口只接受 HTTPS；重定向被拒绝，防止将认证头意外发到另一地址。

HTTP 反思器将 Reflection 的 JSON Schema 写入系统提示，并要求 JSON 返回；客户端再次做类型校验，修正器再做语义校验。服务端 `json_object` 并不等于严格遵循 Schema。不支持该请求格式的服务需要调整适配器。

本次测试通过本地 HTTP 服务覆盖请求、合法响应和非法模型输出。尚未进行真实模型推理验证；在线模型不保证得到与规则反思器相同的结果。初版模型审计保留上下文和已解析输出；完整模型 usage、原始响应、请求重试统计可在下一版加入。

## 6. 接入 Isaac Sim / MuJoCo / 真机时改哪里

实现 `Simulator.preview(action, initial) -> Feedback`，随后将新适配器注入 `ReflectionLoop`。新的 preview 应负责恢复指定初态、把 Action 转成原生技能调用、采集执行轨迹和错误、转换为真实来源的证据。

当前 Evidence.source 固定为 demo_fixture、State.environment 固定为 demo，这是为了防止把演示记录混称实验数据。接入物理引擎时必须一起扩展并版本化消息类型，增加传感器来源、采样时间、标定与坐标变换信息。不是仅修改一个名字就算接入完成。

真机还需要单独的执行网关、幂等命令、状态新鲜度检查、校验与执行绑定、停止确认和本地控制器限制；当前原型没有该入口，不会因设置 API Key 而开始驱动机械臂。保持控制器与模型推理线程/进程独立。

## 7. 对论文可以怎样表述

可如实表述为：“已实现结构化反馈驱动的反思闭环软件原型，支持动作版本管理、证据引用校验、参数修正、有限次数重新验证和过程日志记录。”

当前不能表述为：“已完成机械臂物理仿真”“证明降低速度能解决滑落”“已经实现真机自修正”或“获得成功率提升”。这些结论需要接入实际平台、运行对照实验后再形成。
