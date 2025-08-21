from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config.config import settings, sync_initial_settings
from app.database.connection import connect_to_db, disconnect_from_db
from app.database.initialization import initialize_database
from app.exception.exceptions import setup_exception_handlers
from app.log.logger import get_application_logger, setup_access_logging
from app.middleware.middleware import setup_middlewares
from app.router.routes import setup_routers
from app.scheduler.scheduled_tasks import start_scheduler, stop_scheduler
from app.service.key.key_manager import get_key_manager_instance
from app.service.update.update_service import check_for_updates
from app.utils.helpers import get_current_version
from app.service.client.api_client import initialize_api_client, close_api_client

import asyncio

logger = get_application_logger()

_preload_lock = asyncio.Lock()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "app" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"

# 初始化模板引擎，并添加全局变量
templates = Jinja2Templates(directory="app/templates")


# 定义一个函数来更新模板全局变量
def update_template_globals(app: FastAPI, update_info: dict):
    # Jinja2Templates 实例没有直接更新全局变量的方法
    # 我们需要在请求上下文中传递这些变量，或者修改 Jinja 环境
    # 更简单的方法是将其存储在 app.state 中，并在渲染时传递
    app.state.update_info = update_info
    logger.info(f"Update info stored in app.state: {update_info}")


# --- Helper functions for lifespan ---
async def _setup_database_and_config(app_settings, app: FastAPI):
    """Initializes database, syncs settings, initializes KeyManager, and sets up ChatService."""
    initialize_database()
    logger.info("Database initialized successfully")
    await connect_to_db()
    await sync_initial_settings()

    # 初始化KeyManager
    key_manager = await get_key_manager_instance(app_settings.API_KEYS, app_settings.VERTEX_API_KEYS)
    app.state.key_manager = key_manager  # 将key_manager存储在app.state中

    # 为ValidKeyPool设置聊天服务
    if key_manager and key_manager.valid_key_pool:
        from app.service.chat.gemini_chat_service import GeminiChatService
        chat_service = GeminiChatService(app_settings.BASE_URL, key_manager)
        key_manager.set_chat_service(chat_service)
        logger.info("Chat service set for ValidKeyPool")

    logger.info("Database, config sync, and KeyManager initialized successfully")

async def _background_preload_keys(app: FastAPI):
    """Asynchronously preloads the key pool, ensuring it only runs once."""
    async with _preload_lock:
        key_manager = getattr(app.state, 'key_manager', None)
        if key_manager and getattr(key_manager, '_preload_started', False):
            logger.info("Key preload has already been started. Skipping.")
            return

        if key_manager:
            key_manager._preload_started = True
            if key_manager.valid_key_pool:
                try:
                    logger.info("Starting background key pool preload...")
                    loaded_count = await key_manager.preload_valid_key_pool()
                    logger.info(f"ValidKeyPool background preloaded with {loaded_count} keys")
                except Exception as e:
                    logger.error(f"Failed to background preload ValidKeyPool: {e}", exc_info=True)
            else:
                logger.info("ValidKeyPool not available, skipping background preload.")
        else:
            logger.info("KeyManager not available, skipping background preload.")


async def _shutdown_database():
    """Disconnects from the database."""
    await disconnect_from_db()


def _start_scheduler():
    """Starts the background scheduler."""
    try:
        start_scheduler()
        logger.info("Scheduler started successfully.")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


def _stop_scheduler():
    """Stops the background scheduler."""
    stop_scheduler()


async def _perform_update_check(app: FastAPI):
    """Checks for updates and stores the info in app.state."""
    update_available, latest_version, error_message = await check_for_updates()
    current_version = get_current_version()
    update_info = {
        "update_available": update_available,
        "latest_version": latest_version,
        "error_message": error_message,
        "current_version": current_version,
    }
    if not hasattr(app, "state"):
        from starlette.datastructures import State

        app.state = State()
    app.state.update_info = update_info
    logger.debug(f"Update check completed. Info: {update_info}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application startup and shutdown events.

    Args:
        app: FastAPI应用实例
    """
    logger.info("Application starting up...")
    try:
        initialize_api_client()
        await _setup_database_and_config(settings, app)
        await _perform_update_check(app)
        _start_scheduler()
        
        # Create a background task to preload keys without blocking startup
        import asyncio
        asyncio.create_task(_background_preload_keys(app))
        logger.info("Background key preloading task scheduled.")

    except Exception as e:
        logger.critical(
            f"Critical error during application startup: {str(e)}", exc_info=True
        )

    yield

    logger.info("Application shutting down...")
    _stop_scheduler()
    await _shutdown_database()
    await close_api_client()


def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用程序实例

    Returns:
        FastAPI: 配置好的FastAPI应用程序实例
    """

    # 创建FastAPI应用
    current_version = get_current_version()
    app = FastAPI(
        title="Gemini Balance API",
        description="Gemini API代理服务，支持负载均衡和密钥管理",
        version=current_version,
        lifespan=lifespan,
    )

    if not hasattr(app, "state"):
        from starlette.datastructures import State

        app.state = State()
    app.state.update_info = {
        "update_available": False,
        "latest_version": None,
        "error_message": "Initializing...",
        "current_version": current_version,
    }

    # 配置静态文件
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # 配置中间件
    setup_middlewares(app)

    # 配置异常处理器
    setup_exception_handlers(app)

    # 配置路由
    setup_routers(app)

    # 配置访问日志API密钥隐藏
    setup_access_logging()

    return app
