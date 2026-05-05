# Issue #005: 上游失败下游容错机制

## Parent
002-agents-prd.md - 开放问题：上游失败下游怎么办？

## 类型
AFK

## What to build
实现 Agent 间的容错策略：检测上游状态 → 决定跳过/重试/告警

## Acceptance criteria
- [ ] 每个 Agent 启动时检查上游状态文件
- [ ] 上游 pending/running → 下游等待（超时 30 分钟）
- [ ] 上游 failed → 下游记录 skip 状态并写入日志
- [ ] 失败重试：最多 3 次，间隔 5 分钟
- [ ] 连续 3 天失败发送告警通知
- [ ] 部分成功处理（如抓到 30/50 条）下游正常继续

## Blocked by
- #004（需先定义状态码和错误类型）