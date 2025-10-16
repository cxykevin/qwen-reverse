# Docker 部署指南

本项目提供了Docker支持，可以轻松地在容器中部署千问API代理服务。

## 快速开始

### 1. 准备工作

首先，获取您的千问认证令牌：

1. 进入 [chat.qwen.ai](https://chat.qwen.ai) 并登录您的账号
2. 打开 F12 开发者工具
3. 在顶端找到标签页 "Applications/应用"
4. 在左侧找到 "Local Storage/本地存储"，打开下拉菜单
5. 找到 chat.qwen.ai 并进入
6. 在右侧找到 "token" 的值，整段复制

### 2. 创建环境变量文件

创建 `.env` 文件：

```bash
# .env 文件
QWEN_AUTH_TOKEN=your_auth_token_here
PORT=5000
DEBUG_STATUS=false
```

### 3. 使用 Docker Compose 部署（推荐）

```bash
# 克隆仓库
git clone https://github.com/cxykevin/qwen-reverse.git
cd qwen-reverse

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4. 使用 Docker 直接部署

```bash
# 构建镜像
docker build -t qwen-reverse-alpine .

# 运行容器
docker run -d \
  --name qwen-reverse \
  -p 5000:5000 \
  -e QWEN_AUTH_TOKEN=your_auth_token_here \
  -e PORT=5000 \
  -v $(pwd)/chat_history.db:/app/chat_history.db \
  qwen-reverse-alpine
```

## 配置选项

### 环境变量

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `QWEN_AUTH_TOKEN` | 千问认证令牌 | 必需 |
| `PORT` | 服务端口 | 5000 |
| `DEBUG_STATUS` | 是否开启调试模式 | false |

### 数据持久化

Docker Compose 配置会自动持久化以下数据：

- `chat_history.db` - 聊天历史数据库
- `logs` - 日志文件目录（可选）

### 健康检查

容器包含健康检查，会定期检查 `/health` 端点：

- 检查间隔：30秒
- 超时时间：10秒
- 重试次数：3次
- 启动等待：40秒

## 使用示例

### 获取模型列表

```bash
curl http://localhost:5000/v1/models
```

### 发送聊天请求

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'
```

### 流式响应

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "请写一首关于春天的诗"}],
    "stream": true
  }'
```

## 故障排除

### 1. 容器启动失败

检查日志：
```bash
docker-compose logs qwen-reverse
```

常见问题：
- `QWEN_AUTH_TOKEN` 未设置或无效
- 端口被占用
- 网络连接问题

### 2. 数据库问题

如果数据库损坏，可以删除 `chat_history.db` 文件，容器会自动创建新的数据库。

### 3. 更新镜像

```bash
# 拉取最新镜像
docker-compose pull

# 重新构建并启动
docker-compose up -d --force-recreate
```

## 性能优化

- 使用多阶段构建的Alpine镜像，体积小、启动快
- 数据库持久化，避免数据丢失
- 健康检查确保服务可用性
- 非root用户运行，提高安全性

## 安全注意事项

- 不要在公开环境中暴露 `QWEN_AUTH_TOKEN`
- 生产环境建议配置适当的CORS限制
- 定期更新镜像以获取安全补丁

## 许可证

本项目采用 MIT 许可证。