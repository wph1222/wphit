from langchain_community.chat_models import ChatTongyi

from core.memory import Memory

# 创建记忆实例
memory = Memory(chat_session_id="session_001")
model = ChatTongyi(model="qwen3-max")
# 添加消息（自动触发摘要）
memory.add_user_message("你好，我叫阿苑", llm=model)
memory.add_ai_message("你好阿苑！很高兴认识你。", llm=model)

# 更新关键事实
memory.update_key_facts({"user_name": "阿苑", "preference": "科幻电影"})

# 准备LLM上下文
context = memory.prepare_memory_for_llm()
for msg in context:
    print(msg.content)

# 获取事实
facts = memory.get_key_facts()
print(facts)  # {'user_name': '阿苑', 'preference': '科幻电影'}