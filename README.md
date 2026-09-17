# 谱航智析｜无人机协议字节流分析 Demo

面向比赛展示的离线应用原型。输入已完成解调的十六进制字节流，或导入 `.bin` / `.hex` 捕获文件；程序识别 MAVLink 1、MAVLink 2 和 SBUS 帧，解析字段，依据可修改的规则形成带原始字节位置的证据报告。页面可直接打开，无服务器、账号或设备依赖。

## 立即体验

打开根目录的 `index.html`，或打开 `dist/谱航智析_字节流协议分析Demo.html` 单文件版。点击任一内置样本，查看帧、字段和判定；修改左侧规则后重新分析同一数据，即可比较结果。也可粘贴十六进制字节、导入捕获文件并导出 JSON 报告。

内置 8 组捕获：MAVLink 2 正常／异常、MAVLink 1 遥测、SBUS 正常／失控保护／丢帧、CRC 错误、MAVLink 与 SBUS 混合。MAVLink 样本由 `pymavlink` 生成；`tests/generate_fixtures.py` 保留生成方法。

## 实现范围

- MAVLink 1/2：帧同步、长度与 CRC 校验；识别 HEARTBEAT、GPS_RAW_INT、ATTITUDE、COMMAND_LONG、COMMAND_ACK。对于尚无定义的消息，保留帧与原始字节，并明确提示无法完成 CRC_EXTRA 校验。
- SBUS：25 字节帧、16 个 11 位通道、丢帧和失控保护标志。
- 规则：起飞高度上限、GPS 定位等级下限、连续 SBUS 丢帧阈值、解锁确认要求。修改后可重跑；规则保存在当前浏览器。
- 报告：每条发现记录帧序号、字节偏移、命中字段和原始证据；可导出 JSON。

本原型从**已解调的字节**开始，不进行射频接收、波形解调或加密流解密。MAVLink 2 签名位会显示，但尚未进行签名认证。规则判定是演示算法，不构成飞控安全认证；SBUS 通道值不依赖具体遥控器的校准范围解释为物理量。

## 测试与构建

安装 Node.js 后运行 `npm test`，验证解析、校验、异常数据与规则重跑。运行 `python scripts/build_standalone.py` 可重新生成单文件版。无需安装前端依赖。

`figures/` 单独存放申报书图片代码、最终 SVG 和原始 SVG；见 [图片代码说明](figures/README.md)。`presentation/` 保存实际操作录屏及适合插入 PPT 的 8 张关键帧。

## 协议依据

- [MAVLink 帧序列化与校验](https://mavlink.io/en/guide/serialization.html)
- [MAVLink common 消息定义](https://mavlink.io/en/messages/common)
- [ArduPilot SBUS 解码实现](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_RCProtocol/AP_RCProtocol_SBUS.cpp)

