FROM python:3.9-slim

WORKDIR /app

# 只复制安装所需文件，利用层缓存
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# 安装带 server 可选依赖的包（server extra 提供 cryptography 作真实加密后端）
# 可选：构建时 --build-arg INSTALL_CAD=1 会额外安装真实 CadQuery/OpenCASCADE 内核
# （cad extra），用于参数化 B-Rep 建模；默认不装以保持镜像精简。
ARG INSTALL_CAD=0
RUN pip install --no-cache-dir ".[server]" \
    && if [ "${INSTALL_CAD}" != "0" ]; then pip install --no-cache-dir ".[cad]"; fi

# 默认以 server 模式运行状态服务（端口 8000）
ENV AIPD_MODE=server \
    AIPD_PORT=8000 \
    AIPD_DB_DIR=/data/state.db \
    AIPD_RETENTION_DAYS=90

EXPOSE 8000

# 健康检查端点 GET /health 由内置 HTTP 服务提供
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["python", "-c", "from aipd_os.state.server import main; main()"]
