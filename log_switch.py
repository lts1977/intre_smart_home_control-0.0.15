import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .intreiot.setup_logger import is_logging_enabled, set_logging_enabled
from .const import CONF_ENABLE_DEBUG_LOG, DEFAULT_ENABLE_DEBUG_LOG

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """设置日志开关实体"""
    async_add_entities([IntreLogSwitch(config_entry)], True)

class IntreLogSwitch(SwitchEntity):
    """日志开关实体"""
    _attr_has_entity_name = True
    _attr_name = "日志开关"
    _attr_icon = "mdi:file-document-outline"
    
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._attr_unique_id = f"intre_log_switch_{config_entry.entry_id}"
        self._attr_is_on = self._get_current_state()
    
    def _get_current_state(self) -> bool:
        """获取当前日志开关状态"""
        return self._config_entry.data.get(CONF_ENABLE_DEBUG_LOG, DEFAULT_ENABLE_DEBUG_LOG)
    
    async def async_turn_on(self, **kwargs) -> None:
        """开启日志"""
        set_logging_enabled(True)
        self._update_config_entry(True)
        self._attr_is_on = True
        self.async_write_ha_state()
    
    async def async_turn_off(self, **kwargs) -> None:
        """关闭日志"""
        set_logging_enabled(False)
        self._update_config_entry(False)
        self._attr_is_on = False
        self.async_write_ha_state()
    
    def _update_config_entry(self, enabled: bool) -> None:
        """更新配置项中的日志开关状态"""
        new_data = self._config_entry.data.copy()
        new_data[CONF_ENABLE_DEBUG_LOG] = enabled
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            data=new_data
        )
    
    @property
    def device_info(self):
        """返回设备信息，将开关绑定到集成设备"""
        return {
            "identifiers": {("intre_smart_home_control", self._config_entry.entry_id)},
            "name": "Intre 智能控制",
            "manufacturer": "Intretech",
            "model": "Smart Home Control",
            "suggested_area": "Home",
        }
