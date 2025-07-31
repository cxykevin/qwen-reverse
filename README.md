# Qwen API 逆向项目

这是一个逆向千问官方OpenWebUI站点 https://chat.qwen.ai 为本地API的项目，可以使用该站点的所有模型。

~~本代码完全由qwen3-coder编写~~，有bug别找我，复制粘贴去找qwen3-coder。。。

未测试输入token过长可能导致的问题，请自行尝试解决。

## 功能特点

- 兼容 OpenAI API 格式，支持 `chat.completions` 接口
- 支持流式和非流式响应，目前非流式工作原理为累计完整流式信息后拼接为非流式返回
- 自动模型名称映射（将 OpenAI 模型名转换为 Qwen 模型ID）
- 支持思维链（thinking）功能配置
- 自动管理对话会话（创建和清理）
- 支持 CORS，Health_check端点，方便前端调用

## 待添加功能

- 逆向生图、生视频功能
- 逆向深度研究功能

## 安装依赖

```bash
pip install requests flask flask-cors
```

## 配置

直接修改文件内容即可，项目仅一个main.py文件。

1. 通过环境变量设置认证令牌：
   ```bash
   export QWEN_AUTH_TOKEN="your_auth_token_here"
   ```

   或直接在代码中修改 `QWEN_AUTH_TOKEN` 变量（不推荐用于生产环境）。

2. 配置删除行为（可选）：
   - `IS_DELETE = 0`：不删除临时创建的对话（默认）
   - `IS_DELETE = 1`：在请求完成后自动删除临时对话

3. 配置服务端运行端口，默认给出的是5000

4. 若有需要，可自行修改模型名映射，不会影响/v1/model/接口的返回内容。

## 快速启动

```bash
python main.py
```

默认在端口 5000 启动服务。您也可以通过环境变量指定端口：
```bash
export PORT=8000
python main.py
```

## API 端点

- `GET /` - 服务器信息
- `GET /health` - 健康检查
- `GET /v1/models` - 列出可用模型
- `POST /v1/chat/completions` - 聊天补全接口（兼容 OpenAI 格式）

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

## 模型映射

代理自动将 OpenAI 模型名称映射到对应的 Qwen 模型：

| OpenAI 模型   | Qwen 模型             |
| ------------- | --------------------- |
| qwen, qwen3   | qwen3-235b-a22b       |
| qwen3-coder   | qwen3-coder-plus      |
| qwen-max      | qwen-max-latest       |
| qwen-plus     | qwen-plus-2025-01-25  |
| qwen-turbo    | qwen-turbo-2025-02-11 |
| gpt-3.5-turbo | qwen-turbo-2025-02-11 |
| gpt-4         | qwen-plus-2025-01-25  |
| gpt-4-turbo   | qwen3-235b-a22b       |

## 高级功能

### 思维链（Thinking）控制

通过以下参数控制模型的思考过程：

```json
{
  "model": "qwen",
  "messages": [{"role": "user", "content": "问题"}],
  "enable_thinking": true,
  "thinking_budget": 10
}
```

- `enable_thinking`: 是否启用思考过程（默认 true）
- `thinking_budget`: 思考步骤限制（可选）

## 注意事项

1. 需要有效的 Qwen 认证令牌才能工作
2. 临时对话默认不会自动删除（设置 `IS_DELETE = 1` 可启用自动删除）
3. 服务启动后会自动获取模型列表和用户设置
4. 生产环境建议设置适当的 CORS 限制

## 许可证

本项目采用 MIT 许可证。
