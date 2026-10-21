import sys
import os

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chat_service import ChatService
from core.protocol import ChatRequest, ChatResponse
import uuid


# 创建测试请求
request = ChatRequest(
    user_id="test_user",
    chat_session_id="test_session",
    trace_id=str(uuid.uuid4()),
    user_input="我的快递到哪了？我的订单号是7856757536124",
    api_key=os.getenv("DASHSCOPE_API_KEY")
)

print(f"测试请求: {request}")

try:
    # 初始化ChatService
    chat_service = ChatService()
    # 处理请求
    response = chat_service.handle(request)
    print(f"响应: {response}")
except Exception as e:
    print(f"测试失败: {e}")
