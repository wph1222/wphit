"""
通义千问的配置文件：1）存储通义千问的api key。2）模型配置
"""
import os

# 1.通义千问的api key，一般从环境变量中获取
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# 2.模型名称：就是你要使用阿里云百炼平台里面的哪个模型
INTENT_RECOGNIZE_MODEL = "qwen-max"
TONGYI_MODEL = "qwen-max"

# 3.temperature：温度参数，用于控制模型的输出随机性。
"""
如果temperature越大，模型的输出越随机；
如果temperature越小，模型的输出越确定。
"""
TONGYI_TEMPERATURE = 0.3

# 4.最大输出长度：用于限制模型的输出长度，防止模型输出过长。
TONGYI_MAX_OUTPUT_LENGTH = 1024