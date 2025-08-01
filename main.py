# pip install requests flask flask-cors

import requests
import uuid
import time
import json
import os
import warnings
import sqlite3
import re
import html
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# ==================== 配置区域 ====================
# 请将您的有效 token 放在这里，或通过环境变量 QWEN_AUTH_TOKEN 设置
QWEN_AUTH_TOKEN = os.environ.get("QWEN_AUTH_TOKEN")
if not QWEN_AUTH_TOKEN:
    # 如果环境变量未设置，请在此处直接填写你的 token
    QWEN_AUTH_TOKEN = ""
IS_DELETE = 0  # 是否在会话结束后自动删除会话
PORT = 5000  # 服务端绑定的端口
DEBUG_STATUS = False  # 是否输出debug信息
DATABASE_PATH = "chat_history.db"  # 数据库文件路径
# 模型映射，基于实际返回的模型列表
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

os.environ['FLASK_ENV'] = 'production'  # 或 production
os.environ['FLASK_DEBUG'] = '0'
warnings.filterwarnings("ignore", message=".*development server.*")

def debug_print(message):
    """根据DEBUG_STATUS决定是否输出debug信息"""
    if DEBUG_STATUS:
        print(f"[DEBUG] {message}")

def remove_tool(text):
    # 使用正则表达式匹配 <tool_use>...</tool_use>，包括跨行内容
    pattern = r'<tool_use>.*?</tool_use>'
    # flags=re.DOTALL 使得 . 可以匹配换行符
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    return cleaned_text

