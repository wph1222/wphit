from langchain_community.chat_models import ChatTongyi
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda
from core.protocol import *

from config import *
from core.intent_recognizer import IntentRecognizer
from core.memory import Memory

import time
import os
import logging

log = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.3
RECENT_MESSAGES = 3 * 2


def _handle_low_confidence(
        intent_result,
        user_input: str
) -> str | None:
    return "抱歉，我没太理解您的需求。请问您是想：\n" \
           "1️⃣ 查询物流进度\n" \
           "2️⃣ 修改收货地址\n" \
           "3️⃣ 申请退货退款\n" \
           "4️⃣ 投诉建议\n" \
           "请回复数字或具体需求。"


def _system_prompt_by_intent(intent: str) -> str:
    mapping = {
        "track_shipping": "你是电商物流查询客服。先要订单号/运单号；如果缺失就追问。",
        "change_address": "你是电商改地址客服。先确认是否已发货；需要订单号+新地址。",
        "refund": "你是电商退货退款客服。先给3步结论，再给注意事项，最后引导用户提供订单号。",
        "complaint": "你是电商投诉处理客服。先安抚，再收集订单号与问题细节，给出处理时效。",
        "general": "你是一个友好、简洁的聊天助手。",
    }
    return mapping.get(intent.strip(), mapping["general"])


class ChatService:
    def __init__(self, api_key: str | None = None) -> None:
        # 初始化日志记录器
        if not logging.root.handlers:
            logging.basicConfig(level=logging.INFO)
        # 初始化llm，需要用户传递api_key，否则从环境变量中获取api_key
        if api_key:
            os.environ["DASHSCOPE_API_KEY"] = api_key
        if not os.environ.get("DASHSCOPE_API_KEY"):
            raise ValueError("DASHSCOPE_API_KEY环境变量未设置")

        self.__intent_recognizer = IntentRecognizer(ChatTongyi(model=INTENT_RECOGNIZE_MODEL))
        self.__llm = ChatTongyi(model=TONGYI_MODEL)
        # 维护 Memory 对象缓存，键是chat_session_id
        self.__memory_cache: dict[str, Memory] = {}

    def __get_memory(self, chat_session_id: str) -> Memory:
        """"""
        if chat_session_id not in self.__memory_cache:
            self.__memory_cache[chat_session_id] = Memory(chat_session_id)
        return self.__memory_cache[chat_session_id]

    def handle(self, request: ChatRequest) -> ChatResponse:
        # 请求开始时间
        start_time = time.time()
        memory = self.__get_memory(request.chat_session_id)

        try:
            # 1.意图识别
            intent_result = self.__intent_recognizer.recognize(request.user_input,
                                                               memory.get_recent_messages_text(RECENT_MESSAGES))
            # 2.低置信度处理（todo）
            if intent_result.confidence <= CONFIDENCE_THRESHOLD:
                low_conf = _handle_low_confidence(intent_result, request.user_input)
                return ChatResponse(
                    user_id=request.user_id,
                    chat_session_id=request.chat_session_id,
                    trace_id=request.trace_id,
                    response=low_conf
                )
            # 3.确定主要意图，路由到对应链路（lingyu项目不做多意图，只做单意图）
            intents = intent_result.intents
            primary_intent = intents[0] if intents else "general"
            # 4.构建 Prompt（不同的意图选择不同的prompt）
            prompt = ChatPromptTemplate.from_messages([
                ("system", _system_prompt_by_intent(primary_intent)),
                MessagesPlaceholder("chat_history"),
                ("human", "用户输入：{user_input}")
            ])
            # 5.记忆管理
            memory_messages = memory.prepare_memory_for_llm()
            # if len(memory.history.get_messages()) >= 10:
            #     print("摘要生成")
            # 6.LLM调用
            chain = prompt | self.__llm | StrOutputParser()
            answer = chain.invoke(input={"chat_history": memory_messages, "user_input": request.user_input})
            # 7.写回历史消息(user消息 & AI消息)
            memory.add_user_message(message=request.user_input, llm=self.__llm)
            memory.add_ai_message(message=answer, llm=self.__llm)
            # 8.更新[事实]
            memory.update_key_facts(intent_result.slots)
            # 9.日志记录
            self.__log(
                req=request,
                intents=intents,
                confidence=intent_result.confidence,
                action="normal",
                latency_ms=int((time.time() - start_time) * 1000)
            )

            return ChatResponse(
                user_id=request.user_id,
                chat_session_id=request.chat_session_id,
                trace_id=request.trace_id,
                response=answer
            )
        except Exception as e:
            # 异常处理，记录错误日志
            self.__log(
                req=request,
                intents=["error"],
                confidence=0.0,
                action="error",
                latency_ms=int((time.time() - start_time) * 1000),
                error=str(e),
            )
            raise e

    def __log(self,
              *,
              req: ChatRequest,
              intents: list[str],
              confidence: float,
              action: str,
              latency_ms: int,
              error: str | None = None):
        payload = {
            "trace_id": req.trace_id,
            "user_id": req.user_id,
            "session_id": req.chat_session_id,
            "intents": intents,
            "confidence": confidence,
            "action": action,
            "latency_ms": latency_ms
        }
        # 如果有错误信息，记录为错误日志error，否则记录为普通日志info
        if error:
            payload["error"] = error
            log.error(payload)
        else:
            log.info(payload)
