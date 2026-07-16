# Qt IMU Inspector

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine/MuJoCo 工作流中验证 joint-state 与 IMU 共存，以及 type-specific live Inspector。

## 主要改动

- Qt sensor fixture 在外部 OpenUSD forearm link 上增加 50Hz IMU local site。
- Sensor Tree 同时展示 Shoulder State 与 Forearm IMU。
- 现有 joint-state selection/recording/export 全回归，Recording checkbox 继续过滤未支持的 IMU artifact。
- Pause 后切换 IMU selection，读取 Link、sequence/time、orientation、angular velocity 和 linear acceleration。
- Reset workflow 验证 IMU fixed-step scheduler 回到 Home sequence 0/time 0。

## 验证

- DOM IMU Link 显示外部 USD forearm 名称。
- 三组 vector fields 与 Store typed sample 按 3 位小数完全一致。
- 运动 forearm IMU 至少一个 angular velocity 分量绝对值大于 0.01。
- joint-state JSON/CSV 仍保持 50Hz emitted-only cadence。
- Reset 后 simulation paused，IMU sequence/time 为 0/0。
- 真实 QtWebEngine/MuJoCo E2E 1 passed，viewport canvas/color 非空。

## 已知限制

- IMU 尚不可进入 Recording artifact。
- Vector fields 为只读数值，尚无 plot、frame axes 或 units badge。
- Qt offscreen screenshot compositing 可能滞后一帧；DOM 与 Store 断言是主验收证据。

## 下一步

把 Recording sensor state 从 joint-only 扩展为 typed joint_state/imu event union 和 stable vector CSV columns。
