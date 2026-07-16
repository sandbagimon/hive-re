# Contact Simulation Runtime

日期：2026-07-16
提交：待提交

## 目标

把 MuJoCo contact aggregation 接入 fixed-step Session、Bridge payload 和 TypeScript Sensor Inspector，形成外部
USD 机械臂从无接触到接触再 Reset 的可观察闭环。

## 主要改动

- Session 初始化 ContactSensorScheduler 与 MujocoContactAggregator，并在每次 `mj_step` 后聚合、按 cadence capture。
- SimulationState 同时发布 joint-state、IMU 和 contact latest samples；Reset 重置 contact sequence。
- Bridge JSON Schema 与 TypeScript SensorSample union 增加有界 contact payload。
- Sensor Inspector 解析 link/collider scope，显示 count、normal force/impulse、world tangent force、首个 point/normal。
- 选择 contact sensor 时，viewport 高亮其 link 或 collider 所属 link。
- Recording Panel 只列出当前已经支持 typed export 的 joint-state 与 IMU；Session 对 contact recording 返回明确错误。

## 验证

- 外部 OpenUSD 两关节机械臂初始 forearm contact count 为 0。
- 驱动 shoulder 后，forearm collider 接触 scene 中可见静态平台，count、normal force 和 point 均非空。
- Reset 后 sample 恢复 time 0、sequence 0、contact count 0。
- Contact payload 可序列化为 Bridge/TypeScript 约定字段。
- Session、shared schema、viewport static tests 共 19 passed；TypeScript build 通过。

## 已知限制

- Contact events 尚未写入 recording JSON/CSV。
- Inspector 首版只展示聚合值与第一个 contact point/normal，不提供 per-contact 表格。
- QtWebEngine 真实交互与截图验收留到下一项。

## 下一步

建立 Contact Sensor Qt E2E，验证 Scene Tree selection、live Inspector、link highlight 与 Reset 清空。
