# Docker 部署：Server 与引擎同镜像

本方式以包含 `pdf2zh_next` 的引擎镜像为基础，安装本项目 Server 的依赖并在同一个容器中运行。部署文件位于 `deployment/docker/engine-image/`，不需要挂载宿主 Docker socket。

这套配置默认提供 `pdf2zh_next`，不会自动安装 Wenyi。需要独立引擎容器的部署方法，参见[另一种 Docker 方式](../engine-container/README.md)。

## 1. 准备 Docker 和部署文件

请先按 [Docker 官方安装说明](https://docs.docker.com/get-started/get-docker/) 准备 Docker，并确认以下命令可用：

```shell
docker version
docker compose version
```

使用已有仓库时，在仓库根目录进入：

```shell
cd deployment/docker/engine-image
```

只部署生产服务时，也可以只下载两个文件。以下命令在 Windows PowerShell、macOS 和 Linux 中均可按行执行；Windows 使用 `curl.exe`：

```shell
mkdir zotero-pdf2zh-image
cd zotero-pdf2zh-image
curl -fL -o Dockerfile https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/deployment/docker/engine-image/Dockerfile
curl -fL -o docker-compose.yaml https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/deployment/docker/engine-image/docker-compose.yaml
```

后续生产命令均在包含这两个文件的目录中执行。首次启动后数据目录如下：

```text
当前目录/
├── Dockerfile
├── docker-compose.yaml
└── zotero-pdf2zh/
    ├── config/          # Server 配置与模板
    ├── translated/      # 翻译结果与任务工作目录
    └── 自定义字体.ttf    # 可选
```

## 2. 启动和连接插件

```shell
docker compose up -d --build
docker compose logs -f
```

日志中出现服务在 `0.0.0.0:8890` 监听后，在同机 Zotero 插件中将 Python Server IP 设置为 `http://127.0.0.1:8890`；远程部署填写宿主机地址。

启动时关闭 Server 内部的虚拟环境管理和自动更新检查。Server 包在构建时按 `SERVER_URL` 下载，依赖从该包的 `server/requirements.txt` 安装。引擎来自 `ZOTERO_PDF2ZH_FROM_IMAGE` 基础镜像。

配置模板在镜像中另行保存，启动脚本会将模板复制到挂载的 `config/` 中，再由 Server 创建或补充实际配置，保留已有用户值。翻译参数仍由插件随任务提交。

## 3. 更新和日常管理

| 用途              | 命令                                           |
| ----------------- | ---------------------------------------------- |
| 查看状态          | `docker compose ps`                            |
| 查看日志          | `docker compose logs -f`                       |
| 停止 / 恢复       | `docker compose stop` / `docker compose start` |
| 重启进程          | `docker compose restart`                       |
| 停止并删除容器    | `docker compose down`                          |
| 检查 Compose 配置 | `docker compose config`                        |

修改 `SERVER_URL`、Dockerfile 或需要重新下载 Server 包时：

```shell
docker compose build --pull --no-cache
docker compose up -d
```

`restart` 只重启现有容器进程，不会重新构建镜像或重新下载 Server。备份和迁移时保留 `zotero-pdf2zh/config/` 与 `zotero-pdf2zh/translated/`。

## 4. 开发模式：使用当前仓库源码

开发模式需要完整 checkout，不能只把开发 Compose 文件单独下载到任意目录。目录关系必须保持为：

```text
仓库根目录/
├── server/
│   ├── server.py
│   ├── pdf2zh_server/
│   └── config/
└── deployment/docker/engine-image/
    ├── Dockerfile
    ├── docker-compose.yaml
    └── docker-compose.dev.yaml
```

从仓库根目录执行：

```shell
cd deployment/docker/engine-image
docker compose down
docker compose -f docker-compose.dev.yaml up -d --build
docker compose -f docker-compose.dev.yaml logs -f
```

`../../../server:/app/server` 把当前源码挂入容器；开发配置直接使用仓库的 `server/config/`，翻译输出沿用本目录的 `zotero-pdf2zh/translated/`。开发 Compose 跳过生产模板复制，避免覆盖仓库中的模板。生产与开发均使用宿主端口 `8890`，不能同时启动。

- 修改 Python 源码后运行 `docker compose -f docker-compose.dev.yaml restart`。当前启动命令未启用自动重载。
- 修改依赖后，将依赖更新到实际用于构建的 Server 包，再执行 `docker compose -f docker-compose.dev.yaml build --no-cache` 和 `docker compose -f docker-compose.dev.yaml up -d`；运行中的源码挂载不会安装依赖。
- 修改端口、挂载或环境变量后执行 `docker compose -f docker-compose.dev.yaml up -d` 重新创建容器。
- 回到生产方式前，先 `docker compose -f docker-compose.dev.yaml down`，再 `docker compose up -d`。

## 5. 字体、端口和下载源

需要字体时，先准备 `zotero-pdf2zh/LXGWWenKai-Regular.ttf`，再在所用 Compose 文件中取消或加入以下挂载：

```yaml
- ./zotero-pdf2zh/LXGWWenKai-Regular.ttf:/app/LXGWWenKai-Regular.ttf:ro
```

参数中使用容器内的 `/app/LXGWWenKai-Regular.ttf`。默认配置不会挂载不存在的字体文件。

如果端口 `8890` 被占用，将 `ports` 改为 `"8891:8890"`，插件地址相应改为 `http://127.0.0.1:8891`。修改后运行 `docker compose up -d`。

网络受限时，在 `build.args` 中修改 `SERVER_URL` 为自己可用的完整发布包地址。需要固定版本时使用已有 tag 或 commit 对应的 `server.zip`，不要只更换基础镜像而忽略 Server 包来源。Docker 镜像加速按宿主 Docker 配置，参见 [Docker 文档](https://docs.docker.com/docker-hub/image-library/mirror/)。

本方式的基础镜像由社区维护，具体引擎版本以所拉取的镜像为准；仅重新启动容器不会更新引擎。
