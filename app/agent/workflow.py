"""LangGraph 问答工作流定义（阶段七）。

这个文件专门负责“编排流程”，不负责具体业务细节。

你可以把它理解成一张流程图：
1. 用户问题先进入 validate_input 节点；
2. 校验通过后进入 preprocess_question；
3. 然后进入 retrieve 做知识库检索；
4. 再进入 match_judge 判断是否命中；
5. 命中就走 generate_answer；
6. 未命中就走 handle_miss；
7. 检索异常就走 error_fallback；
8. 最后统一进入 write_log 写日志，再结束。

每个节点的具体实现不在本文件，而是在 app/agent/nodes.py。
本文件只负责把这些节点“串起来”。
"""

# 让类型标注延迟解析。
# 小白理解：这是 Python 的兼容写法，能减少类型标注在运行时引起的导入/解析问题。
from __future__ import annotations

# lru_cache 是 Python 标准库里的缓存装饰器。
# 这里用于缓存已经编译好的 LangGraph，避免每次请求都重新构建流程图。
from functools import lru_cache

# LangGraph 的核心对象：
# - START：流程开始的虚拟节点；
# - END：流程结束的虚拟节点；
# - StateGraph：基于“状态 state”的流程图。
from langgraph.graph import END, START, StateGraph

# AskState 是整个问答流程共享的状态结构。
# 可以把它理解成一个字典，里面保存 question、matched、answer、sources 等字段。
from app.agent.ask_state import AskState

# 这些 ROUTE_* 常量是条件路由的返回值。
# 用常量比直接写字符串更安全，避免手写字符串拼错。
from app.agent.constants import (
    ROUTE_CONTINUE,
    ROUTE_END,
    ROUTE_ERROR,
    ROUTE_MATCHED,
    ROUTE_MISS,
    ROUTE_OK,
)

# 下面这些就是工作流里的 8 个业务节点。
# 本文件只注册它们，不展开节点内部逻辑。
from app.agent.nodes import (
    error_fallback_node,
    generate_answer_node,
    handle_miss_node,
    match_judge_node,
    preprocess_question_node,
    retrieve_node,
    validate_input_node,
    write_log_node,
)


def route_after_validate(state: AskState) -> str:
    """校验后路由：空问题直接 END，否则继续预处理。

    参数解释：
    - state: 当前问答流程的共享状态。

    返回值解释：
    - ROUTE_END: 直接结束流程；
    - ROUTE_CONTINUE: 继续进入 preprocess_question。

    语法解释：
    - `state.get("is_valid", False)` 表示从字典里取 is_valid；
      如果没有这个 key，就默认返回 False。
    - `not ...` 表示取反。

    业务解释：
    如果用户发的是空问题，就没必要继续检索知识库，也不写问答日志。
    """

    if not state.get("is_valid", False):
        return ROUTE_END
    return ROUTE_CONTINUE


def route_after_retrieve(state: AskState) -> str:
    """检索后路由：异常走 error_fallback，否则 match_judge。

    返回值解释：
    - ROUTE_ERROR: 检索异常，进入 error_fallback；
    - ROUTE_OK: 检索服务正常，进入 match_judge。

    业务解释：
    retrieve 节点可能遇到 Qdrant 不可用、向量检索报错等情况。
    一旦出现检索异常，就不再判断命中，而是走统一兜底回答。
    """

    if state.get("retrieval_error", False):
        return ROUTE_ERROR
    return ROUTE_OK


def route_after_match(state: AskState) -> str:
    """命中判断后路由：命中 generate_answer，未命中 handle_miss。

    返回值解释：
    - ROUTE_MATCHED: 知识库命中，进入 generate_answer 生成答案；
    - ROUTE_MISS: 知识库未命中，进入 handle_miss 返回固定话术。

    业务解释：
    matched 不是 LLM 决定的，而是前面的检索与相似度阈值决定的。
    也就是说，只有知识库先命中，后面才会调用 LLM 组织回答。
    """

    if state.get("matched", False):
        return ROUTE_MATCHED
    return ROUTE_MISS


