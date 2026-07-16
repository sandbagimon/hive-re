# Contact Recording Runtime and UI

日期：2026-07-16
提交：待提交

## 目标

把 fixed-step contact emitted events 接入 Session recorder，并在 TypeScript Recording Panel 开放选择和导出。

## 主要改动

- Session 保存 ContactSensorScheduler.capture 返回值，与同一 physics step 的 joint-state/IMU events 合并 capture。
- t=0 recording boundary 同时注入 contact latest sequence 0，即使当前 contact count 为 0。
- Session sensor type map 直接驱动三类 recording，不再把 contact 判为 unsupported。
- Recorder capture union 扩展到 ContactSensorSample，SimulationState event count 包含 contact emitted events。
- Recording Panel 的 draft signature、selection 与 checkbox 列表开放 joint-state、IMU、contact 三类 sensor。
- 重新生成 TypeScript editor bundle。

## 验证

- 100Hz physics / 50Hz contact sensor 运行 250 steps，recording 包含 251 rows 与 sequence 0-125 共 126 events。
- t=0 event 是 empty contact；后续 event 至少一项包含非零 count/force 和 contact point。
- 非发射 physics step 的 sensors map 为空，证明 cadence 不会复制 latest sample。
- Runtime event 可转为 typed contact JSON，CSV header 包含 stable normal-force 与 point/normal columns。
- Session/web viewport 聚焦测试 3 passed；TypeScript build 和 frontend tests 通过。

## 已知限制

- 三类 sensor 同时录制和完整 JSON/CSV 文件导出尚未经过真实 QtWebEngine E2E。
- Contact CSV 每个 sensor 固定 56 列，宽表规模会随 contact sensor 数量线性增加。

## 下一步

建立 joint-state、IMU、contact 联合 Qt recording/export E2E。
