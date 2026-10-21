from dataclasses import dataclass
from typing import Any

from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from .prompt import INTENT_RECOGNIZE_PROMPT
from langchain_core.output_parsers import StrOutputParser
import json
import re


@dataclass(frozen=True)
class IntentResult:
    """
    意图识别结果：
    - intents: 意图列表, 每个元素为一个意图名称
    - slots: slot值字典, 键为slot名称, 值为slot值
    - confidence: 置信度分数, 取值范围 0~1, 越大表示越信该意图
    """
    intents: list[str]
    slots: dict[str, Any]
    confidence: float


class IntentRecognizer:
    """
    意图识别器：通过大语言模型识别用户输入的意图，输出IntentResult对象
    """

    def __init__(self, llm: ChatTongyi) -> None:
        """
        初始化意图识别
        :param llm: 大语言模型
        """
        self.__prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_RECOGNIZE_PROMPT),
            ("ai", "上下文内容：{chat_history}"),
            ("human", "用户输入：{user_input}")
        ])
        self.__llm = llm
        self.__chain = self.__prompt | self.__llm | StrOutputParser()

    def recognize(self, user_input: str, chat_history: str | None = None) -> IntentResult:
        """
        识别用户输入的意图
        :param chat_history:上下文内容
        :param user_input:用户输入的文本
        :return:意图识别结果
        """
        # 1.调用llm去识别用户的意图，输出str格式的json字符串
        chat_history = chat_history if chat_history else ""
        result = self.__chain.invoke(input={"chat_history": chat_history, "user_input": user_input})

        # 2.解析大模型输出
        data = self.__parse_str_to_json(result)
        # 2.1. 解析intents意图
        intents = data.get("intents")
        if not isinstance(intents, list):
            intent = data.get("intent")
            intents = [intent] if isinstance(intent, str) else []
        # 2.2. 解析slots插槽
        slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
        # 2.3. 解析confidence置信度
        try:
            confidence = float(data.get("confidence"))
        except ValueError:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        # 3.返回结果
        return IntentResult(intents, slots, confidence)

    def __parse_str_to_json(self, text: str) -> dict[str, Any]:
        """
        将text解析为dict字典类型
        :param text: 待解析的字符串
        :return: 解析后的dict字典
        """
        if not text and not text.strip():
            # 如果模型输出为空，那么返回默认值
            return {"intents": ["general"], "slots": {}, "confidence": 0.0}

        # 尝试将text转换成dict
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 如果解析失败，尝试从模型输出中提取json字符串
        find_text = re.search(r"{{.*?}}", text, re.DOTALL)
        if find_text:
            try:
                return json.loads(find_text.group(0))
            except json.JSONDecodeError:
                pass

        # 如果未找到json字符串，那么返回默认值
        return {"intents": ["general"], "slots": {}, "confidence": 0.0}