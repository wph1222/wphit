from dataclasses import dataclass


@dataclass(frozen=True)
class ChatRequest:
    """
    聊天请求：
    - user_id: 用户ID
    - session_id: 会话ID (user_id + session_id就可以保证会话的唯一性)
    - trace_id: 跟踪ID (用于日志记录和调试)
    - user_input: 用户输入的文本
    - api_key: API密钥
    """
    api_key: str
    user_id: str
    chat_session_id: str
    user_input: str
    trace_id: str


@dataclass(frozen=True)
class ChatResponse:
    """
    聊天响应：
    - user_id: 用户ID
    - session_id: 会话ID
    - trace_id: 跟踪ID
    - response: 大模型的响应文本
    """
    user_id: str
    chat_session_id: str
    trace_id: str
    response: str
