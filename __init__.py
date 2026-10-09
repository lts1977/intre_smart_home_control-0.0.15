from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
# 临时注释config_entry_control导入，因HA 2026.6.2中不存在该模块
# from homeassistant.helpers.config_entry_control import ConfigEntryControl, ConfigEntryControlType
import logging
import threading
import time
import asyncio
import websockets
import json
import socket
import requests
from typing import Optional, List
from .intreiot.intreIot_cloud import IntreIotHttpClient
from .intreiot.intreIot_client import IntreIoTClient
from .intreiot.const import (DOMAIN, SUPPORTED_PLATFORMS)
from .const import CONF_SELECTED_ENTITIES, CONF_ENABLE_DEBUG_LOG, DEFAULT_ENABLE_DEBUG_LOG
from homeassistant.helpers.event import async_track_state_change_event
from .intreiot.intre_manage_engine import (IntreManagementEngine,get_intress_instance_async)
from .intreiot.engine_manager import EngineManager
from .intreiot.intreIot_ha import (IntreIotHa)
from typing import Any, Callable, Optional, final

# 初始化安装运行日志
from .intreiot.setup_logger import get_setup_logger, write_setup_header, log_setup_event
_LOGGER = logging.getLogger(__name__)
setup_logger = get_setup_logger()
write_setup_header()
log_setup_event("安装", "插件主模块开始加载", "info")

HOME_ASSISTANT_URL = "http://192.168.1.34:8123"
ACCESS_TOKEN="***"


