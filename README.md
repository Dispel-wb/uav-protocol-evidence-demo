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
- 协议敏感度学习基线：`src/protocol-model.js` 提取字节直方图、哈希二元组和长度特征，训练可解释的质心分类器，并以相似度和类别间隔执行开集拒识。现有小样本测试只能验证代码路径，不能证明跨设备泛化能力。
- 模型评测：`npm run evaluate:model` 根据 `samples/model-dataset.json` 完成阈值校准，报告已知准确率、未知召回率、误接收率、误拒绝率和单样本推理时间。
- 主动调试：页面根据未知字段与状态证据给出下一组受控实验、原因和验收口径；`src/active-learning.js` 只允许人工确认后的候选样本进入训练集。

完整的分阶段差距审计和实施清单见 [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md)。实现顺序固定为：先完成连续字节链路智能分析，再做离线 IQ 接入、降噪和单一调制解调，最后接入实时 SDR 硬件。

## 离线 IQ 分析

`rf/` 已提供第一版可复现射频前端：读取 SigMF 的 complex float32 / complex int16 IQ 数据，执行去直流、噪声功率估计、突发检测、频谱峰值、占用带宽和无参考 SNR 估计。运行：

```bash
npm run test:rf
npm run diagnose:sdr
npm run fixture:iq
npm run analyze:iq
npm run demod:iq
npm run select:iq
npm run test:e2e
npm run evaluate:fsk
npm run evaluate:modulation
npm run evaluate:bpsk
npm run evaluate:qpsk
npm run evaluate:denoise
npm run evaluate:tone-denoise
npm run evaluate:rrc
npm run evaluate:clock-drift
npm run evaluate:gardner
npm run stream:replay
npm run stream:state
```

固定回归样本位于 `samples/iq/fsk_demo.sigmf-*`，对应质量和解调报告为 `reports/iq_quality_fsk_demo.json` 与 `reports/fsk_demod_report.json`。当前闭环对带频偏和噪声的2-FSK样本完成频偏估计、频移校正、FIR滤波、增益归一化、符号定时、判决和同步字搜索，随后把恢复字节交给原有协议解析器，验证出CRC有效的MAVLink 2心跳帧。

该样本由程序生成，只能证明处理步骤能够连通并被重复测试，不能证明真实无人机链路性能。现阶段解调器只支持2-FSK；下一步是接入真实IQ，并逐步增加其他调制候选。

`npm run select:iq` 会尝试800、1000、1200和2400 Bd四个2-FSK候选。当前样本中只有1200 Bd候选找到同步字并恢复CRC有效的MAVLink帧，其余候选连同失败原因一起保存在 `reports/fsk_candidate_selection.json`。这仍然是同一调制方式内的参数搜索，尚未实现任意调制识别。

`npm run evaluate:fsk` 对5档噪声和5档载波频偏执行25组确定性合成测试。当前结果为20/25组精确恢复：噪声标准差0.02～0.12、频偏−4 kHz～+4 kHz的组合全部通过；噪声标准差0.18的5组全部被突发检测门限拒绝，且没有产生CRC有效的错误帧。完整逐例记录见 `reports/fsk_robustness.json`。这是同一生成模型内的失败边界测试，只能作为回归证据。

GFSK作为第二种波形沿用同一频率判决主链，但在调制前加入BT=0.5的高斯脉冲整形。`rf/modulation_features.py` 根据瞬时频率中过渡区域的比例区分矩形2-FSK与GFSK，并在低SNR或模糊区间拒绝给出标签。`npm run evaluate:modulation` 的40组合成测试全部恢复CRC有效帧：30个较高SNR案例分类正确，10个低SNR案例拒识，错误分类为0。逐例证据位于 `reports/fsk_shape_evaluation.json`；该阈值尚未经过真实发射机和其他BT参数验证。

BPSK使用独立的相位调制链：平方去除数据符号、平方谱线峰值估计载波频偏、二阶相位估计、全符号定时搜索和同步字检验。`rf/waveform_selector.py` 同时尝试FSK族与BPSK，再以协议CRC为首要证据选路。`npm run evaluate:bpsk` 的20组合成测试覆盖噪声标准差0.02～0.12和频偏±500 Hz，20例全部精确恢复。错误调制选择和错误CRC接收均为0，逐例结果位于 `reports/bpsk_robustness.json`。

