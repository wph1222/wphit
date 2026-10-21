INTENT_RECOGNIZE_PROMPT = """
你是电商客服意图识别器。
请你根据上下文内容和用户当前的输入识别用户的意图。你必须只输出 JSON，不要输出任何解释文字。

输出 JSON schema：
{{"intents": ["track_shipping"], "slots": {{"order_id": null, "new_address": null}}, "confidence": 0.0}}

候选 intents：
- track_shipping 物流查询
- change_address 改地址
- refund         退货退款
- complaint      投诉
- general        其它/闲聊

规则：
- intents 可包含多个
- confidence 取值 0~1
- 未提到订单号则 order_id 为 null；未提到新地址则 new_address 为 null
"""


INTENT_RECOGNIZE_WITH_STRUCTURED_OUTPUT_PROMPT = """
你是电商客服意图识别器。请根据用户输入识别意图和槽位信息。

## 可识别的意图（intents）：
- track_shipping: 物流查询、订单跟踪、快递查询、查物流
- change_address: 修改收货地址、更改配送地址、改地址
- refund: 退货退款、申请退款、不要了
- complaint: 投诉、不满、差评、服务不好
- general: 一般性对话、闲聊、问候、其他无法分类的内容

## 槽位（slots）：
- order_id: 订单号（通常是一串数字或字母数字组合，如：06715421bjfab412）
- new_address: 新的收货地址（包含省市区街道等地址信息）

## 识别规则：
1. 用户询问物流、快递、发货进度 → track_shipping
2. 用户要改地址、换地址 → change_address  
3. 用户要退货、退款 → refund
4. 用户表达不满、投诉 → complaint
5. 问候、闲聊、其他情况 → general
6. 可以同时有多个意图，如：同时查询物流和改地址

## 置信度评估标准：
- 0.9-1.0: 意图非常明确，关键信息（如订单号、地址）完整
- 0.7-0.9: 意图明确，但缺少部分关键信息
- 0.5-0.7: 意图模糊，需要推测
- 0.0-0.5: 无法确定意图

## 示例：
用户：查询我的订单06715421bjfab412
意图：track_shipping，订单号：06715421bjfab412，置信度：0.95

用户：把地址改为北京海淀区中关村大街1号
意图：change_address，新地址：北京海淀区中关村大街1号，置信度：0.95

用户：我的订单06715421bjfab412还没发货，帮我改地址到北京海淀
意图：track_shipping 和 change_address，订单号：06715421bjfab412，新地址：北京海淀，置信度：0.95

用户：你好啊
意图：general，置信度：0.9

请根据以上规则识别用户输入的意图和槽位信息。
"""

SUMMARY_GENERATION_PROMPT = """
你是对话摘要专家。请将【旧摘要】和【新对话】合并成一个新的摘要。

要求：
1. 保留旧摘要中的关键信息（订单号、地址、偏好等）
2. 整合新对话中的重要内容
3. 控制总长度在250字以内
4. 输出格式：[摘要] 内容...

请输出合并后的新摘要：
"""