class ChatHistoryManager:
    """管理聊天历史记录的本地存储"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    chat_id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at INTEGER,
                    updated_at INTEGER,
                    chat_type TEXT,
                    current_response_id TEXT,
                    last_assistant_content TEXT
                )
            ''')
            conn.commit()
            debug_print("数据库初始化完成")
        finally:
            conn.close()
    
    def update_session(self, chat_id: str, title: str, created_at: int, updated_at: int, 
                      chat_type: str, current_response_id: str, last_assistant_content: str):
        """更新或插入会话记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO chat_sessions 
                (chat_id, title, created_at, updated_at, chat_type, current_response_id, 
                 last_assistant_content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, title, created_at, updated_at, chat_type, current_response_id,
                  remove_tool(last_assistant_content)))
            conn.commit()
            debug_print(f"更新会话记录: {chat_id}")
        finally:
            conn.close()
    
    def get_session_by_last_content(self, content: str):
        """根据最新AI回复内容查找会话"""
        normalized_content = self.normalize_text(content)
        debug_print(f"查找会话，标准化内容: {normalized_content[:100]}...")
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT chat_id, current_response_id, last_assistant_content
                FROM chat_sessions 
                WHERE last_assistant_content IS NOT NULL
            ''')
            results = cursor.fetchall()
            
            debug_print(f"数据库中共有 {len(results)} 条会话记录")
            
            for row in results:
                chat_id, current_response_id, stored_content = row
                normalized_stored = self.normalize_text(stored_content)
                debug_print(f"比较会话 {chat_id}...")
                
                if normalized_content == normalized_stored:
                    debug_print(f"匹配成功！会话ID: {chat_id}")
                    return {
                        'chat_id': chat_id,
                        'current_response_id': current_response_id
                    }
            
            debug_print("未找到匹配的会话")
            return None
        finally:
            conn.close()
    
    def delete_session(self, chat_id: str):
        """删除会话记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM chat_sessions WHERE chat_id = ?', (chat_id,))
            conn.commit()
            debug_print(f"删除会话记录: {chat_id}")
        finally:
            conn.close()
    
    def clear_all_sessions(self):
        """清空所有会话记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM chat_sessions')
            conn.commit()
            debug_print("清空所有会话记录")
        finally:
            conn.close()
    
    def normalize_text(self, text: str) -> str:
        """标准化文本，处理转义字符、空白符等"""
        if not text:
            return ""
        
        # HTML解码
        text = html.unescape(text)
        # 去除多余空白字符
        text = re.sub(r'\s+', ' ', text.strip())
        # 去除常见的markdown符号
        text = re.sub(r'[*_`~]', '', text)
        # 去除emoji（简单处理）
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF✨🌟]', '', text)
        
        return text

class QwenClient:
    """
    用于与 chat.qwen.ai API 交互的客户端。
    封装了创建对话、发送消息、接收流式响应及删除对话的逻辑。
    """
    def __init__(self, auth_token: str, base_url: str = "https://chat.qwen.ai"):
        self.auth_token = auth_token
        self.base_url = base_url
        self.session = requests.Session()
        self.history_manager = ChatHistoryManager(DATABASE_PATH)
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
        # 启动时同步历史记录
        self.sync_history_from_cloud()

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

    def sync_history_from_cloud(self):
        """从云端同步历史记录到本地数据库"""
        debug_print("开始从云端同步历史记录")
        self._update_auth_header()
        
        try:
            # 清空本地记录
            self.history_manager.clear_all_sessions()
            
            page = 1
            while True:
                # 获取历史会话列表
                list_url = f"{self.base_url}/api/v2/chats/?page={page}"
                response = self.session.get(list_url)
                response.raise_for_status()
                data = response.json()
                
                if not data.get('success') or not data.get('data'):
                    break
                
                sessions = data['data']
                debug_print(f"第 {page} 页获取到 {len(sessions)} 个会话")
                
                if not sessions:
                    break
                
                # 获取每个会话的详细信息
                for session in sessions:
                    chat_id = session['id']
                    try:
                        detail_url = f"{self.base_url}/api/v2/chats/{chat_id}"
                        detail_response = self.session.get(detail_url)
                        detail_response.raise_for_status()
                        detail_data = detail_response.json()
                        
                        if not detail_data.get('success'):
                            continue
                        
                        chat_detail = detail_data['data']
                        messages = chat_detail.get('chat', {}).get('messages', [])
                        
                        # 提取最新的AI回复内容
                        last_assistant_content = ""
                        for msg in reversed(messages):
                            if msg.get('role') == 'assistant':
                                # 从content_list中提取内容
                                content_list = msg.get('content_list', [])
                                if content_list:
                                    last_assistant_content = content_list[-1].get('content', '')
                                else:
                                    last_assistant_content = msg.get('content', '')
                                break
                        
                        # 保存到本地数据库
                        current_response_id = chat_detail.get('currentId', '')
                        
                        self.history_manager.update_session(
                            chat_id=chat_id,
                            title=session.get('title', ''),
                            created_at=session.get('created_at', 0),
                            updated_at=session.get('updated_at', 0),
                            chat_type=session.get('chat_type', ''),
                            current_response_id=current_response_id,
                            last_assistant_content=last_assistant_content
                        )
                        
                    except Exception as e:
                        debug_print(f"获取会话 {chat_id} 详细信息失败: {e}")
                        continue
                
                page += 1
                
            debug_print("历史记录同步完成")
            
        except Exception as e:
            debug_print(f"同步历史记录失败: {e}")

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
            debug_print(f"成功创建对话: {chat_id}")
            return chat_id
        except requests.exceptions.RequestException as e:
            debug_print(f"创建对话失败: {e}")
            raise

    def delete_chat(self, chat_id: str):
        """删除一个对话"""
        self._update_auth_header() # 确保 token 是最新的
        url = f"{self.base_url}/api/v2/chats/{chat_id}"
        
        try:
            response = self.session.delete(url)
            response.raise_for_status()
            res_data = response.json()
            if res_data.get('success', False):
                debug_print(f"成功删除对话: {chat_id}")
                # 同时删除本地记录
                self.history_manager.delete_session(chat_id)
                return True
            else:
                debug_print(f"删除对话 {chat_id} 返回 success=False: {res_data}")
                return False
        except requests.exceptions.RequestException as e:
            debug_print(f"删除对话失败 {chat_id}: {e}")
            return False
        except json.JSONDecodeError:
            debug_print(f"删除对话时无法解析 JSON 响应 {chat_id}")
            return False

    def find_matching_session(self, messages: list):
        """根据消息历史查找匹配的会话"""
        debug_print("开始查找匹配的会话")
        
        # 检查是否有AI回复历史
        last_assistant_message = None
        for msg in reversed(messages):
            if msg.get('role') == 'assistant':
                last_assistant_message = msg
                break
        
        if not last_assistant_message:
            debug_print("请求中没有AI回复历史，将创建新会话")
            return None
        
        last_content = last_assistant_message.get('content', '')
        if not last_content:
            debug_print("最新AI回复内容为空，将创建新会话")
            return None
        
        debug_print("查找匹配...")
        
        # 查找匹配的会话
        matched_session = self.history_manager.get_session_by_last_content(last_content)
        
        if matched_session:
            debug_print(f"找到匹配的会话: {matched_session['chat_id']}")
            return matched_session
        else:
            debug_print("未找到匹配的会话，将创建新会话")
            return None

    def update_session_after_chat(self, chat_id: str, title: str, messages: list, 
                                  current_response_id: str, assistant_content: str):
        """聊天结束后更新会话记录"""
        debug_print(f"更新会话记录: {chat_id}")
        
        current_time = int(time.time())
        
        self.history_manager.update_session(
            chat_id=chat_id,
            title=title,
            created_at=current_time,
            updated_at=current_time,
            chat_type="t2t",
            current_response_id=current_response_id,
            last_assistant_content=assistant_content
        )

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

        debug_print(f"收到聊天请求，消息数量: {len(messages)}, 模型: {qwen_model_id}")
        # debug_print(f"收到的完整请求: \n{openai_request}\n")

        # 查找匹配的现有会话
        matched_session = self.find_matching_session(messages)
        
        chat_id = None
        parent_id = None
        user_input = ""
        
        if matched_session:
            # 使用现有会话进行增量聊天
            chat_id = matched_session['chat_id']
            parent_id = matched_session['current_response_id']
            
            # 只取最新的用户消息
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    user_input = msg.get('content', '')
                    break
            
            debug_print(f"使用现有会话 {chat_id}，parent_id: {parent_id}")
            # debug_print(f"用户输入: {user_input[:100]}...")
            
        else:
            # 创建新会话，拼接所有消息
            formatted_history = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            if messages and messages[0]['role'] != "system":
                formatted_history = "system:\n\n" + formatted_history
            user_input = formatted_history
            
            chat_id = self.create_chat(qwen_model_id, title=f"OpenAI_API_对话_{int(time.time())}")
            parent_id = None
            
            debug_print(f"创建新会话 {chat_id}")

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
                "parent_id": parent_id,
                "messages": [{
                    "fid": str(uuid.uuid4()),
                    "parentId": parent_id,
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
                    "parent_id": parent_id
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
                            assistant_content = ""  # 用于累积assistant回复内容
                            has_sent_content = False # 标记是否已经开始发送 answer 内容
                            current_response_id = None  # 当前回复ID

                            for line in r.iter_lines(decode_unicode=True):
                                # 检查标准的 SSE 前缀
                                if line.startswith("data: "):
                                    data_str = line[6:]  # 移除 'data: '
                                    if data_str.strip() == "[DONE]":
                                        # 发送最终的 done 消息块，包含 finish_reason
                                        final_chunk = {
                                            "id": f"chatcmpl-{chat_id[:10]}",
                                            "object": "chat.completion.chunk",
                                            "created": int(time.time()),
                                            "model": model,
                                            "choices": [{
                                                "index": 0,
                                                "delta": {}, 
                                                "finish_reason": finish_reason
                                            }]
                                        }
                                        yield f"data: {json.dumps(final_chunk)}\n\n"
                                        yield "data: [DONE]\n\n"
                                        break
                                    try:
                                        data = json.loads(data_str)
                                        
                                        # 提取response_id
                                        if "response.created" in data:
                                            current_response_id = data["response.created"].get("response_id")
                                            debug_print(f"获取到response_id: {current_response_id}")
                                        
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
                                            elif phase == "answer" or (phase is None and content):
                                                # 一旦进入 answer 阶段或有内容，标记为已开始
                                                has_sent_content = True 
                                                assistant_content += content  # 累积assistant回复
                                                
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
                                                # 如果累积了 reasoning_text，则在第一个 answer 块中附带
                                                if reasoning_text:
                                                     openai_chunk["choices"][0]["delta"]["reasoning_content"] = reasoning_text
                                                     reasoning_text = "" # 发送后清空

                                                yield f"data: {json.dumps(openai_chunk)}\n\n"

                                            # 3. 处理结束信号 (通常在 answer 阶段的最后一个块)
                                            if status == "finished":
                                                finish_reason = delta.get("finish_reason", "stop")

                                    except json.JSONDecodeError:
                                        continue
                    except requests.exceptions.RequestException as e:
                        debug_print(f"流式请求失败: {e}")
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
                        # 聊天结束后更新会话记录
                        if assistant_content and current_response_id:
                            # 构建完整的消息历史
                            updated_messages = messages.copy()
                            updated_messages.append({
                                "role": "assistant",
                                "content": assistant_content
                            })
                            
                            self.update_session_after_chat(
                                chat_id=chat_id,
                                title=f"OpenAI_API_对话_{int(time.time())}",
                                messages=updated_messages,
                                current_response_id=current_response_id,
                                assistant_content=assistant_content
                            )

                return generate()

            else:
                # 非流式请求: 聚合流式响应
                response_text = ""  # 用于聚合最终回复
                reasoning_text = "" # 用于聚合 thinking 阶段的内容
                finish_reason = "stop"
                usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                current_response_id = None
                
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
                                    
                                    # 提取response_id
                                    if "response.created" in data:
                                        current_response_id = data["response.created"].get("response_id")
                                    
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
                    
                    # 聊天结束后更新会话记录
                    if response_text and current_response_id:
                        # 构建完整的消息历史
                        updated_messages = messages.copy()
                        updated_messages.append({
                            "role": "assistant",
                            "content": response_text
                        })
                        
                        self.update_session_after_chat(
                            chat_id=chat_id,
                            title=f"OpenAI_API_对话_{int(time.time())}",
                            messages=updated_messages,
                            current_response_id=current_response_id,
                            assistant_content=response_text
                        )
                    
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
                    pass  # 不再自动删除会话

        except requests.exceptions.RequestException as e:
            debug_print(f"聊天补全失败: {e}")
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
        debug_print(f"处理聊天补全请求时发生未预期错误: {e}")
        return jsonify({
            "error": {
                "message": f"内部服务器错误: {str(e)}",
                "type": "server_error",
                "param": None,
                "code": None
            }
        }), 500

@app.route('/v1/chats/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """删除指定的对话"""
    try:
        success = qwen_client.delete_chat(chat_id)
        if success:
            return jsonify({"message": f"会话 {chat_id} 已删除", "success": True})
        else:
            return jsonify({"message": f"删除会话 {chat_id} 失败", "success": False}), 400
    except Exception as e:
        debug_print(f"删除会话时发生错误: {e}")
        return jsonify({
            "error": {
                "message": f"删除会话失败: {str(e)}",
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
    print(f"正在启动服务器于端口 {PORT}...")
    print(f"Debug模式: {'开启' if DEBUG_STATUS else '关闭'}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
