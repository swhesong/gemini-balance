import re
from typing import Any, Dict
from app.log.logger import get_gemini_logger
from app.service.key.key_manager import KeyManager
from app.database.services import add_error_log
from app.utils.helpers import redact_key_for_logging

logger = get_gemini_logger()


async def handle_api_error_and_get_next_key(
    key_manager: KeyManager,
    error: Exception,
    old_key: str,
    model_name: str = None,
    retries: int = 1,
    source: str = "unknown",
) -> str:
    """
    统一处理API错误，根据错误类型执行相应操作，并返回一个新的可用密钥。
    如果错误源是'key_validation'，则不返回新密钥。
    """
    error_str = str(error)

    # 分类错误类型
    is_429_error = "429" in error_str
    is_auth_error = "401" in error_str or "403" in error_str  # 认证/授权错误
    is_client_error = "400" in error_str or "404" in error_str or "422" in error_str  # 客户端错误
    is_server_error = "500" in error_str or "502" in error_str or "504" in error_str  # 服务器错误
    is_service_unavailable = "503" in error_str  # 服务不可用（可重试）
    is_timeout_error = "408" in error_str  # 请求超时（可重试）

    # 致命错误：立即标记密钥无效（不记录失败次数）
    is_fatal_error = is_auth_error or is_client_error
    # 可重试错误：记录失败次数，下轮重试（包括服务器错误）
    is_retryable_error = is_server_error or is_service_unavailable or is_timeout_error

    # 提取错误代码
    error_code = None
    match = re.search(r"status code (\d+)", error_str)
    if match:
        error_code = int(match.group(1))
    elif is_429_error:
        error_code = 429
    elif is_auth_error:
        if "401" in error_str:
            error_code = 401
        elif "403" in error_str:
            error_code = 403
    elif is_client_error:
        if "400" in error_str:
            error_code = 400
        elif "404" in error_str:
            error_code = 404
        elif "422" in error_str:
            error_code = 422
    elif is_server_error:
        if "500" in error_str:
            error_code = 500
        elif "502" in error_str:
            error_code = 502
        elif "504" in error_str:
            error_code = 504
    elif is_service_unavailable:
        error_code = 503
    elif is_timeout_error:
        error_code = 408

    # 确定错误类型
    error_type = None
    if is_429_error:
        error_type = "RATE_LIMIT"
    elif is_auth_error:
        error_type = "AUTH_ERROR"
    elif is_client_error:
        error_type = "CLIENT_ERROR"
    elif is_server_error:
        error_type = "SERVER_ERROR"
    elif is_service_unavailable:
        error_type = "SERVICE_UNAVAILABLE"
    elif is_timeout_error:
        error_type = "TIMEOUT_ERROR"
    else:
        error_type = "UNKNOWN_ERROR"

    # 记录错误日志
    try:
        logger.info(f"Attempting to record error log for key {old_key[:8]}... with error type {error_type}")
        result = await add_error_log(
            gemini_key=old_key,
            model_name=model_name,
            error_type=error_type,
            error_log=error_str,
            error_code=error_code,
            request_msg={"retries": retries, "source": "error_processor"}
        )
        if result:
            logger.info(f"Error log recorded successfully for key {old_key[:8]}... with error type {error_type}")
        else:
            logger.warning(f"Error log recording returned False for key {old_key[:8]}... with error type {error_type}")
    except Exception as log_error:
        logger.error(f"Failed to record error log for key {old_key[:8]}...: {str(log_error)}", exc_info=True)

    logger.info(f"Processing error for key {old_key[:8]}...: error_type={error_type}, should_switch={'yes' if (is_429_error or is_fatal_error or is_retryable_error) else 'no'}")

    # --- Step 1: Handle the key that caused the error ---
    if is_429_error:
        if model_name:
            logger.info(f"Detected 429 error for model '{model_name}' with key '{old_key}'. Marking key for model-specific cooldown.")
            await key_manager.mark_key_model_as_cooling(old_key, model_name)
            if source != "key_validation":
                logger.info("Temporarily removing from active pool as it was an in-use key.")
                await key_manager.remove_key_from_pool(old_key)
        else:
            logger.info(f"Detected 429 error with key '{old_key}'. Marking key as failed due to rate limit.")
            await key_manager.mark_key_as_failed(old_key)

    elif is_fatal_error:
        error_category = "auth" if is_auth_error else "client"
        logger.warning(f"Detected fatal {error_category} error for key '{old_key}'. Marking key as failed immediately.")
        await key_manager.mark_key_as_failed(old_key)

    elif is_retryable_error:
        logger.warning(f"Detected retryable server error for key '{old_key}'.")
        if source != "key_validation":
            logger.info("Temporarily removing from active pool as it was an in-use key.")
            await key_manager.remove_key_from_pool(old_key)

    else:
        # For other non-specific errors, use the original failure counting logic
        await key_manager.handle_api_failure(old_key, retries, model_name=model_name)

    # --- Step 2: Decide whether to provide a new key ---
    if source == "key_validation":
        logger.debug("Error handled for key validation source. No new key will be provided.")
        return ""

    # --- Step 3: If not a validation call, get the next available key ---
    logger.info(f"Getting next working key after '{error_type}' error...")
    new_key = await key_manager.get_next_working_key(model_name=model_name)
    logger.info(f"Switched to new key: {redact_key_for_logging(new_key)}")

    return new_key


async def log_api_error(
    api_key: str, 
    error: Exception, 
    model_name: str = None, 
    error_type: str = "unknown",
    request_msg: Dict[str, Any] = None
) -> bool:
    """
    统一记录API错误日志，不涉及密钥切换逻辑
    
    Args:
        api_key: 使用的API密钥
        error: 异常对象
        model_name: 模型名称
        error_type: 错误类型
        request_msg: 请求消息
        
    Returns:
        bool: 是否记录成功
    """
    error_str = str(error)
    
    # 提取错误代码
    error_code = None
    match = re.search(r"status code (\d+)", error_str)
    if match:
        error_code = int(match.group(1))
    
    # 根据错误类型分类
    if error_type == "unknown":
        is_429_error = "429" in error_str
        is_auth_error = "401" in error_str or "403" in error_str
        is_client_error = "400" in error_str or "404" in error_str or "422" in error_str
        is_server_error = "500" in error_str or "502" in error_str or "504" in error_str
        is_service_unavailable = "503" in error_str
        is_timeout_error = "408" in error_str
        
        if is_429_error:
            error_type = "RATE_LIMIT"
        elif is_auth_error:
            error_type = "AUTH_ERROR"
        elif is_client_error:
            error_type = "CLIENT_ERROR"
        elif is_server_error:
            error_type = "SERVER_ERROR"
        elif is_service_unavailable:
            error_type = "SERVICE_UNAVAILABLE"
        elif is_timeout_error:
            error_type = "TIMEOUT_ERROR"
        else:
            error_type = "UNKNOWN_ERROR"
    
    # 记录错误日志
    try:
        logger.info(f"Recording error log for key {api_key[:8]}... with error type {error_type}")
        result = await add_error_log(
            gemini_key=api_key,
            model_name=model_name,
            error_type=error_type,
            error_log=error_str,
            error_code=error_code,
            request_msg=request_msg or {"source": "service_layer"}
        )
        if result:
            logger.info(f"Error log recorded successfully for key {api_key[:8]}... with error type {error_type}")
        else:
            logger.warning(f"Error log recording returned False for key {api_key[:8]}... with error type {error_type}")
        return result
    except Exception as log_error:
        logger.error(f"Failed to record error log for key {api_key[:8]}...: {str(log_error)}", exc_info=True)
        return False