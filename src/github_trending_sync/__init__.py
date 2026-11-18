"""GitHub Trending 每日同步与飞书日报。

从 GitHub Trending 页面采集当日 Top N 项目，标准化后写入飞书多维表格，
并向飞书测试群发送当日摘要。同名快照幂等，保护人工复核字段。
"""

__version__ = "1.0.0"