QPSK进一步使用四次方法消除数据符号、四次谱线峰值恢复载波，并遍历四种象限模糊和全部符号定时。`npm run evaluate:qpsk` 的20组合成测试覆盖噪声标准差0.02～0.12和频偏±400 Hz，20例全部精确恢复。错误调制选择和错误CRC接收均为0，逐例结果位于 `reports/qpsk_robustness.json`。

BPSK与QPSK现在同时尝试矩形脉冲的积分判决和滚降系数0.35的根升余弦匹配滤波判决；载波频偏由平方／四次谱线峰值估计，避免成形过渡区的低幅相位使相位展开失稳。`npm run evaluate:rrc` 对两种调制、3档噪声和3档频偏执行18组合成测试，18组均恢复正确载荷并通过MAVLink CRC，错误调制选择和错误CRC接收均为0。完整结果位于 `reports/rrc_psk_evaluation.json`。发射端和接收端仍使用同一套合成实现，尚未覆盖真实采样器漂移、多径、功放非线性和真实发射机。

RRC分支进一步在−10000～+10000 ppm的离散候选上改变符号采样周期，并用协议CRC、同步字误差和星座离散度依次排序。`npm run evaluate:clock-drift` 对BPSK/QPSK各5组恒定时钟偏移做消融：固定符号时钟精确恢复6/10组，启用漂移搜索后恢复10/10组，改善4组、回退0组，错误调制和错误CRC接收均为0。该范围用于在短突发中放大漂移效应，报告位于 `reports/psk_clock_drift_ablation.json`。

`rf/timing_recovery.py` 实现了带线性插值、归一化Gardner误差、频率积分项和±3%环路边界的定时恢复。`npm run evaluate:gardner` 使用4个连续MAVLink帧构成长突发，并令采样时钟由−10000 ppm线性漂移至+10000 ppm。在4档噪声、2个随机种子的8组测试中，固定漂移网格完整恢复0/8组，Gardner环完整恢复8/8组；每组4个协议帧均通过CRC。当前结果仍来自同源合成数据，尚未验证真实采样器的抖动、突变或多径耦合。报告位于 `reports/gardner_timing_evaluation.json`。

`rf/denoise.py` 提供稀疏脉冲干扰抑制：只在已检测突发内部，以幅度中位数和MAD形成稳健阈值，将占比不超过5%的离群采样用相邻正常复数采样插值；异常比例过高时拒绝处理。`npm run evaluate:denoise` 对四种波形各5组注入1%、幅度3.0的脉冲干扰。未处理链恢复12/20组，启用抑制后恢复20/20组，改善8组且回退0组。完整消融记录位于 `reports/impulse_denoise_ablation.json`。

连续窄带干扰采用边缘相干音抵消：只使用窗口首尾各10%的样本估计持续音调，通过零填充频谱获得粗频率、非均匀投影细化频率，再估计复幅度并从全窗相减；边缘相干度低于5 dB时拒绝处理。`npm run evaluate:tone-denoise` 在7、9、11 kHz和四种波形组成的12组案例中，将CRC有效恢复从5/12提高到12/12，改善7组、回退0组；对12组干净信号的错误启用为0。报告位于 `reports/tone_denoise_ablation.json`。

## SDR实时接收接口

`rf/stream_capture.py` 定义了统一采样接口、固定容量环形缓冲和SigMF落盘路径；`rf/soapy_source.py` 提供可选的SoapySDR适配器。没有安装SoapySDR及具体硬件驱动时，模块仍可导入并使用`ArraySource`完成同路径回放测试。

安装并配置硬件驱动后，可使用：

```bash
python -m rf.capture_sdr --list
python -m rf.capture_sdr --args "driver=设备驱动名" --frequency 433920000 --sample-rate 1000000 --duration 2 --gain 20 --output captures/test
```

真实采样报告会记录设备参数、接收样本数、超时、溢出、空读、时间戳跳变和环形缓冲覆盖数量。目前仓库中没有真实SDR硬件实测记录，因此实时接收仍属于“接口与回放已验证、硬件未验证”。

