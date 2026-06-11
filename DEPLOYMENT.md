# Bear Code Docker 部署说明

Bear Code 可以作为 Docker 化的命令行工具运行。镜像中会内置一份项目代码到 `/app`，容器启动后的工作目录是 `/workspace`。实际使用时，通常把当前项目目录挂载到 `/workspace`，让 Bear Code 在这个目录里读取、搜索和修改代码。

## 1. 准备环境变量

先根据 `.env.example` 创建本地 `.env` 文件，并填入 API 配置：

```env
APIKEY=sk-your-api-key
API=https://api.deepseek.com/anthropic
MINI_CLAUDE_MODEL=claude-sonnet-4-6
```

如果使用 OpenAI 兼容接口，可以改成：

```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-host/v1
MINI_CLAUDE_MODEL=gpt-4o
```

也可以在运行时通过 `--api-base` 覆盖接口地址。

注意：不要把真实 API Key 写进 Dockerfile 或提交到 Git 仓库。推荐通过 `.env`、Docker Secret 或部署平台的密钥管理能力注入。

## 2. 构建镜像

在 Bear Code 项目根目录执行：

```bash
docker build -t bear-code .
```

构建完成后，本地会得到一个名为 `bear-code` 的镜像。

## 3. 启动交互式会话

在 Bear Code 项目根目录执行：

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code
```

参数说明：

- `--rm`：容器退出后自动删除容器本身。
- `-it`：开启交互式终端，适合进入 REPL 对话。
- `--env-file .env`：把本地 `.env` 中的 API 配置传入容器。
- `-v "$PWD:/workspace"`：把当前目录挂载到容器的 `/workspace`。
- `-v bear-code-sessions:/root/.bear-code`：用 Docker volume 持久化会话历史。
- `-v bear-code-memory:/root/.BearCode`：用 Docker volume 持久化长期记忆数据。

## 4. 为什么挂载后改动会直接生效

这条命令里有一个关键挂载：

```bash
-v "$PWD:/workspace"
```

它是 Docker 的 bind mount。含义是：把宿主机当前目录 `$PWD` 映射到容器里的 `/workspace`。容器运行时看到的 `/workspace` 不是镜像构建时复制进去的静态文件，而是宿主机目录的实时视图。

当前 Dockerfile 里还有两个细节：

```dockerfile
ENV PYTHONPATH=/app
WORKDIR /workspace
ENTRYPOINT ["python", "-m", "agents.main"]
```

镜像构建时会把 Bear Code 源码复制到 `/app`，但容器启动后工作目录是 `/workspace`。当你在 Bear Code 仓库根目录运行：

```bash
-v "$PWD:/workspace"
```

此时 `/workspace` 里也有本地的 `agents/` 目录。执行 `python -m agents.main` 时，Python 会先从当前工作目录 `/workspace` 查找 `agents` 包，再去 `PYTHONPATH=/app` 查找。因此，本地挂载进来的 `/workspace/agents` 会优先于镜像内置的 `/app/agents` 被加载。

所以，像修改 `agents/agent.py` 这种源码变更，只要你用上面的挂载方式启动容器，通常会直接生效，不需要重新 `docker build`。

需要重新构建镜像的常见情况：

- 修改了 `Dockerfile`。
- 修改了 `requirements.txt`，需要安装新的 Python 依赖。
- 没有把 Bear Code 源码目录挂载到 `/workspace`，而是完全依赖镜像内 `/app` 的代码。
- 部署到远端环境时不使用本地 bind mount，而是只运行打包好的镜像。

不需要重新构建镜像的常见情况：

- 修改了 `agents/*.py` 这类源码文件，并且当前 Bear Code 仓库通过 `$PWD:/workspace` 挂载进容器。
- 修改了 `.env` 后重新启动容器。
- 修改了被挂载目录中的普通项目文件。

## 5. 执行一次性任务

可以把提示词直接放在镜像名后面：

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code "阅读这个项目，并总结主要入口文件"
```

## 6. 常用运行选项

规划模式，只读分析，不直接改文件：

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  bear-code --plan "这个功能应该怎么重构？"
```

自动批准工具调用，适合你明确希望它直接执行修改的场景：

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  bear-code --yolo "运行测试并修复失败"
```

临时指定模型和接口地址：

```bash
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  bear-code --model gpt-4o --api-base https://example.com/v1 "hello"
```

## 7. 数据持久化

Bear Code 会在容器内写入两类数据：

- `/root/.bear-code`：会话历史、工具结果等运行数据。
- `/root/.BearCode`：长期记忆数据。

如果只使用 `--rm` 而不挂载 volume，容器退出后这些数据会丢失。推荐使用命名 volume：

```bash
-v bear-code-sessions:/root/.bear-code
-v bear-code-memory:/root/.BearCode
```

查看已有 volume：

```bash
docker volume ls
```

如果确认不再需要历史数据，可以删除：

```bash
docker volume rm bear-code-sessions bear-code-memory
```

## 8. 常见问题

### API key 缺失

如果看到类似 `API key is required` 的错误，检查 `.env` 是否存在，以及是否通过 `--env-file .env` 传入容器。

### 修改代码后没有生效

先确认启动命令是否包含：

```bash
-v "$PWD:/workspace"
```

并确认你是在 Bear Code 仓库根目录执行命令。如果你在其他目录运行，`$PWD` 指向的就不是 Bear Code 源码目录，容器内 `/workspace` 也不会包含本地修改后的 `agents/` 代码。

### 依赖变更后仍然报缺包

如果改了 `requirements.txt`，需要重新构建镜像：

```bash
docker build -t bear-code .
```

因为 Python 依赖是在镜像构建阶段安装的，不会因为挂载源码目录而自动重新安装。
