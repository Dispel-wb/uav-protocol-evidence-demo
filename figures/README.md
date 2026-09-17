# 申报书图片代码

- `final_svg/`：申报书采用的 5 张最终矢量图，可直接插入 Word 或演示文稿。
- `generate.py`：最终图的绘制源码。运行 `python figures/generate.py` 会重新输出 SVG；建议在独立副本上修改，避免覆盖已确认版。
- `original_svg/`：用户提供的原始 SVG 和生成代码，留作对照。

图片采用论文中常见的白色画布、深色文字与细线。深蓝和暗红只用于区分数据流、异常及关键路径，灰度也能读懂；节点内容包含协议字节、字段、判断或证据，而非纯装饰性卡片。图注在正文中单独排版。

## 推荐绘制软件

1. **[Inkscape](https://inkscape.org/)**：首选，免费且原生编辑 SVG。适合调整线条、文字、箭头、间距及导出高清 PNG／PDF。
2. **[diagrams.net 桌面版](https://github.com/jgraph/drawio-desktop)**：适合重新搭建流程结构、连线和决策节点。可[导出 SVG](https://www.drawio.com/docs/manual/export/export-to-svg/)，但本目录的程序化 SVG 并不等同于可直接恢复的 `.drawio` 工程。
3. **[Adobe Illustrator](https://helpx.adobe.com/illustrator/using/saving-artwork.html)**：已有授权时，可用于精细排版并保存 SVG。

修改流程：先在 `generate.py` 中调整结构和文字，重新生成 SVG；再用 Inkscape 作局部微调。若希望所有修改可复现，最终改动也应回写到源码。

