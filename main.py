# pip install requests flask flask-cors

import requests
import uuid
import time
import json
import os
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS # 引入 CORS

# ==================== 配置区域 ====================
# 请将您的有效 token 放在这里，或通过环境变量 QWEN_AUTH_TOKEN 设置
# 获取方法：登录 chat.qwen.ai -> 开发者工具F12 -> 顶栏 Application/应用 -> 左侧栏 LocalStorage/本地存储 -> 下拉菜单 https://chat.qwen.ai -> 右侧找到token，整段复制值，放到下方
QWEN_AUTH_TOKEN = os.environ.get("QWEN_AUTH_TOKEN")
if not QWEN_AUTH_TOKEN:
    # 如果环境变量未设置，请在此处直接填写你的 token
    QWEN_AUTH_TOKEN = ""
IS_DELETE = 0  # 是否在单次对话结束后删除对话记录，1 为删除，0 为不删除
PORT = 5000  # 服务端运行端口
# 模型名映射，基于实际返回的模型列表
MODEL_MAP = {
    "qwen": "qwen3-235b-a22b", # 默认旗舰模型
    "qwen3": "qwen3-235b-a22b",
    "qwen3-coder": "qwen3-coder-plus",
    "qwen3-moe": "qwen3-235b-a22b",
    "qwen3-dense": "qwen3-32b",
    "qwen-max": "qwen-max-latest",
    "qwen-plus": "qwen-plus-2025-01-25",
    "qwen-turbo": "qwen-turbo-2025-02-11",
    "qwq": "qwq-32b",
    # OpenAI 常见模型映射到 Qwen 对应能力模型
    "gpt-3.5-turbo": "qwen-turbo-2025-02-11", # 快速高效
    "gpt-4": "qwen-plus-2025-01-25",         # 复杂任务
    "gpt-4-turbo": "qwen3-235b-a22b",       # 最强大
}
# =================================================

