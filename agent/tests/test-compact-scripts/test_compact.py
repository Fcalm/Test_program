"""压缩质量测试工具

用法：
    python -m agent.scripts.test_compact

    或直接运行：
    python agent/scripts/test_compact.py

修改下方 MESSAGES 列表来测试不同对话场景。
"""

import asyncio
import json
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 agent.xxx 包可导入
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from agent.core.state import AgentState  # noqa: E402
from agent.hooks.compact_hook import CompactHook, count_tokens, get_context_limit  # noqa: E402


# ============================================================
# 在这里放你要测试的对话，格式：[{"role": "...", "content": "..."}]
# ============================================================

MESSAGES = [
    {"role": "user", "content": "我想针对字节跳动的后端开发实习岗位生成一份简历"},
    {"role": "assistant", "content": "好的！请先提供这个岗位的 JD 文本或链接，我来帮你分析核心要求。"},
    {"role": "user", "content": "岗位：后端开发实习\n职责：负责公司内部系统的后端开发，参与系统架构设计\n要求：熟悉 Python/Go，了解 MySQL、Redis，有实习经验优先"},
    {"role": "assistant", "content": "已解析 JD：\n- 岗位：后端开发实习\n- 公司：字节跳动\n- 核心技能：Python、Go、MySQL、Redis\n\n接下来我需要了解你的背景，请问你是哪所学校、什么专业、大几？"},
    {"role": "user", "content": "我是清华大学计算机专业大三，GPA 3.8/4.0，排名前 5%"},
    {"role": "assistant", "content": "很好！清华 CS + 高 GPA 是很强的背景。接下来问几个关于项目经历的问题：\n1. 你有没有后端开发相关的项目经历？\n2. 有没有用过 Python 或 Go 做过实际项目？"},
    {"role": "user", "content": "我有一个用 Python Flask 开发的在线商城项目，支持用户注册、商品浏览、购物车、订单管理。用了 MySQL 做数据库，Redis 做缓存，部署在阿里云上。"},
    {"role": "assistant", "content": "这个项目很匹配！请详细说说：\n1. 你在项目中具体负责哪些模块？\n2. 遇到过什么技术难点？怎么解决的？\n3. 有没有量化成果（如性能提升、用户量等）？"},
    {"role": "user", "content": "我负责了商品搜索和购物车模块。搜索用了 Elasticsearch 做全文检索，性能比直接查 MySQL 快了 10 倍。购物车用 Redis 存储，解决了并发下单时的库存超卖问题。项目上线后有 500+ 用户使用。"},
    {"role": "assistant", "content": "非常不错的经历！我已经收集到足够的信息。现在帮你整理简历内容：\n\n**教育背景**：清华大学 | 计算机科学与技术 | GPA 3.8/4.0 | 前 5%\n\n**项目经历**：在线商城系统\n- 使用 Flask + MySQL + Redis 开发后端，支持用户注册、商品浏览、购物车、订单管理\n- 负责商品搜索模块，集成 Elasticsearch 全文检索，查询性能提升 10 倍\n- 实现购物车模块，利用 Redis 缓存解决并发场景下的库存超卖问题\n- 项目上线后服务 500+ 用户\n\n你还有实习经历或其他项目想补充吗？"},
    {"role": "user", "content": "我还有一段在腾讯的后端实习经历，做了 3 个月"},
    {"role": "assistant", "content": "请介绍一下你在腾讯实习时的主要工作内容和成果。"},
    {"role": "user", "content": "在腾讯 IEG 事业群做游戏后台开发，主要用 C++ 和 Go。参与了游戏匹配系统的优化，将匹配算法从 O(n²) 优化到 O(n log n)，匹配时间从 5 秒降到 0.5 秒。还写了自动化测试脚本，覆盖率从 40% 提升到 80%。"},
    {"role": "assistant", "content": "这段实习经历非常有价值！我已更新简历：\n\n**实习经历**：腾讯 IEG | 游戏后台开发实习生 | 3 个月\n- 使用 C++/Go 参与游戏匹配系统开发\n- 优化匹配算法复杂度从 O(n²) 到 O(n log n)，匹配时间降低 90%（5s → 0.5s）\n- 编写自动化测试脚本，测试覆盖率从 40% 提升至 80%\n\n简历初稿已完成，需要我调整哪个部分？"},
    {"role": "user", "content": "我觉得实习经历那块可以再详细一点，能不能帮我展开写一下具体的技术细节？"},
    {"role": "assistant", "content": "好的，我来帮你把腾讯实习经历的技术细节展开：\n\n**实习经历**：腾讯 IEG | 游戏后台开发实习生 | 2025.06 - 2025.09\n\n**游戏匹配系统优化**\n- 负责游戏匹配系统的核心算法优化，使用 Go 语言重构匹配服务\n- 原系统采用暴力遍历匹配，时间复杂度 O(n²)，在高峰期匹配延迟高达 5 秒\n- 重新设计匹配算法，引入基于 ELO 评分系统的分层匹配策略，结合优先队列和二分查找，将复杂度降至 O(n log n)\n- 引入 Redis 缓存玩家状态信息，减少数据库查询次数 70%\n- 采用 Go 协程并发处理匹配请求，单机 QPS 从 200 提升至 1500\n- 最终匹配延迟从 5 秒降至 0.5 秒，高峰期系统稳定性提升显著\n\n**自动化测试体系建设**\n- 使用 Python + pytest 框架搭建自动化测试平台\n- 设计并实现接口测试用例 200+，覆盖核心业务流程\n- 引入 Jenkins 实现 CI/CD 流水线，每次代码提交自动触发回归测试\n- 测试覆盖率从 40% 提升至 80%，线上 Bug 率下降 60%\n\n**微服务架构实践**\n- 参与将单体服务拆分为微服务架构，使用 gRPC 进行服务间通信\n- 使用 etcd 实现服务注册与发现，保障服务高可用\n- 接入 Prometheus + Grafana 监控体系，实现实时性能监控和告警\n\n这样展开后技术深度更好了，你觉得怎么样？"},
    {"role": "user", "content": "很好！那项目经历部分也帮我展开一下，特别是那个 Elasticsearch 搜索优化的部分。"},
    {"role": "assistant", "content": "没问题，我来详细展开在线商城项目的搜索优化部分：\n\n**项目经历**：在线商城系统 | 个人全栈项目 | 2024.09 - 2025.03\n\n**系统架构设计**\n- 采用前后端分离架构，后端基于 Flask 框架，遵循 RESTful API 设计规范\n- 数据库采用 MySQL 8.0，使用 SQLAlchemy ORM 进行数据操作，实现读写分离\n- 引入 Redis 6.0 作为缓存层，缓存热点商品数据和用户会话信息\n- 使用 Docker + Docker Compose 进行容器化部署，部署在阿里云 ECS 上\n- 配置 Nginx 反向代理和负载均衡，支持高并发访问\n\n**商品搜索模块（核心亮点）**\n- 集成 Elasticsearch 7.x 实现全文检索功能，支持商品名称、描述、分类的多字段搜索\n- 设计自定义分词器，采用 ik_max_word 中文分词插件，提升中文搜索准确率\n- 实现搜索结果排序算法，综合相关性评分、销量、评分等多维度排序\n- 引入搜索建议（Search Suggest）功能，基于用户输入实时返回补全建议\n- 优化前：直接查询 MySQL LIKE 模糊匹配，百万级数据查询耗时 3-5 秒\n- 优化后：Elasticsearch 倒排索引查询，平均响应时间降至 200-300 毫秒，性能提升约 10 倍\n- 实现搜索结果缓存策略，热门搜索词结果缓存至 Redis，进一步降低响应时间至 50ms\n\n**购物车与库存管理**\n- 使用 Redis Hash 结构存储购物车数据，支持多设备同步\n- 实现基于 Redis Lua 脚本的原子性库存扣减操作，解决高并发场景下的库存超卖问题\n- 引入分布式锁（Redisson）防止恶意刷单和重复下单\n- 设计订单超时自动取消机制，使用 Redis 过期键监听释放库存\n\n**性能优化成果**\n- 系统整体响应时间：P99 从 2s 降至 200ms\n- 支持并发用户数从 100 提升至 1000+\n- 项目上线后累计服务 500+ 注册用户，日均 PV 3000+\n\n这样技术细节够丰富了吗？"},
    {"role": "user", "content": "太棒了！现在帮我看看整体简历结构，有没有需要调整的地方？比如排版、重点突出这些。"},
    {"role": "assistant", "content": "我来帮你整体梳理一下简历结构，并给出优化建议：\n\n---\n\n# 个人简历\n\n## 基本信息\n- **姓名**：XXX\n- **学校**：清华大学 | 计算机科学与技术 | 本科大三\n- **GPA**：3.8/4.0 | 专业排名前 5%\n- **联系方式**：xxx@tsinghua.edu.cn | 138-xxxx-xxxx\n- **GitHub**：github.com/xxx\n\n---\n\n## 求职意向\n**字节跳动 - 后端开发实习生**\n\n---\n\n## 教育背景\n\n**清华大学** | 计算机科学与技术 | 本科 | 2022.09 - 2026.06（预计）\n- GPA：3.8/4.0，专业排名前 5%，获国家奖学金\n- 核心课程：数据结构与算法（95）、操作系统（93）、计算机网络（94）、数据库系统（96）、分布式系统（92）\n- 竞赛获奖：ACM-ICPC 区域赛银牌、CCPC 铜牌\n\n---\n\n## 实习经历\n\n### 腾讯 IEG | 游戏后台开发实习生 | 2025.06 - 2025.09\n\n**游戏匹配系统优化**\n- 负责游戏匹配系统的核心算法优化，使用 Go 语言重构匹配服务\n- 重新设计匹配算法，引入 ELO 评分分层匹配策略，结合优先队列和二分查找，复杂度从 O(n²) 降至 O(n log n)\n- 引入 Redis 缓存玩家状态信息，减少数据库查询次数 70%\n- 采用 Go 协程并发处理匹配请求，单机 QPS 从 200 提升至 1500\n- **成果**：匹配延迟从 5 秒降至 0.5 秒，降低 90%\n\n**自动化测试体系建设**\n- 使用 Python + pytest 搭建自动化测试平台，设计接口测试用例 200+\n- 引入 Jenkins 实现 CI/CD 流水线，每次代码提交自动触发回归测试\n- **成果**：测试覆盖率从 40% 提升至 80%，线上 Bug 率下降 60%\n\n**微服务架构实践**\n- 参与将单体服务拆分为微服务架构，使用 gRPC 进行服务间通信\n- 使用 etcd 实现服务注册与发现，接入 Prometheus + Grafana 监控体系\n\n---\n\n## 项目经历\n\n### 在线商城系统 | 个人全栈项目 | 2024.09 - 2025.03\n\n- 采用 Flask + MySQL + Redis + Elasticsearch 技术栈，实现完整的电商后端系统\n- **搜索优化**：集成 Elasticsearch 全文检索，设计自定义分词器，查询性能提升 10 倍（3-5s → 200-300ms）\n- **库存管理**：使用 Redis Lua 脚本实现原子性库存扣减，解决高并发超卖问题\n- **性能成果**：系统 P99 响应时间从 2s 降至 200ms，支持并发用户 1000+\n- 项目上线后累计服务 500+ 用户，日均 PV 3000+\n\n---\n\n## 技术技能\n\n| 类别 | 技能 |\n|------|------|\n| 编程语言 | Python（熟练）、Go（熟练）、C++（熟悉）、Java（了解） |\n| 数据库 | MySQL（熟练）、Redis（熟练）、Elasticsearch（熟悉） |\n| 框架/工具 | Flask、Django、Gin、gRPC、Docker、Nginx、Jenkins |\n| 中间件 | Kafka、RabbitMQ、etcd |\n| 其他 | Linux、Git、CI/CD、微服务架构、分布式系统 |\n\n---\n\n## 自我评价\n- 扎实的计算机基础，对数据结构与算法、操作系统、网络有深入理解\n- 具备良好的工程实践能力，注重代码质量和系统性能优化\n- 热爱技术，活跃于 GitHub 开源社区，持续学习新技术\n\n---\n\n## 排版优化建议\n\n1. **重点突出**：将量化成果（如性能提升 10 倍、延迟降低 90%）用粗体标注，方便 HR 快速抓取亮点\n2. **STAR 法则**：每个经历都按照 Situation-Task-Action-Result 结构描述\n3. **一页原则**：如果内容超过一页，可以适当精简自我评价部分\n4. **关键词匹配**：确保 JD 中提到的 Python、Go、MySQL、Redis 等关键词都在简历中明确体现\n\n你觉得这个结构怎么样？需要我再调整哪个部分？"},
    {"role": "user", "content": "结构很好！不过我想在技能部分再加一些内容，比如我学过分布式系统和微服务相关的知识，还有 Kafka 这些消息队列。"},
    {"role": "assistant", "content": "好的，我来帮你扩充技能部分，突出分布式系统和消息队列的能力：\n\n## 技术技能（优化版）\n\n| 类别 | 技能 |\n|------|------|\n| **编程语言** | Python（熟练，3 年经验）、Go（熟练，1 年经验）、C++（熟悉）、Java（了解） |\n| **数据库** | MySQL（熟练，索引优化、分库分表、读写分离）、Redis（熟练，缓存设计、分布式锁、Lua 脚本）、Elasticsearch（熟悉，全文检索、分词优化） |\n| **后端框架** | Flask、Django、Gin、FastAPI、Spring Boot（了解） |\n| **消息队列** | Kafka（熟悉，生产者/消费者模型、分区策略、消费者组）、RabbitMQ（了解） |\n| **微服务** | gRPC（熟练）、etcd（熟悉，服务注册发现）、Docker（熟练）、Kubernetes（了解） |\n| **运维监控** | Nginx（熟练，反向代理、负载均衡）、Jenkins（熟练，CI/CD 流水线）、Prometheus + Grafana（熟悉） |\n| **分布式系统** | 分布式缓存、分布式锁、一致性哈希、CAP 理论、Raft 共识算法（了解） |\n| **其他** | Linux（熟练）、Git（熟练）、设计模式、单元测试、性能调优 |\n\n**技能亮点说明**：\n- **分布式缓存**：深入理解 Redis 缓存穿透、击穿、雪崩问题及解决方案，实际项目中应用缓存预热、布隆过滤器等技术\n- **消息队列**：理解 Kafka 的 ISR 机制、ACK 策略，能够根据业务场景选择合适的消息可靠性级别\n- **微服务治理**：了解服务熔断、限流、降级等微服务治理策略，有实际项目实践经验\n- **性能优化**：掌握 MySQL 索引优化、慢查询分析、Explain 执行计划分析，具备 SQL 调优实战经验\n\n这样技能部分就更全面了，既覆盖了 JD 要求的核心技能，又展示了你在分布式系统和消息队列方面的深度。需要我再补充其他内容吗？"},
    {"role": "user", "content": "技能部分很好！现在帮我生成一份最终的 Markdown 格式简历，可以直接复制到简历模板里用的。"},
]


