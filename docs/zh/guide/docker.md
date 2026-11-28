# Docker 部署

Docker 部署将 Server 和翻译引擎放在容器中运行。插件仍安装在 Zotero 中，通过 HTTP 连接 Server。

## 选择部署方式

仓库保留两种部署方式，按运行方式分类：

| 目录                                  | 运行方式                                 | 适用情况                                              |
| ------------------------------------- | ---------------------------------------- | ----------------------------------------------------- |
| `deployment/docker/engine-image/`     | Server 与 `pdf2zh_next` 在同一镜像中运行 | 日常 Next 翻译，以及需要 Next Python 运行时适配的功能 |
| `deployment/docker/engine-container/` | Server 通过宿主 Docker 启动独立 Next 引擎容器 | 独立管理 Next 引擎镜像 |

两套配置默认映射宿主端口 `8890`，选择其中一套启动即可。独立引擎方式需要挂载 Docker socket；它的服务镜像只安装 Server 依赖，不提供本地 Next Python 环境，表格增强、跳过参考文献、自定义中转等运行时适配请使用 `engine-image`。

默认 Docker 配置不会安装 Wenyi；Server 的其他安装方式与引擎配置见[安装指南](/zh/guide/installation)和[配置说明](/zh/guide/configuration)。

## 前置要求

先按 [Docker 官方说明](https://docs.docker.com/get-started/get-docker/) 准备 Docker，确认 Docker 已启动：

```shell
docker version
docker compose version
```

Windows Docker Desktop 使用 Linux 容器。下面以 `engine-image` 为例。

## 快速开始

### 1. 准备部署文件

已有仓库时，在仓库根目录执行：

```shell
cd deployment/docker/engine-image
```

只部署服务时，也可以单独下载两个文件。Windows PowerShell 使用 `curl.exe`；macOS / Linux 使用 `curl`：

```shell
mkdir zotero-pdf2zh-image
cd zotero-pdf2zh-image
curl -fL -o Dockerfile https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/deployment/docker/engine-image/Dockerfile
curl -fL -o docker-compose.yaml https://raw.githubusercontent.com/yankang104/zotero-pdf2zh/main/deployment/docker/engine-image/docker-compose.yaml
```

后续命令均在包含 `Dockerfile` 和 `docker-compose.yaml` 的目录中运行。

### 2. 构建和启动

```shell
docker compose up -d --build
docker compose logs -f
```

Server 包在构建时下载，引擎由基础镜像提供。看到日志中的服务监听地址后，在同机 Zotero 插件中填写 `http://127.0.0.1:8890`。远程部署填写宿主机地址。

### 3. 保存数据

首次启动生成以下宿主目录：

```text
zotero-pdf2zh/
├── config/          # Server 配置与模板
└── translated/      # 翻译结果与任务工作目录
```

启动脚本补充配置模板，Server 按已有规则保留用户配置值。迁移部署时备份这两个目录。插件自己的服务商配置仍保存在 Zotero 偏好设置中。

## 开发模式

开发模式需要完整仓库，并保留 `deployment/docker/engine-image/` 与根目录 `server/` 的相对关系。从仓库根目录执行：

```shell
cd deployment/docker/engine-image
docker compose down
docker compose -f docker-compose.dev.yaml up -d --build
```

开发 Compose 使用 `../../../server:/app/server` 挂载当前源码，配置直接写入仓库的 `server/config/`，输出仍保存在部署目录的 `zotero-pdf2zh/translated/`。生产和开发模式不能同时占用端口 `8890`。

修改 Python 后需要重启进程：

```shell
docker compose -f docker-compose.dev.yaml restart
```

源码挂载不会自动重载 Python 或安装依赖。依赖变化需要更新构建所用的 Server 包并重新构建镜像；端口、挂载或环境变量变化需要执行对应的 `up -d` 重新创建容器。

## 管理与更新

| 用途           | 命令                                           |
| -------------- | ---------------------------------------------- |
| 查看状态       | `docker compose ps`                            |
| 查看日志       | `docker compose logs -f`                       |
| 停止 / 恢复    | `docker compose stop` / `docker compose start` |
| 重启现有进程   | `docker compose restart`                       |
| 停止并删除容器 | `docker compose down`                          |
| 查看最终配置   | `docker compose config`                        |

需要更新 Server 包或基础镜像时，重新下载相应部署文件后执行：

```shell
docker compose build --pull --no-cache
docker compose up -d
```

生产镜像使用构建时下载的 Server 包，本地 checkout 的 Python 修改不会自动进入镜像。仅执行 `restart` 不会更新代码或引擎。

如果端口冲突，将 Compose 的 `ports` 改成 `"8891:8890"`，并同步修改插件地址。需要字体时，先准备实际文件，再加入对应的只读挂载。Server 下载源通过构建参数 `SERVER_URL` 调整，镜像加速按宿主 Docker 配置。

## 两种方式的详细说明

- [Server 与引擎同镜像：生产、开发、字体和更新](https://github.com/yankang104/zotero-pdf2zh/blob/main/deployment/docker/engine-image/README.md)
- [独立引擎容器：Docker socket、引擎镜像和下载源](https://github.com/yankang104/zotero-pdf2zh/blob/main/deployment/docker/engine-container/README.md)
- [配置说明](/zh/guide/configuration)
- [常见问题](/zh/guide/faq/)