class QwenClient:
    """
    用于与 chat.qwen.ai API 交互的客户端。
    封装了创建对话、发送消息、接收流式响应及删除对话的逻辑。
    """
    def __init__(self, auth_token: str, base_url: str = "https://chat.qwen.ai"):
        self.auth_token = auth_token
        self.base_url = base_url
        self.session = requests.Session()
        # 初始化时设置基本请求头
        self.session.headers.update({
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "source": "web",
        })
        self.user_info = None
        self.models_info = None
        self.user_settings = None
        self._initialize()

    def _initialize(self):
        """初始化客户端，获取用户信息、模型列表和用户设置"""
        self._update_auth_header()
        try:
            # 获取用户信息
            user_info_res = self.session.get(f"{self.base_url}/api/v1/auths/")
            user_info_res.raise_for_status()
            self.user_info = user_info_res.json()

            # 获取模型列表
            models_res = self.session.get(f"{self.base_url}/api/models")
            models_res.raise_for_status()
            self.models_info = {model['id']: model for model in models_res.json()['data']}

            # 获取用户设置
            settings_res = self.session.get(f"{self.base_url}/api/v2/users/user/settings")
            settings_res.raise_for_status()
            self.user_settings = settings_res.json()['data']

        except requests.exceptions.RequestException as e:
            print(f"客户端初始化失败: {e}")
            raise

    def _update_auth_header(self):
        """更新会话中的认证头"""
        self.session.headers.update({"authorization": f"Bearer {self.auth_token}"})

    def _get_qwen_model_id(self, openai_model: str) -> str:
        """将 OpenAI 模型名称映射到 Qwen 模型 ID"""
        # 如果直接匹配到 key，则使用映射值；否则尝试看模型 ID 是否直接存在于 Qwen 模型列表中；最后回退到默认模型
        mapped_id = MODEL_MAP.get(openai_model)
        if mapped_id and mapped_id in self.models_info:
            return mapped_id
        elif openai_model in self.models_info:
            return openai_model # OpenAI 模型名恰好与 Qwen ID 相同
        else:
            print(f"模型 '{openai_model}' 未找到或未映射，使用默认模型 'qwen3-235b-a22b'")
            return "qwen3-235b-a22b" # 最可靠的回退选项

    def create_chat(self, model_id: str, title: str = "新对话") -> str:
        """创建一个新的对话"""
        self._update_auth_header() # 确保 token 是最新的
        url = f"{self.base_url}/api/v2/chats/new"
        payload = {
            "title": title,
            "models": [model_id],
            "chat_mode": "normal",
            "chat_type": "t2t", # Text to Text
            "timestamp": int(time.time() * 1000)
        }
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            chat_id = response.json()['data']['id']
            print(f"成功创建对话: {chat_id}")
            return chat_id
        except requests.exceptions.RequestException as e:
            print(f"创建对话失败: {e}")
            raise

    def delete_chat(self, chat_id: str):
        """删除一个对话"""
        self._update_auth_header() # 确保 token 是最新的
        url = f"{self.base_url}/api/v2/chats/{chat_id}"
        
        if IS_DELETE == 1:
            try:
                response = self.session.delete(url)
                response.raise_for_status()
                res_data = response.json()
                if res_data.get('success', False):
                    print(f"成功删除对话: {chat_id}")
                else:
                    print(f"删除对话 {chat_id} 返回 success=False: {res_data}")
            except requests.exceptions.RequestException as e:
                # 删除失败不应中断主流程，仅记录日志
                print(f"删除对话失败 {chat_id}: {e}")
            except json.JSONDecodeError:
                print(f"删除对话时无法解析 JSON 响应 {chat_id}")
        return

    def chat_completions(self, openai_request: dict):
        """
        执行聊天补全，模拟 OpenAI API。
        返回流式生成器或非流式 JSON 响应。
        """
        self._update_auth_header() # 确保 token 是最新的
        
        # 解析 OpenAI 请求
        model = openai_request.get("model", "qwen3")
        messages = openai_request.get("messages", [])
        stream = openai_request.get("stream", False)
        # 解析新增参数
        enable_thinking = openai_request.get("enable_thinking", True) # 默认启用思考
        thinking_budget = openai_request.get("thinking_budget", None) # 默认不指定

        # 映射模型
        qwen_model_id = self._get_qwen_model_id(model)

        # 拼接上下文消息
        formatted_history = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
        if messages[0]['role'] != "system":
            formatted_history = "system:\n\n" + formatted_history
        user_input = formatted_history

        # 创建新对话
        chat_id = self.create_chat(qwen_model_id, title=f"OpenAI_API_对话_{int(time.time())}")

        try:
            # 准备请求负载
            timestamp_ms = int(time.time() * 1000)
            
            # 构建 feature_config
            feature_config = {
                "output_schema": "phase"
            }
            if enable_thinking:
                feature_config["thinking_enabled"] = True
                # 如果提供了 thinking_budget 则使用，否则尝试从用户设置获取
                if thinking_budget is not None:
                    feature_config["thinking_budget"] = thinking_budget
                else:
                    # 尝试从用户设置中获取默认的 thinking_budget
                    default_budget = self.user_settings.get('model_config', {}).get(qwen_model_id, {}).get('thinking_budget')
                    if default_budget:
                        feature_config["thinking_budget"] = default_budget
            else:
                feature_config["thinking_enabled"] = False

            payload = {
                "stream": True, # 始终使用流式以获取实时数据
                "incremental_output": True,
                "chat_id": chat_id,
                "chat_mode": "normal",
                "model": qwen_model_id,
                "parent_id": None,
                "messages": [{
                    "fid": str(uuid.uuid4()),
                    "parentId": None,
                    "childrenIds": [str(uuid.uuid4())],
                    "role": "user",
                    "content": user_input,
                    "user_action": "chat",
                    "files": [],
                    "timestamp": timestamp_ms,
                    "models": [qwen_model_id],
                    "chat_type": "t2t",
                    "feature_config": feature_config,
                    "extra": {"meta": {"subChatType": "t2t"}},
                    "sub_chat_type": "t2t",
                    "parent_id": None
                }],
                "timestamp": timestamp_ms
            }

            # 添加必要的头
            headers = {
                "x-accel-buffering": "no" # 对于流式响应很重要
            }

            url = f"{self.base_url}/api/v2/chat/completions?chat_id={chat_id}"
            
            if stream:
                # 流式请求
                def generate():
                    try:
                        # 使用流式请求，并确保会话能正确处理连接
                        with self.session.post(url, json=payload, headers=headers, stream=True) as r:
                            r.raise_for_status()
                            finish_reason = "stop"
                            reasoning_text = ""  # 用于累积 thinking 阶段的内容
                            has_sent_content = False # 标记是否已经开始发送 answer 内容

                            for line in r.iter_lines(decode_unicode=True):
                                # 检查标准的 SSE 前缀
                                if line.startswith("data: "):
                                    data_str = line[6:]  # 移除 'data: '
                                    if data_str.strip() == "[DONE]":
                                        # 在发送最终块之前，如果还有未发送的 reasoning_text，发送它
                                        # （理论上 finished 块应该已经处理了，但作为后备）
                                        # 发送最终的 done 消息块，包含 finish_reason
                                        final_chunk = {
                                            "id": f"chatcmpl-{chat_id[:10]}",
                                            "object": "chat.completion.chunk",
                                            "created": int(time.time()),
                                            "model": model,
                                            "choices": [{
                                                "index": 0,
                                                # 如果从未发送过 content，最后一次发送空 delta 和 finish_reason
                                                # 如果发送过，这次也发送 finish_reason
                                                "delta": {}, 
                                                "finish_reason": finish_reason
                                            }]
                                        }
                                        yield f"data: {json.dumps(final_chunk)}\n\n"
                                        yield "data: [DONE]\n\n"
                                        break
                                    try:
                                        data = json.loads(data_str)
                                        # 处理 choices 数据
                                        if "choices" in data and len(data["choices"]) > 0:
                                            choice = data["choices"][0]
                                            delta = choice.get("delta", {})
                                            
                                            # --- 重构逻辑：清晰区分 think 和 answer 阶段 ---
                                            phase = delta.get("phase")
                                            status = delta.get("status")
                                            content = delta.get("content", "")

                                            # 1. 处理 "think" 阶段
                                            if phase == "think":
                                                if status != "finished":
                                                    reasoning_text += content
                                                # 注意：think 阶段的内容不直接发送，只累积

                                            # 2. 处理 "answer" 阶段 或 无明确 phase 的内容 (兼容性)
                                            #    (有些早期数据块可能没有 phase，但包含实际回复内容)
                                            elif phase == "answer" or (phase is None and content):
                                                # 一旦进入 answer 阶段或有内容，标记为已开始
                                                has_sent_content = True 
                                                # 构造包含 content 的流式块
                                                openai_chunk = {
                                                    "id": f"chatcmpl-{chat_id[:10]}",
                                                    "object": "chat.completion.chunk",
                                                    "created": int(time.time()),
                                                    "model": model,
                                                    "choices": [{
                                                        "index": 0,
                                                        "delta": {"content": content},
                                                        "finish_reason": None # answer 阶段进行中不设 finish_reason
                                                    }]
                                                }
                                                # 如果累积了 reasoning_text，则在第一个 answer 块或包含 content 的块中附带
                                                # 并在发送后清空，避免重复发送
                                                if reasoning_text:
                                                     openai_chunk["choices"][0]["delta"]["reasoning_content"] = reasoning_text
                                                     reasoning_text = "" # 发送后清空

                                                yield f"data: {json.dumps(openai_chunk)}\n\n"

                                            # 3. 处理结束信号 (通常在 answer 阶段的最后一个块)
                                            if status == "finished":
                                                finish_reason = delta.get("finish_reason", "stop")
                                                # 注意：[DONE] 信号会触发最终块的发送，所以这里不需要再 yield 一个带 finish_reason 的块
                                                # 除非我们想在 [DONE] 之前发送最后一个内容块同时带 finish_reason，
                                                # 但标准做法是在 [DONE] 时发送。
                                                # 当前逻辑是在 [DONE] 时发送最终块。

                                            # --- 重构逻辑结束 ---

                                    except json.JSONDecodeError:
                                        # 忽略无效的 JSON 行，但可以考虑记录警告
                                        # print(f"Warning: Skipping invalid JSON line: {line}")
                                        continue
                    except requests.exceptions.RequestException as e:
                        print(f"流式请求失败: {e}")
                        # 发送一个错误块
                        error_chunk = {
                            "id": f"chatcmpl-error",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": f"Error during streaming: {str(e)}"},
                                "finish_reason": "error"
                            }]
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                    finally:
                        # 请求结束后删除对话
                        self.delete_chat(chat_id)

                return generate()

            else:
                # 非流式请求: 聚合流式响应
                response_text = ""  # 用于聚合最终回复
                reasoning_text = "" # 用于聚合 thinking 阶段的内容
                finish_reason = "stop"
                usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                try:
                    with self.session.post(url, json=payload, headers=headers, stream=True) as r:
                        r.raise_for_status()
                        for line in r.iter_lines(decode_unicode=True):
                            # 检查完整的 SSE 前缀
                            if line.startswith("data: "): 
                                data_str = line[6:] # 移除 'data: '
                                if data_str.strip() == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    
                                    # 处理 choices 数据来构建最终回复
                                    if "choices" in data and len(data["choices"]) > 0:
                                        delta = data["choices"][0].get("delta", {})
                                        
                                        # 累积 "think" 阶段的内容
                                        if delta.get("phase") == "think":
                                            if delta.get("status") != "finished":
                                                reasoning_text += delta.get("content", "")
                                        
                                        # 只聚合 "answer" 阶段的内容
                                        if delta.get("phase") == "answer":
                                            if delta.get("status") != "finished":
                                                response_text += delta.get("content", "")
                                        
                                        # 收集最后一次的 usage 信息
                                        if "usage" in data:
                                            qwen_usage = data["usage"]
                                            usage_data = {
                                                "prompt_tokens": qwen_usage.get("input_tokens", 0),
                                                "completion_tokens": qwen_usage.get("output_tokens", 0),
                                                "total_tokens": qwen_usage.get("total_tokens", 0),
                                            }
                                    
                                    # 检查是否是结束信号
                                    if "choices" in data and len(data["choices"]) > 0:
                                        delta = data["choices"][0].get("delta", {})
                                        if delta.get("status") == "finished":
                                            finish_reason = delta.get("finish_reason", "stop")
                                        
                                except json.JSONDecodeError:
                                    # 忽略无法解析的行
                                    continue
                    
                    # 构造非流式的 OpenAI 响应
                    openai_response = {
                        "id": f"chatcmpl-{chat_id[:10]}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": response_text
                            },
                            "finish_reason": finish_reason
                        }],
                        "usage": usage_data
                    }
                    
                    # 在非流式响应中添加 reasoning_content
                    if reasoning_text:
                        openai_response["choices"][0]["message"]["reasoning_content"] = reasoning_text
                    
                    return jsonify(openai_response)
                finally:
                    # 请求结束后删除对话
                    self.delete_chat(chat_id)

        except requests.exceptions.RequestException as e:
            # 确保在出错时也尝试删除对话
            self.delete_chat(chat_id)
            print(f"聊天补全失败: {e}")
            # 返回 OpenAI 格式的错误
            return jsonify({
                "error": {
                    "message": f"内部服务器错误: {str(e)}",
                    "type": "server_error",
                    "param": None,
                    "code": None
                }
            }), 500


