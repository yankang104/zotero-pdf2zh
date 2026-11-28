# Docker 部署：独立引擎容器

本方式在服务容器中运行 Flask Server，通过宿主 Docker 启动独立的翻译引擎容器。部署文件位于 `deployment/docker/engine-container/`。

本方式调用独立 `pdf2zh_next` 引擎容器；Server 服务容器只安装 Server 依赖，Docker 命令包装器不提供本地 Next Python 环境。需要表格增强、跳过参考文献、自定义中转等 Next Python 运行时适配时，使用[同镜像运行 Server 与引擎的方式](../engine-image/README.md)。

## 1. 准备 Docker 和部署文件

确认 Docker 已启动，并可运行以下命令：

```shell
docker version
docker compose version
```

使用已有仓库时，在仓库根目录进入：

```shell
cd deployment/docker/engine-container
```

也可以只下载本方式的两个文件。以下命令在 Windows PowerShell、macOS 和 Linux 中均可按行执行；Windows 使用 `curl.exe`：

```shell
mkdir zotero-pdf2zh-container
cd zotero-pdf2zh-container
curl -fL -o Dockerfile https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/deployment/docker/engine-container/Dockerfile
curl -fL -o docker-compose.yaml https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/deployment/docker/engine-container/docker-compose.yaml
```

后续命令均在包含这两个文件的目录中运行。配置和输出首次启动时通过挂载目录保存：

```text
当前目录/
├── Dockerfile
├── docker-compose.yaml
├── config/          # Server 配置与模板
└── translated/      # 翻译结果与任务工作目录
```

本方式还会挂载 `/var/run/docker.sock`，供 Server 容器调用宿主 Docker。Docker Desktop 需要使用 Linux 容器。

## 2. 启动和连接插件

```shell
docker pull awwaawwa/pdfmathtranslate-next:latest
docker compose up -d --build
docker compose logs -f
```

服务监听容器内的 `0.0.0.0:8890`，映射到宿主端口 `8890`。在同一台计算机的 Zotero 插件中填写 `http://127.0.0.1:8890`；远程部署填写宿主机地址。

首次启动会把镜像中的配置模板复制到 `config/`，Server 按既有迁移规则生成或补充配置，保留已有用户值。`translated/.jobs/` 是翻译期间的任务目录，也通过同一挂载供引擎容器读取。

## 3. 配置、字体和端口

在 `docker-compose.yaml` 的 `environment` 中设置 `ZOTERO_PDF2ZH_FROM_IMAGE`，指定要调用的引擎镜像。插件选择的引擎须与 Dockerfile 中的命令包装器相匹配。

需要自定义字体时，先把实际字体文件放到当前目录，再在 `volumes` 中增加：

```yaml
- ./LXGWWenKai-Regular.ttf:/app/LXGWWenKai-Regular.ttf:ro
```

字体挂载会被独立引擎容器继承，相关字体路径填写容器内路径。修改卷或环境变量后执行 `docker compose up -d` 重新创建容器。

若端口被占用，把 `ports` 改为 `"8891:8890"`，并将插件地址改为 `http://127.0.0.1:8891`。

## 4. 下载源与更新

Server 在构建时从 `SERVER_ZIP_URL` 下载。可在 Compose 的 `build.args` 设置发布包地址，也可通过 `ZOTERO_PDF2ZH_SERVER_FILE_DOWNLOAD_URL` 环境变量覆盖默认值。

GitHub 连接较慢时，可以设置自己可用的代理前缀，或改用 CDN 地址：

```yaml
build:
  args:
    # 方式一：保留原地址，设置代理前缀
    GITHUB_PROXY_PREFIX: "https://你的代理前缀/"
    # 方式二：直接设置完整地址，同时清空代理前缀
    # SERVER_ZIP_URL: "https://cdn.jsdelivr.net/gh/yankang104/zotero-pdf2zh@main/server.zip"
    # GITHUB_PROXY_PREFIX: ""
```

需要固定版本时，把 `main` 改成已存在的 tag 或 commit。基础引擎镜像的拉取由宿主 Docker 处理；镜像加速设置参见 [Docker 文档](https://docs.docker.com/docker-hub/image-library/mirror/)。Python 依赖安装先使用 PyPI，失败时按 Dockerfile 原有配置回退到 USTC。

更新部署文件或 Server 包后执行：

```shell
docker compose build --no-cache
docker compose up -d
```

更新引擎还需先 `docker pull` 对应的 `ZOTERO_PDF2ZH_FROM_IMAGE` 镜像。已有仓库的本地 Python 修改不会自动进入生产镜像，Server 以构建时下载的包为准。

## 常用管理与排错

| 用途             | 命令                                           |
| ---------------- | ---------------------------------------------- |
| 查看状态         | `docker compose ps`                            |
| 查看日志         | `docker compose logs -f`                       |
| 停止 / 恢复服务  | `docker compose stop` / `docker compose start` |
| 重启进程         | `docker compose restart`                       |
| 停止并删除容器   | `docker compose down`                          |
| 查看合并后的配置 | `docker compose config`                        |

下载失败时核对构建日志的 `Download server from:` 地址；404 检查分支、tag 或地址，超时检查网络或下载源。引擎启动失败时同时检查宿主 Docker、引擎镜像是否拉取成功以及 Docker socket 挂载。

`config/` 和 `translated/` 保存在宿主目录。迁移部署时连同这两个目录备份；调整目录结构前先停止正在执行的任务。
