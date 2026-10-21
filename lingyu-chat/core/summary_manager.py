from typing import Dict, List

from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .prompt import SUMMARY_GENERATION_PROMPT

# 全局存储：会话摘要 (key是chat_session_id，value是摘要)
_summary_store: Dict[str, str] = {}
# 全局存储：未摘要消息数量(key是chat_session_id，value未摘要消息数量)
_unsummarized_count: Dict[str, int] = {}

# 默认配置
SUMMARY_BATCH_SIZE = 12
RECENT_WINDOW = 6

str_output_parser = StrOutputParser()


class SummaryManager:
    """负责会话摘要的生成与存储"""

    def __init__(self, chat_session_id: str) -> None:
        self.chat_session_id = chat_session_id
        # 初始化摘要
        if chat_session_id not in _summary_store:
            _summary_store[chat_session_id] = ""
        if chat_session_id not in _unsummarized_count:
            _unsummarized_count[chat_session_id] = 0

    def get_summary(self) -> str:
        """获取当前会话的摘要"""
        return _summary_store.get(self.chat_session_id, "")

    def update_summary(self, new_summary: str) -> None:
        """更新当前会话的摘要"""
        _summary_store[self.chat_session_id] = new_summary

    def get_unsummarized_count(self) -> int:
        """获取未摘要的消息数量"""
        return _unsummarized_count.get(self.chat_session_id, 0)

    def increment_unsummarized_count(self, delta: int = 1) -> None:
        """增加未摘要消息计数"""
        current = _unsummarized_count.get(self.chat_session_id, 0)
        _unsummarized_count[self.chat_session_id] = current + delta

    def reset_unsummarized_count(self) -> None:
        """重置未摘要消息计数"""
        _unsummarized_count[self.chat_session_id] = 0

    def should_trigger_summary(self) -> bool:
        """检查是否达到摘要生成阈值"""
        return self.get_unsummarized_count() >= SUMMARY_BATCH_SIZE

    def generate_incremental_summary(
            self,
            old_summary: str,
            new_messages: List[BaseMessage],
            llm: ChatTongyi = None
    ) -> str:
        """生成增量摘要"""
        if not new_messages:
            return old_summary

        # 提取新消息文本
        messages_text = ""
        for msg in new_messages:
            if isinstance(msg, HumanMessage):
                messages_text += f"human：{msg.content}\n"
            elif isinstance(msg, AIMessage):
                messages_text += f"ai：{msg.content}\n"

        # 没有LLM时使用简单方式
        if not llm:
            return self._simple_summary(old_summary, messages_text)

        # 使用LLM生成摘要
        try:
            summary_prompt = ChatPromptTemplate.from_messages([
                ("system", SUMMARY_GENERATION_PROMPT),
                ("human", f"旧摘要：{old_summary}\n新消息：{messages_text}")
            ])
            chain = summary_prompt | llm | str_output_parser
            result = chain.invoke(input={})
            new_summary = result.strip()
            return new_summary
        except:
            return self._simple_summary(old_summary, messages_text)

    def _simple_summary(self, old_summary: str, new_text: str) -> str:
        """简单的摘要拼接方式（降级方案）"""
        if old_summary and old_summary != "[摘要] 无":
            old_part = old_summary[:150] if len(old_summary) >= 150 else old_summary
            new_part = new_text[:150] if len(new_text) >= 150 else new_text
            return f"[摘要] {old_part}...{new_part}"
        else:
            return f"[摘要] {new_text[:150]}"
