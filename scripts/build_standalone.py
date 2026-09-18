"""Create a file:// compatible single-HTML release from the source tree."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
html=(root/'index.html').read_text(encoding='utf-8')
css=(root/'src'/'style.css').read_text(encoding='utf-8')
html=html.replace('<link rel="stylesheet" href="src/style.css">',f'<style>\n{css}\n</style>')
for name in ['decoder.js','discovery.js','samples.js','app.js']:
    script=(root/'src'/name).read_text(encoding='utf-8')
    html=html.replace(f'<script src="src/{name}"></script>',f'<script>\n{script}\n</script>')
dest=root/'dist'/'谱航智析_字节流协议分析Demo.html';dest.parent.mkdir(exist_ok=True)
dest.write_text(html,encoding='utf-8')
print(dest)
