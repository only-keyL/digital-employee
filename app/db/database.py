"""数据库基础配置。

这个文件只负责三件事：
1. 创建 SQLAlchemy 的 Base，供 ORM 模型类继承；
2. 根据配置创建数据库连接引擎 engine；
3. 提供 get_db，给 FastAPI 接口按请求创建/关闭数据库 Session。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的父类。

    app/models 里的表模型都会继承 Base。
    SQLAlchemy 通过 Base 收集模型和表结构信息，后续才能建表、查询、插入数据。
    """

    pass


# engine 可以理解为“数据库连接管理器”。
# 它不等于某一条具体连接，而是负责按需创建、复用和检查数据库连接。
engine = create_engine(
    settings.database_url,  # 数据库连接串，例如 mysql+pymysql://user:password@host:port/db
    pool_pre_ping=True,  # 每次取连接前先探测连接是否可用，避免拿到断开的 MySQL 连接
    pool_recycle=3600,  # 连接使用超过 3600 秒后回收重建，减少 MySQL 空闲断连问题
    echo=settings.app_debug,  # debug 模式下打印 SQL，方便本地排查
)

# SessionLocal 是“数据库会话工厂”，调用 SessionLocal() 才会得到一次具体会话。
# autocommit=False 表示不会自动提交事务，需要业务代码显式 commit。
# autoflush=False 表示不在每次查询前自动 flush，避免小白调试时出现隐式写入困惑。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：为一次请求提供一个数据库 Session。

    用法通常是：
        def api(db: Session = Depends(get_db)):
            ...

    执行流程：
    1. 请求进来时，创建一个 db Session；
    2. yield db 把 Session 交给路由函数 / Service 使用；
    3. 请求处理结束后，不管成功还是异常，finally 都会关闭 Session。

    它主要解决的问题是：
    - 每个请求都能拿到独立的数据库会话；
    - 请求结束后连接能被正确释放；
    - 业务代码不用到处手写创建和关闭 Session 的重复代码。
    """
    db = SessionLocal()
    try:
        # yield 前：相当于把 db 交给 FastAPI 后续的接口函数使用。
        # yield 后：等接口执行完，代码会继续走到 finally。
        yield db
    finally:
        # 关闭 Session，不是关闭整个数据库服务。
        # 它会释放当前请求占用的连接资源，避免连接泄漏。
        db.close()
