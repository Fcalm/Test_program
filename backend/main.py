from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import create_tables
from backend.routers.auth import router as auth_router
from backend.routers.resume import router as resume_router
from backend.routers.files import router as files_router
from backend.routers.tools import router as tools_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表
    await create_tables()
    yield


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
app.include_router(tools_router)  # 临时：agent 开发后删除


@app.get("/")
async def root():
    return {"message": "AI简历助手 API", "docs": "/docs"}
