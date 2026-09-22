# 谱航智析｜无人机协议字节流分析 Demo

面向比赛展示的离线应用原型。输入已完成解调的十六进制字节流，或导入 `.bin` / `.hex` 捕获文件；程序识别 MAVLink 1、MAVLink 2 和 SBUS 帧，也会对重复出现的未知报文提出可复核的结构假设。页面可直接打开，无服务器、账号或设备依赖。

## 立即体验

打开根目录的 `index.html`，或打开 `dist/谱航智析_字节流协议分析Demo.html` 单文件版。点击任一内置样本，查看帧、字段和判定；修改左侧规则后重新分析同一数据，即可比较结果。也可粘贴十六进制字节、导入捕获文件并导出 JSON 报告。

内置 10 组捕获：原有 8 组已知协议样本，加上两种未知协议交错，以及已知与未知协议混合。MAVLink 样本由 `pymavlink` 生成；`tests/generate_fixtures.py` 和 `tests/generate_unknown_fixtures.py` 保留生成方法。未知协议样本的布局只存在于测试生成脚本中，发现算法没有导入其帧头或字段定义。

## 实现范围

- MAVLink 1/2：帧同步、长度与 CRC 校验；识别 HEARTBEAT、GPS_RAW_INT、ATTITUDE、COMMAND_LONG、COMMAND_ACK。对于尚无定义的消息，保留帧与原始字节，并明确提示无法完成 CRC_EXTRA 校验。
- SBUS：25 字节帧、16 个 11 位通道、丢帧和失控保护标志。
- 规则：起飞高度上限、GPS 定位等级下限、连续 SBUS 丢帧阈值、解锁确认要求。修改后可重跑；规则保存在当前浏览器。
- 报告：每条发现记录帧序号、字节偏移、命中字段和原始证据；可导出 JSON。
- 未知协议发现：对未被已知解析器消费的字节寻找重复双字节前缀，尝试候选长度关系与末字节 `sum8`／`xor8` 校验；将帧对齐后找固定值、候选序号和候选类型。报告列出每个假设的原始偏移与证据。至少需要三帧重复样本；没有验证校验时仅以低置信度呈现重复结构。
- 链路智能分析：汇总字节覆盖率、已知帧完整性、协议组成、协议切换点、字节熵和下一步采集建议；这些指标只描述解调后字节，不冒充射频质量指标。
- 连续捕获接口：`src/stream-intelligence.js` 接收带时间戳的数据块，能够跨块恢复被拆开的帧，维护滑动窗口并报告协议出现、消失、瞬时字节率和丢块计数。
- 状态与因果证据：从有效的 MAVLink 心跳、命令和应答中重建 `disarmed → arming-requested → armed → takeoff-requested → takeoff-accepted` 轨迹，报告缺少前置条件、缺少应答和孤立应答；“起飞命令已接受”不会被误写成“已经离地”。

完整的分阶段差距审计和实施清单见 [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md)。实现顺序固定为：先完成连续字节链路智能分析，再做离线 IQ 接入、降噪和单一调制解调，最后接入实时 SDR 硬件。

本原型从**已解调的字节**开始，不进行射频接收、波形解调或加密流解密。未知字段的业务含义、协议名称及设备行为无法仅从孤立字节证明；结构发现也不能保证覆盖所有封装方式。MAVLink 2 签名位会显示，但尚未进行签名认证。规则判定是演示算法，不构成飞控安全认证；SBUS 通道值不依赖具体遥控器的校准范围解释为物理量。

## 测试与构建

安装 Node.js 后运行 `npm test`，验证解析、校验、异常数据、规则重跑，以及未知协议样本的结构发现和证据不足时的拒绝推断。运行 `python scripts/build_standalone.py` 可重新生成单文件版。无需安装前端依赖。

`figures/` 单独存放申报书图片代码、最终 SVG 和原始 SVG；见 [图片代码说明](figures/README.md)。`presentation/` 保存实际操作录屏及适合插入 PPT 的 8 张关键帧。

## 协议依据

- [MAVLink 帧序列化与校验](https://mavlink.io/en/guide/serialization.html)
- [MAVLink common 消息定义](https://mavlink.io/en/messages/common)
- [ArduPilot SBUS 解码实现](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_RCProtocol/AP_RCProtocol_SBUS.cpp)
- [Discoverer：从网络轨迹自动推断消息格式](https://www.usenix.org/conference/16th-usenix-security-symposium/presentation/discoverer-automatic-protocol-reverse-enginee)
- [NetPlier：从消息轨迹进行概率协议逆向](https://www.ndss-symposium.org/ndss-paper/netplier-probabilistic-network-protocol-reverse-engineering-from-message-traces/)
