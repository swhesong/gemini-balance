# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
- **Local Development**: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- **Docker Compose**: `docker-compose up -d` (recommended for production)
- **Docker**: `docker run -d -p 8000:8000 --name gemini-balance -v ./data:/app/data --env-file .env softs2005/gemini-balance:latest`

### Testing
- **Run all tests**: `python tests/test_runner.py`
- **Specific test**: `python -m unittest tests.test_ttl_cache.TestTTLCache.test_ttl_expiration`

### Database
- **Fix settings table**: `python fix_settings_table.py` (use if database schema needs updates)

### Docker Build
- **Build Docker image**: `./build-docker.sh` (Linux/macOS) or `build-docker.bat` (Windows)
- **Multi-architecture builds available**: AMD and ARM support via `softs2005/gemini-balance:latest`

## Architecture Overview

This is a FastAPI-based Gemini API proxy and load balancer that manages multiple API keys with intelligent routing and monitoring. It supports multiple API formats (Gemini, OpenAI, Vertex AI) and provides comprehensive key management, monitoring, and load balancing capabilities.

### Core Components

**Application Structure** (`app/core/application.py`):
- Central FastAPI app creation with lifespan management
- Database initialization and connection handling
- Settings synchronization between environment and database
- Background scheduler for maintenance tasks

**Configuration System** (`app/config/config.py`):
- Pydantic-based settings with environment variable support
- Dynamic configuration that syncs with database on startup
- Supports both SQLite and MySQL databases
- Complex type parsing for lists, dictionaries, and nested structures

**Key Management** (`app/service/key/key_manager.py`):
- Multi-key load balancing with ValidKeyPool for efficient key rotation
- Failure tracking and automatic key disabling
- Support for both Gemini and Vertex AI API keys
- Background key validation and pool maintenance

### Service Layer Architecture

**Chat Services** (`app/service/chat/`):
- `gemini_chat_service.py`: Handles Gemini API interactions
- `openai_chat_service.py`: Provides OpenAI-compatible API proxy
- `vertex_express_chat_service.py`: Vertex AI platform integration

**Request Handling** (`app/handler/`):
- Stream response optimization and retry logic
- Error processing and message conversion
- Response handling for different API formats

**Utility Systems** (`app/utils/`):
- `ttl_cache.py`: Time-based cache with automatic expiration
- `helpers.py`: Common utility functions
- `uploader.py`: File upload handling

### Database Models

**Key Components** (`app/database/models.py`):
- Settings: Dynamic configuration storage
- API key management and validation tracking
- Request and error logging
- File management and user isolation

### API Endpoints

**Multi-Protocol Support**:
- **Gemini Format**: `/gemini/v1beta/` (native Gemini API)
- **OpenAI Format**: `/hf/v1/` and `/openai/v1/` (OpenAI-compatible)
- **Vertex Express**: Direct Google Vertex AI integration

**Web Interface**:
- `/keys_status` - Real-time key monitoring and management
- `/config` - Dynamic configuration editor
- `/error_logs` - Error log viewer with search/filter

### Advanced Features

**ValidKeyPool System**:
- Intelligent key pool with TTL-based expiration
- Emergency refill mechanism for low key situations
- Different usage limits for Pro vs Non-Pro models
- Background maintenance tasks

**Image Generation**:
- Support for multiple image hosting providers (SM.MS, PicGo, Cloudflare)
- Automatic upload and URL generation
- Configurable models for image generation

**File Management**:
- Complete Files API support for uploads and management
- Automatic cleanup of expired files
- User isolation when enabled

**TTS Support**:
- Native text-to-speech service implementation
- Multiple TTS model support
- Streaming response handling

### Configuration Notes

**Environment Variables**: Copy `.env.example` to `.env` and configure:
- Database settings (MySQL recommended for production)
- API keys for Gemini and Vertex AI
- Authentication tokens for admin access
- Model-specific configurations and safety settings

**Database Configuration**: 
- Uses MySQL by default in production
- SQLite for development
- Automatic schema initialization on startup
- Settings are synchronized from environment to database on startup

**Key Pool Configuration**:
- `VALID_KEY_POOL_ENABLED`: Enable intelligent key management
- `VALID_KEY_POOL_SIZE`: Number of keys to keep in rotation
- `KEY_TTL_HOURS`: Time before keys need revalidation
- `POOL_MAINTENANCE_INTERVAL_MINUTES`: How often to check pool health

### Development Patterns

**Error Handling**: Comprehensive error logging with automatic cleanup
**Configuration Changes**: Most configuration changes take effect immediately without restart
**Testing**: Focus on key management and cache functionality in `tests/` directory
**Logging**: Multi-level logging with automatic retention policies
**Middleware**: Smart routing and request logging middleware for performance monitoring
