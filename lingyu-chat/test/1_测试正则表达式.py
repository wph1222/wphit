import re
import json

def extract_json(s):
    # 从字符串 s 中提取第一个由花括号包裹的内容。
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            print(f"```{s}```不是一个合法的json格式")
    return None

# 示例1：正常提取
s1 = '好的，我将直接给你输出json，不输出别的内容:\n {"name": "张三", "age": 30} 更多文本'
print(extract_json(s1))  # {'name': '张三', 'age': 30}

# 示例2：多行 JSON
s2 = '数据如下：\n{\n  "status": "ok",\n  "code": 200\n}\n结束'
print(extract_json(s2))  # {'status': 'ok', 'code': 200}

# 示例3：无效 JSON（括号内的内容不是合法 JSON）
s3 = f'代码块 {{ var x = 1; }}   注释'
print(extract_json(s3))  # None