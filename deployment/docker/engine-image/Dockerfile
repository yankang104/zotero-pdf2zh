# --- Dockerfile (国内加速版) ---

# 接收一个构建参数，用于指定基础镜像的名称
ARG ZOTERO_PDF2ZH_FROM_IMAGE=awwaawwa/pdfmathtranslate-next:latest
# 从这个基础镜像开始构建
FROM ${ZOTERO_PDF2ZH_FROM_IMAGE}

# 设置工作目录
WORKDIR /app

# -----------------------------------------------------------------
# 【核心逻辑】基础镜像已经包含了 python 和 pdf2zh-next 引擎,
# 我们只需要安装 server.py 运行所需的额外依赖包即可。
# -----------------------------------------------------------------
# 【国内加速】直接启用阿里云镜像源, 加速 apt-get 下载
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends wget unzip && \
    rm -rf /var/lib/apt/lists/*

# 安装 server.py 运行需要的 flask 和 pypdf 等
# 注意：这里不再需要安装 pdf2zh-next

# 接收 server.py 的下载地址作为构建参数
ARG SERVER_URL=https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/server.zip
# 下载并解压 server.zip
RUN wget -O server.zip "$SERVER_URL" && \
    unzip -q server.zip && \
    rm server.zip

RUN uv pip install --system --no-cache-dir -r /app/server/requirements.txt

# 把模板保存在挂载点之外；每次启动复制模板，现有用户配置由 Server 自行迁移。
RUN mkdir -p /opt/pdf2zh-defaults && \
    cp /app/server/config/*.example /opt/pdf2zh-defaults/ && \
    printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'mkdir -p /app/server/config /app/server/translated' \
    'for template in /opt/pdf2zh-defaults/*.example; do' \
    '  cp "$template" "/app/server/config/${template##*/}"' \
    'done' \
    'exec "$@"' \
    > /usr/local/bin/start-server && chmod +x /usr/local/bin/start-server

# 为配置文件和翻译结果声明挂载点
VOLUME ["/app/server/config", "/app/server/translated"]

# 暴露新版 server.py 的默认端口
EXPOSE 8890

# 定义容器启动命令，并明确禁用 server.py 内部的 venv 管理。
# Docker 环境默认不做交互式更新检查，避免容器启动时等待用户输入。
ENTRYPOINT ["/usr/local/bin/start-server"]
CMD ["python", "/app/server/server.py", "--enable_venv=False", "--host=0.0.0.0", "--check_update=False", "--port=8890"]