`npm run diagnose:sdr` 会检查SoapySDR Python绑定、设备枚举结果和当前阻塞项，并把结果写入 `reports/hardware_readiness.json`。当前机器的报告为：绑定未安装、枚举设备数0、`readyForCapture=false`。安装与具体接收硬件匹配的SoapySDR运行库、Python绑定和厂商驱动后，应重新运行该命令，再进行有限SigMF采样和连续运行验证。

`rf/full_pipeline.py` 已把统一采样源、信号质量分析、2-FSK候选解调和协议CRC反馈连接成有限窗口闭环。数组回放测试能够从分块采样重新选择1200 Bd并恢复有效MAVLink帧。

`rf/streaming_pipeline.py` 进一步用有界队列隔离采样线程与分析阶段，支持连续分块、背压计数、设备异常上报、逐窗口协议判定和MAVLink序号连续性检查。`rf/protocol_state.py` 将CRC有效的心跳、命令和应答跨窗口连接成状态证据，报告缺少解锁前提、孤立应答和缺少应答；重复帧不会再次推进状态。“TAKEOFF已接受”只表示命令应答，不代表飞行器已经离地。`npm run stream:replay` 将固定录制连续回放3次，当前3个窗口均选择1200 Bd并恢复CRC有效帧；重复序号被记录为2次重复，最终状态保持为 `disarmed`。报告写入 `reports/streaming_pipeline.json`。报告中的延迟来自本机数组回放，只用于软件回归，不能代替真实SDR的实时性能测量。

`npm run stream:state` 执行更完整的合成射频轨迹：未解锁心跳、解锁命令、成功应答、已解锁心跳、起飞命令和成功应答分别编码为6个2-FSK IQ窗口。当前6个窗口全部完成解调和CRC验证，最终形成2组命令—应答关系并到达 `takeoff-accepted`，没有状态违规；报告位于 `reports/streaming_state_trajectory.json`。

真实SDR的操作者控制入口为：

```bash
python -m rf.live_analyze --args "driver=设备驱动名" --frequency 433920000 --sample-rate 1000000 --gain 20 --symbol-rates 1200 --modulations fsk bpsk qpsk --max-duration 3600 --output captures/live-report.json
```

运行期间按 Ctrl+C 会请求安全停止；系统完成当前已接收分块、关闭SDR流并写出停止原因、有效窗口、延迟、序号连续性和协议状态证据。该入口及停止流程已通过数组源测试，但仓库目前没有真实SDR长时间运行记录。

网页交互原型仍从**已解调的字节**开始；仓库中的离线后端和流式采样接口已能处理合成2-FSK、BT=0.5 GFSK、BPSK和QPSK IQ，但尚无真实SDR实测，也不能处理任意调制或加密流。未知字段的业务含义、协议名称及设备行为无法仅从孤立字节证明；结构发现也不能保证覆盖所有封装方式。MAVLink 2 签名位会显示，但尚未进行签名认证。规则判定是演示算法，不构成飞控安全认证；SBUS 通道值不依赖具体遥控器的校准范围解释为物理量。

## 测试与构建

安装 Node.js 后运行 `npm test`，验证解析、校验、异常数据、规则重跑，以及未知协议样本的结构发现和证据不足时的拒绝推断。运行 `python scripts/build_standalone.py` 可重新生成单文件版。无需安装前端依赖。

`figures/` 单独存放申报书图片代码、最终 SVG 和原始 SVG；见 [图片代码说明](figures/README.md)。`presentation/` 保存实际操作录屏及适合插入 PPT 的 8 张关键帧。

## 协议依据

- [MAVLink 帧序列化与校验](https://mavlink.io/en/guide/serialization.html)
- [MAVLink common 消息定义](https://mavlink.io/en/messages/common)
- [ArduPilot SBUS 解码实现](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_RCProtocol/AP_RCProtocol_SBUS.cpp)
- [Discoverer：从网络轨迹自动推断消息格式](https://www.usenix.org/conference/16th-usenix-security-symposium/presentation/discoverer-automatic-protocol-reverse-enginee)
- [NetPlier：从消息轨迹进行概率协议逆向](https://www.ndss-symposium.org/ndss-paper/netplier-probabilistic-network-protocol-reverse-engineering-from-message-traces/)