def build_ask_workflow():
    """构建并编译 8 节点问答 StateGraph。

    这个函数做三件事：
    1. 创建 StateGraph；
    2. 注册所有节点；
    3. 配置节点之间的流转关系。

    小白理解：
    - add_node 像是在流程图里画一个方框；
    - add_edge 像是在两个方框之间画一条固定箭头；
    - add_conditional_edges 像是在画“如果 A 就去这里，否则去那里”的分支箭头；
    - compile() 表示把这张图编译成可执行对象。
    """

    # 创建一个基于 AskState 的流程图。
    # AskState 规定了每个节点之间共享哪些字段。
    graph = StateGraph(AskState)

    # 注册节点：给每个节点起一个名字，并绑定具体处理函数。
    #
    # 第一个参数是节点名，例如 "validate_input"。
    # 第二个参数是具体函数，例如 validate_input_node。
    #
    # 后面 add_edge / add_conditional_edges 都会用节点名来连线。
    graph.add_node("validate_input", validate_input_node)  # 校验输入
    graph.add_node("preprocess_question", preprocess_question_node)  # 预处理问题
    graph.add_node("retrieve", retrieve_node)  # 向量检索
    graph.add_node("match_judge", match_judge_node)  # 命中判定
    graph.add_node("generate_answer", generate_answer_node)  # LLM 生成答案
    graph.add_node("handle_miss", handle_miss_node)  # 未命中固定话术
    graph.add_node("error_fallback", error_fallback_node)  # 检索异常兜底
    graph.add_node("write_log", write_log_node)  # 写 question_log / 未命中表

    # 固定边：流程从 START 这个虚拟起点进入 validate_input。
    # START 不是业务函数，只是 LangGraph 表示“开始”的特殊节点。
    graph.add_edge(START, "validate_input")

    # 条件边：validate_input 执行完后，要根据 route_after_validate 的返回值决定下一步。
    #
    # 映射关系：
    # - ROUTE_END      -> END，流程直接结束；
    # - ROUTE_CONTINUE -> preprocess_question，继续后续问答流程。
    graph.add_conditional_edges(
        "validate_input",
        route_after_validate,
        {ROUTE_END: END, ROUTE_CONTINUE: "preprocess_question"},
    )

    # 固定边：预处理完成后，一定进入 retrieve 做检索。
    graph.add_edge("preprocess_question", "retrieve")

    # 条件边：retrieve 执行完后，要看检索是否异常。
    #
    # 映射关系：
    # - ROUTE_ERROR -> error_fallback，返回检索异常兜底话术；
    # - ROUTE_OK    -> match_judge，继续判断是否命中知识库。
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {ROUTE_ERROR: "error_fallback", ROUTE_OK: "match_judge"},
    )

    # 条件边：match_judge 执行完后，要看是否命中知识库。
    #
    # 映射关系：
    # - ROUTE_MATCHED -> generate_answer，用知识卡片生成答案；
    # - ROUTE_MISS    -> handle_miss，返回未命中固定话术。
    graph.add_conditional_edges(
        "match_judge",
        route_after_match,
        {ROUTE_MATCHED: "generate_answer", ROUTE_MISS: "handle_miss"},
    )

    # 下面三条边把三种结果统一收口到 write_log。
    #
    # 也就是说，不管是：
    # - 命中并生成了答案；
    # - 未命中并返回固定话术；
    # - 检索异常并返回兜底话术；
    # 最后都要写 question_log，方便后续统计和排查。
    graph.add_edge("generate_answer", "write_log")
    graph.add_edge("handle_miss", "write_log")
    graph.add_edge("error_fallback", "write_log")

    # 写完日志后进入 END，流程结束。
    # END 也是 LangGraph 的特殊虚拟节点，不是业务函数。
    graph.add_edge("write_log", END)

    # compile() 会把上面定义的流程图变成可执行对象。
    # 后续 AskGraphRunner 会调用 graph.invoke(state, config) 来真正跑一次问答流程。
    return graph.compile()


# 缓存已编译的 graph。
#
# 语法解释：
# - @lru_cache(maxsize=1) 是装饰器；
# - 它会让 get_compiled_ask_graph() 第一次执行后把结果缓存起来；
# - 下一次再调用时直接返回缓存结果，不重新执行 build_ask_workflow()。
#
# 业务解释：
# 工作流结构是固定的，不需要每个请求都重新构建。
# 但数据库 Session 不能缓存，所以 Session 不放在 graph 里，而是在运行时通过 config 注入。
@lru_cache(maxsize=1)
def get_compiled_ask_graph():
    """获取进程内缓存的 compiled graph（不含 Session）。

    “不含 Session”很重要：
    - graph 是全局可复用的流程图；
    - Session 是每个请求独立的数据库会话；
    - 如果把 Session 缓存在 graph 里，就会造成请求之间串数据或连接泄漏。
    """

    return build_ask_workflow()