# ============================================================

async def main():
    output = []
    output.append("=" * 60)
    output.append("压缩质量测试")
    output.append("=" * 60)

    # 构造 state
    state = AgentState(
        scenario="resume",
        user_id=1,
        session_id="test-compact-session",
        messages=MESSAGES,
    )

    # 显示原始消息统计
    token_count = count_tokens(MESSAGES)
    context_limit = get_context_limit("deepseek-v4-flash")
    output.append(f"\n原始消息数：{len(MESSAGES)}")
    output.append(f"原始 token 数：{token_count}")
    output.append(f"上下文限制：{context_limit}")
    output.append(f"占比：{token_count / context_limit * 100:.1f}%")

    # 构造历史文本（与 _call_llm_compact 逻辑一致）
    history_text = "\n".join(
        f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:200]}"
        for msg in state.messages[-20:]
    )

    # 调用 LLM 压缩
    hook = CompactHook()
    output.append(f"\n{'=' * 60}")
    output.append("LLM 压缩结果：")
    output.append("=" * 60)

    try:
        summary = await hook._call_llm_compact(state)
        output.append(f"\n{summary}")

        # 模拟压缩后的 state
        new_state = hook._create_compacted_state(state, summary)

        output.append(f"\n{'=' * 60}")
        output.append("压缩后状态：")
        output.append("=" * 60)
        output.append(f"保留消息数：{len(new_state.messages)}")
        output.append(f"新 token 数：{count_tokens(new_state.messages)}")
        output.append(f"摘要存在 key_data：{'_compact_summary' in new_state.key_data}")

        output.append(f"\n{'=' * 60}")
        output.append("保留的最近消息：")
        output.append("=" * 60)
        for i, msg in enumerate(new_state.messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            preview = content[:80] + "..." if len(content) > 80 else content
            output.append(f"  [{i}] {role}: {preview}")

    except Exception as e:
        output.append(f"\n压缩失败: {e}")
        output.append("请检查 .env 中的 OPENAI_API_KEY 和 OPENAI_BASE_URL 配置")

    # 写入文件（避免 Windows 终端 GBK 编码问题）
    result_text = "\n".join(output)
    out_file = Path(__file__).parent / "compact_result.txt"
    out_file.write_text(result_text, encoding="utf-8")
    sys.stdout.buffer.write(f"结果已写入: {out_file}\n".encode("utf-8"))
    sys.stdout.buffer.write(result_text.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    asyncio.run(main())
