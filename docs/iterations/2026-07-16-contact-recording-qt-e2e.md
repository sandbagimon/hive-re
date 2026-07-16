# Joint, IMU, and Contact Recording Qt E2E

日期：2026-07-16
提交：待提交

## 目标

在真实 QtWebEngine/MuJoCo 流程中同时录制、停止并导出 joint-state、IMU、contact 三类 sensor。

## 主要改动

- 扩展 contact Qt 场景，同时挂载 50Hz shoulder state、forearm IMU 和 forearm collider contact。
- Recording Panel 同时勾选三类 sensor，并保留默认两关节 state/actuator recording。
- UI 驱动 shoulder 接触可见平台后 Pause/Stop，读取 Python 端完整 recording。
- 通过项目 RPC 同时导出 JSON 与 CSV 到磁盘，再从文件重新读取验证。
- 保留接触时 Inspector、Scene Tree 三类 sensor、SecondSegment 高亮和导出 Console 的离屏截图。

## 验证

- 真实 QWebEngine + MuJoCo + OpenUSD 联合 E2E：1 passed。
- 41 个 state rows 中三类 50Hz event sequence 均从 0 连续递增，相邻 timestamp 为 0.02s。
- 总 sensor_event_count 等于 joint-state、IMU、contact 三类 events 数量之和。
- 至少一个非发射 physics step 的 sensors map 为空；contact events 从 empty 变为非零 count/force。
- JSON 文件与内存 recording 完全一致。
- CSV 同时包含 joint-state 5 列、IMU 13 列、contact 56 列；sequence 空 cells 与非零 normal force 均验证。
- `/tmp/simlab-contact-recording-ui.png` 视觉检查通过，无空白、遮挡或 Inspector 字段溢出。

## 已知限制

- Contact 宽表固定保留 8 个 point/normal slots，多 contact sensor 时 CSV 会较宽。
- Qt E2E 为 opt-in 测试，默认 pytest 在无 WebEngine display 环境下跳过。

## 下一步

补齐统一 sensor noise contract 和 deterministic Reset/seed 语义，完成 Iteration I 首版 contract。
