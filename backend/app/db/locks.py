"""
================================================================================
文件作用：给「同一个人」的写操作排队，防止重复提交把数据写坏
================================================================================

这是全项目最重要的一个防护，它挡的是一个真实发生过的线上事故。

事故是怎么发生的
----------------
  1. 医生点「提交」
  2. 手机网络卡住，请求迟迟没有回来
  3. 前端等了 25 秒超时，显示「提交失败」
  4. 医生又点了一次
  5. 但第一个请求在服务器上**还在跑**
     —— 前端取消 fetch 只是自己不等了，并不能让后端停下来
  6. 于是两个一模一样的请求同时在写数据库

三个参与者写接口全都是「先查有没有 → 没有就新建」的写法，
两个请求同时跑就变成：

        请求 A 查：没有          请求 B 查：没有
        请求 A 建一条            请求 B 又建一条    ← 重复了

加锁之前实际造成的后果
----------------------
  /api/action       两个请求给同一道题各插了一条作答记录。
                    actions 表对 case_presentation_id 有唯一约束，
                    后写的那个直接违约崩掉，返回 HTTP 500。
                    ★ 医生看到的就是「网络异常，请稍后重试」——
                      而他的答案其实早就存好了。
  /api/case/open    两个请求各建了一条记录。生产库因此积累了 23 组重复行。
  /api/post-survey  写了两份后测问卷，导出时这个人被算成两个。

怎么用
------
    async with session_write_lock(db, session.id):
        ...查、写、commit 全都要放在里面...

★ 必须把 commit 也包进来。如果提前放锁，第二个请求就会在第一个还没提交时
  进来，照样查不到数据、照样重复写——等于白加。

★ 锁是按「会话」加的，只挡同一个人自己的请求。不同医生之间完全不互相等待，
  所以 100 人同时在线也没有任何性能损失。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  _local_locks           SQLite（测试/本地）用的进程内锁字典
  第 2 块  session_write_lock()   ★ 锁本身，两种数据库两套实现
================================================================================
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ── 第 1 块：SQLite 路径用的进程内锁 ────────────────────────────────────────
# Only used on the SQLite path (single process, bounded by the number of
# sessions a test run creates), so unbounded growth is not a concern.
#
# 大白话：这是个字典，键是会话编号，值是一把锁。
#
# defaultdict(asyncio.Lock) 的意思是"取一个不存在的键时，自动造一把新锁"，
# 省得每次都要写"如果没有就新建"。
#
# ★ 这个字典只增不减，理论上是内存泄漏。但它只在 SQLite（本地开发和测试）
#   路径上用，一次测试跑下来最多几十个会话，占几 KB，无所谓。
#   生产环境走的是下面 Postgres 那条路，根本不碰这个字典。
_local_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


# ── 第 2 块：锁本身 ★ ───────────────────────────────────────────────────────
# @asynccontextmanager 把一个函数变成能用 `async with` 的东西。
# 写法上的约定：函数体里 yield 之前的代码 = 进入时执行（加锁），
# yield 之后的代码 = 离开时执行（解锁）。
@asynccontextmanager
async def session_write_lock(db: AsyncSession, session_id: str) -> AsyncIterator[None]:
    """Hold a per-session write lock for the duration of the block.

    Must wrap the *whole* handler body, commit included: releasing before the
    commit would reopen the very window this closes.
    """
    # 判断当前连的是哪种数据库。
    # db.bind 是这个会话绑定的数据库引擎，dialect.name 是数据库类型名
    #（"postgresql" 或 "sqlite"）。先判断 is not None 是防御性的：
    # 极少数情况下会话可能还没绑定引擎，那时直接走下面的本地锁分支。
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # ---- 生产环境：Postgres 的「事务级咨询锁」 ----
        #
        # hashtext() maps the session id to the int the advisory-lock API
        # takes. A collision would merely make two unrelated participants
        # take turns for a few milliseconds, never a correctness problem.
        #
        # 大白话，这一行做了什么：
        #
        # 「咨询锁」(advisory lock) 是 Postgres 提供的一种通用锁，
        # 它不锁任何具体的表或行，就是让你自己拿一个数字当"钥匙牌"，
        # 谁先拿到谁先走，后来的排队等。
        #
        # ★ 为什么必须用数据库的锁，而不能用 Python 自己的锁：
        #   生产环境跑着 4 个 gunicorn 进程。同一个医生的两个请求
        #   很可能被分给不同的进程，进程内的锁根本挡不住对方。
        #   而咨询锁由数据库统一管理，4 个进程都得听它的。
        #
        # ★ 「事务级」(xact) 三个字很关键：锁在事务结束时自动释放
        #   （commit 或 rollback 都算）。这意味着即使代码里漏写了解锁、
        #   甚至请求处理到一半崩了，锁也不会永久卡死。
        #
        # ★ hashtext 把会话编号这个字符串转成锁 API 要的整数。
        #   理论上两个不同的会话可能算出同一个数（哈希碰撞），
        #   后果也只是两个陌生人排队几毫秒，不影响任何数据的正确性。
        #
        # ★ 参数用 :key 占位符而不是拼字符串，是防 SQL 注入的标准写法。
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key)::bigint)"),
            {"key": session_id},
        )
        # 交给调用方去执行它的查询和写入。
        # 注意这里**没有**对应的解锁代码——事务结束时数据库自动放锁。
        yield
        # 提前 return，不要走到下面 SQLite 的分支去。
        return

    # ---- 本地开发 / 测试：SQLite ----
    # SQLite 没有咨询锁这种东西，但它本来就是单进程跑的，
    # 用 Python 自带的 asyncio 锁效果完全等价。
    #
    # `async with 锁:` 的意思是：进来时如果锁被别人占着就等，
    # 拿到锁执行里面的代码，离开时自动释放（哪怕中间抛异常也会释放）。
    async with _local_locks[session_id]:
        yield
