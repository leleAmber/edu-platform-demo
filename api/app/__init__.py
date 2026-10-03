"""课伴AI 移动端后端（FastAPI）。

bootstrap 放在包初始化里：任何 `import app.xxx` 都会先定位 core/ 并注入配置，
这样无论从哪个模块进来，`from core import ...` 都不会因为 sys.path 没准备好而失败。
"""

from . import config as _config

_config.bootstrap()