# --- Flask 应用 ---
app = Flask(__name__)
# 配置 CORS，允许所有来源 (生产环境请根据需要进行限制)
CORS(app) 

# 初始化客户端
qwen_client = QwenClient(auth_token=QWEN_AUTH_TOKEN)

@app.route('/v1/models', methods=['GET'])
def list_models():
    """列出可用模型 (模拟 OpenAI API)"""
    try:
        # 从已获取的模型信息构造 OpenAI 格式列表
        openai_models = []
        for model_id, model_info in qwen_client.models_info.items():
            openai_models.append({
                "id": model_info['info']['id'],
                "object": "model",
                "created": model_info['info']['created_at'],
                "owned_by": model_info['owned_by']
            })
        return jsonify({"object": "list", "data": openai_models})
    except Exception as e:
        print(f"列出模型时出错: {e}")
        return jsonify({
            "error": {
                "message": f"获取模型列表失败: {e}",
                "type": "server_error",
                "param": None,
                "code": None
            }
        }), 500

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """处理 OpenAI 兼容的聊天补全请求"""
    openai_request = request.get_json()
    if not openai_request:
        return jsonify({
            "error": {
                "message": "请求体中 JSON 无效",
                "type": "invalid_request_error",
                "param": None,
                "code": None
            }
        }), 400

    stream = openai_request.get("stream", False)
    
    try:
        result = qwen_client.chat_completions(openai_request)
        if stream:
            # 如果是流式响应，`result` 是一个生成器函数
            return Response(stream_with_context(result), content_type='text/event-stream')
        else:
            # 如果是非流式响应，`result` 是一个 Flask Response 对象 (jsonify)
            return result
    except Exception as e:
        print(f"处理聊天补全请求时发生未预期错误: {e}")
        return jsonify({
            "error": {
                "message": f"内部服务器错误: {str(e)}",
                "type": "server_error",
                "param": None,
                "code": None
            }
        }), 500

@app.route('/', methods=['GET'])
def index():
    """根路径，返回 API 信息"""
    return jsonify({
        "message": "千问 (Qwen) OpenAI API 代理正在运行。",
        "docs": "https://platform.openai.com/docs/api-reference/chat"
    })

# 健康检查端点
@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # 从环境变量获取端口，默认为 5000
    port = int(os.environ.get("PORT", PORT))
    print(f"正在启动服务器于端口 {port}...")
    app.run(host='0.0.0.0', port=port, debug=False) # 生产环境请关闭 debug
