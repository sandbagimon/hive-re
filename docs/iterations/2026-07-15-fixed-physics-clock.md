# Fixed Physics Clock

日期：2026-07-15
提交：待提交

## 目标

让仿真速度由 MuJoCo timestep 和真实 elapsed time 决定，而不是由 Qt callback 次数决定。

## 主要改动

- SimulationService 接受可注入 monotonic clock，便于确定性测试。
- Run 时记录墙钟起点，callback 将 elapsed time 累加后换算为整数个固定 MuJoCo step。
- 不足一个 timestep 时保持当前 physics state；累计余数留到后续 callback。
- `simulation_config.max_catch_up_steps` 控制单帧最大补算，默认 8。
- 大幅 UI 卡顿时丢弃超出 cap 的 backlog，防止恢复后长时间阻塞主线程。
- Pause、manual Step、Reset 清空 clock accumulator；Resume 不补算暂停期间的墙钟时间。
- 拒绝布尔值、非整数和小于 1 的 catch-up 配置。

## 验证

- 16 ms + 16 ms callback 在 10 ms timestep 下依次推进 1 和 2 steps。
- 1 秒卡顿在 cap=4 时只推进 40 ms simulation time。
- Pause 10 秒后 Resume 只从新的墙钟起点推进。
- 完整门禁见提交记录。

## 下一步

捕获 runtime step 异常和非有限 state，并将 fault 安全发布到 UI。
