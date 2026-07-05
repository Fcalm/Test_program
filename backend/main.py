import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import create_tables
from backend.services.redis_client import close_redis
from backend.services.orphan_cleaner import run_orphan_cleanup
from backend.routers.auth import router as auth_router
from backend.routers.resume import router as resume_router
from backend.routers.files import router as files_router
from backend.routers.analysis import router as analysis_router
from agent.routers.tools import router as tools_router
from agent.routers.agent import router as agent_router
from agent.routers.user_settings import router as user_settings_router

logger = logging.getLogger(__name__)

# 孤儿文件清理间隔（12 小时）
ORPHAN_CLEANUP_INTERVAL = 12 * 3600


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表
    await create_tables()

    # 启动时执行一次孤儿文件清理
    asyncio.create_task(_run_cleanup())

    # 每 12 小时定时执行
    async def _periodic_cleanup():
        while True:
            await asyncio.sleep(ORPHAN_CLEANUP_INTERVAL)
            await _run_cleanup()

    periodic_task = asyncio.create_task(_periodic_cleanup())

    yield

    periodic_task.cancel()
    await close_redis()


async def _run_cleanup():
    """执行孤儿文件清理（异常不影响主进程）"""
    try:
        stats = await run_orphan_cleanup()
        if stats.get("deleted", 0) > 0:
            logger.info("孤儿文件清理: 扫描 %d, 删除 %d", stats["scanned"], stats["deleted"])
    except Exception as e:
        logger.warning("孤儿文件清理失败: %s", e)


app = FastAPI(
    title="AI简历助手",
    description="登录注册接口",
    version="0.1.0",
    lifespan=lifespan,
)

# 允许前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(resume_router)
app.include_router(files_router)
app.include_router(analysis_router)
app.include_router(tools_router)  # 临时：agent 开发后删除
app.include_router(agent_router)
app.include_router(user_settings_router)


@app.get("/")
async def root():
    return {"message": "AI简历助手 API", "docs": "/docs"}