class Intrenitify():
    _main_loop: asyncio.AbstractEventLoop
    _refresh_devices_timer: Optional[asyncio.TimerHandle]
    
    def __init__(self, hass: HomeAssistant) -> None:
        self._main_loop = hass.loop
        self._refresh_devices_timer = None

    @final
    async def async_setup_entry(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> bool:
        """Set up an entry."""
        # 初始化时应用日志开关（从config_entry.data读取）
        log_enabled = config_entry.data.get(CONF_ENABLE_DEBUG_LOG, DEFAULT_ENABLE_DEBUG_LOG)
        from .intreiot.setup_logger import set_logging_enabled
        set_logging_enabled(log_enabled)

        def ha_persistent_notify(
            notify_id: str, title: Optional[str] = None,
            message: Optional[str] = None
        ) -> None:
            """Send messages in Notifications dialog box."""
            if title:
                persistent_notification.async_create(
                    hass=hass, message=message,
                    title=title, notification_id=notify_id)
            else:
                persistent_notification.async_dismiss(
                    hass=hass, notification_id=notify_id)

        _LOGGER.debug("intretech init4455 ="+str(config_entry.data)+str(hass.data[DOMAIN]))
        log_setup_event("安装", f"Intrenitify.async_setup_entry 开始, entry_id={config_entry.entry_id}", "info")
        intre_ss:IntreManagementEngine= await get_intress_instance_async(hass=hass, config_entry=config_entry,persistent_notify=ha_persistent_notify)
        log_setup_event("安装", "Intrenitify.async_setup_entry 引擎实例创建完成", "info")
        return True

    @final
    def __request_refresh_devices_info(self, hass: HomeAssistant, config_entry: ConfigEntry, delay_sec: int) -> None:
        if self._refresh_devices_timer:
            self._refresh_devices_timer.cancel()
            self._refresh_devices_timer = None
        
        self._refresh_devices_timer = self._main_loop.call_later(
            delay_sec, lambda: self._main_loop.create_task(
                self.async_setup_entry(hass, config_entry))) 

    def start_refresh_timer(self, hass: HomeAssistant, config_entry: ConfigEntry, delay_sec: int = 10) -> None:
        """启动设备刷新定时器,默认10秒刷新一次"""
        self.__request_refresh_devices_info(hass, config_entry, delay_sec)

    def stop_refresh_timer(self) -> None:
        """停止设备刷新定时器"""
        if self._refresh_devices_timer:
            self._refresh_devices_timer.cancel()
            self._refresh_devices_timer = None


async def async_setup(hass: HomeAssistant, hass_config: dict) -> bool:
    log_setup_event("安装", "async_setup 函数执行", "debug")
    _LOGGER.debug("intretech async_setup init")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault('products', {})
    hass.data[DOMAIN].setdefault('intre_ss', {})
    hass.data[DOMAIN].setdefault('intreIot_clients', {})
    return True


async def async_initialize_core(hass: HomeAssistant, config_entry: ConfigEntry):
    """核心初始化逻辑（可重复调用）"""
    log_setup_event("初始化", "async_initialize_core 开始执行", "info")
    log_setup_event("初始化", f"配置项数据: {config_entry.data}", "debug")
    def ha_persistent_notify(
        notify_id: str, title: Optional[str] = None,
        message: Optional[str] = None
    ) -> None:
        from homeassistant.components import persistent_notification
        if title:
            persistent_notification.async_create(
                hass=hass, message=message, title=title, notification_id=notify_id
            )
        else:
            persistent_notification.async_dismiss(hass=hass, notification_id=notify_id)

    _LOGGER.debug("核心初始化逻辑执行: " + str(config_entry.data))
    try:
        intre_ss: IntreManagementEngine = await get_intress_instance_async(
            hass=hass, 
            config_entry=config_entry,
            persistent_notify=ha_persistent_notify
        )

        # 将实例注册到全局 EngineManager
        EngineManager.register_instance("intre_manage_engine", intre_ss) 
        _LOGGER.debug("IntreManagementEngine 实例已注册到 EngineManager")

        return True
    except Exception as e:
        _LOGGER.error(f"Intre Smart Home Control 初始化失败: {e}", exc_info=True)
        log_setup_event("初始化", f"核心初始化失败: {e}", "error")
        return False


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """首次设置配置项（仅执行一次）"""
    log_setup_event("安装", f"async_setup_entry 开始, entry_id={config_entry.entry_id}", "info")
    result = await async_initialize_core(hass, config_entry)
    if result:
        log_setup_event("安装", "async_setup_entry 核心初始化成功", "info")
        # 加载所有支持的平台
        for platform in SUPPORTED_PLATFORMS:
            try:
                await hass.config_entries.async_forward_entry_setup(config_entry, platform)
            except Exception as e:
                _LOGGER.debug(f"Forward platform {platform} error (ignored): {e}")
    else:
        log_setup_event("安装", "async_setup_entry 核心初始化失败", "error")
    return result


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Unload the entry."""
    log_setup_event("卸载", f"async_unload_entry 开始, entry_id={config_entry.entry_id}", "info")
    entry_id = config_entry.entry_id
    # 逐平台卸载，忽略未加载的平台
    for platform in SUPPORTED_PLATFORMS:
        try:
            await hass.config_entries.async_forward_entry_unload(config_entry, platform)
        except Exception as e:
            _LOGGER.debug(f"Unload platform {platform} error (ignored): {e}")

    # 清理products
    if DOMAIN in hass.data and 'products' in hass.data[DOMAIN]:
        hass.data[DOMAIN]['products'].pop(entry_id, None)

    # 清理intreIot_client
    if DOMAIN in hass.data and 'intreIot_clients' in hass.data[DOMAIN]:
        intreIot_client = hass.data[DOMAIN]['intreIot_clients'].pop(entry_id, None)
        if intreIot_client:
            await intreIot_client.deinit_async()
            del intreIot_client

    # 卸载时注销引擎实例，避免reload后重复注册
    EngineManager.unregister_instance("intre_manage_engine")
    log_setup_event("卸载", f"async_unload_entry 完成, entry_id={entry_id}", "info")
    return True


async def async_remove_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Remove the entry."""
    log_setup_event("卸载", f"async_remove_entry 开始, entry_id={config_entry.entry_id}", "info")
    storage: Optional[IntreIoTStorage] = hass.data[DOMAIN].get('intreiot_storage', None)

    # Clean device list
    await storage.remove_async(domain='IntreIot_config', name=f'{config_entry.entry_id}_cn', type_=dict)
    
    return True

async def async_get_entry_controls(hass: HomeAssistant, config_entry: ConfigEntry) -> List[Any]:
    """返回集成卡片上的自定义控制按钮（临时注释，因config_entry_control模块不存在）"""
    return []

# 控制灯光的函数
def control_entity(entity_id,cmd):
    domain=entity_id.split('.', 1)[0]
    url = f"{HOME_ASSISTANT_URL}/api/services/{domain}/{cmd}"
    headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
    }
    data = {
    "entity_id": entity_id
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"domain {cmd} 操作成功")
    else:
        print(f"domain {cmd} 操作失败: {response.text}")

# Socket 服务端
def start_socket_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", 8888))
    server_socket.listen(5)
    print("Socket 服务端已启动，等待客户端连接...")

    while True:
        conn, addr = server_socket.accept()
        with conn:
            print(f"Connected by {addr}")
            data = conn.recv(1024)
            if not data:
                continue
            
            try:
                json_data = json.loads(data.decode('utf-8'))
                entity_id = json_data.get('entity_id')
                cmd = json_data.get('cmd')
                
                if entity_id and cmd:
                    control_entity(entity_id, cmd)
                else:
                    print("Invalid JSON data: missing 'entity_id' or 'cmd'")
            except json.JSONDecodeError:
                print("Invalid JSON data received")
