"""不依赖测试文件嵌套深度的仓库路径。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
