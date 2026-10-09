"""
Binary Sensor 平台 — 将 HA 的 binary_sensor.* 实体同步到盈趣云端。

映射关系：
  HA binary_sensor 实体  →  盈趣 sensor 模块（moduleCode='sensor'）
  HA state: on/off       →  盈趣属性: onOff = "1"/"0"

工作流程：
  1. 扫描 HA 中所有 binary_sensor.* 实体
  2. 包装为 IntreBinarySensor 模块，注册到对应的 Product
  3. 订阅 HA 实体状态变化 → 实时上报盈趣云端
  4. 接收云端 property/set 命令 → 调用 HA 服务（binary_sensor 为只读，云端控制会被忽略并回复）
"""

import asyncio
import logging
import time
from typing import final
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .intreiot.intreIot_module import IntreIoTProduct, IntreIoTModule
from .intreiot.intre_manage_engine import IntreManagementEngine
from .intreiot.const import DOMAIN
from .util import StateUtils

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    # 防御：首次由 HA async_forward_entry_setup 调用时 config_data 可能尚未初始化
    if DOMAIN not in hass.data or 'config_data' not in hass.data[DOMAIN]:
        _LOGGER.debug('binary_sensor async_setup_entry: config_data not ready, skip')
        return
    if 'intre_ss' not in hass.data[DOMAIN] or config_entry.entry_id not in hass.data[DOMAIN]['intre_ss']:
        _LOGGER.debug('binary_sensor async_setup_entry: intre_ss not ready, skip')
        return

    intre_ss: IntreManagementEngine = hass.data[DOMAIN]['intre_ss'][config_entry.entry_id]
    _hadevices = hass.data[DOMAIN]['config_data']['_hadevices']

    for hadevice in _hadevices:
        product = hadevice['product']
        entitys = hadevice['entitys']
        for entity in entitys:
            if entity['entry'].entity_id.split(".")[0] == 'binary_sensor':
                module_info = {}
                _LOGGER.debug('binary_sensor create: %s', entity['entry'].entity_id)
                module_info['moduleCode'] = 'binary_sensor'
                module_info['moduleKey'] = entity['entry'].entity_id
                module_info['moduleName'] = entity['entry'].name or entity['entry'].entity_id
                module_info['entity_id'] = entity['entry'].entity_id
                binary_sensor: IntreBinarySensor = IntreBinarySensor(
                    intre_ss=intre_ss, product=product, module_info=module_info
                )
                product.add_modules(binary_sensor)


class IntreBinarySensor(IntreIoTModule):
    """将 HA binary_sensor 实体映射为盈趣传感器模块，上报 onOff 属性。"""

    _product: IntreIoTProduct
    _intre_ss: IntreManagementEngine
    _onOff: bool

    def __init__(self, intre_ss: IntreManagementEngine, product: IntreIoTProduct, module_info: dict) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing IntreBinarySensor...')
        self._intre_ss = intre_ss
        self._product = product

        # 读取初始状态
        state = intre_ss._intre_ha.get_entity_state(self._entity_id)
        self._onOff = StateUtils.util_get_state_onoff(state)

        # 订阅 HA 实体状态变化
        self._intre_ss.sub_entity(self._entity_id, self._entity_state_notify)

        # 订阅云端属性设置命令（binary_sensor 通常为只读，但仍注册回调以回复确认）
        self._product.sub_prop_set(self._module_key, self.attr_change_req)

        _LOGGER.debug('IntreBinarySensor initialized: %s = %s', self._entity_id, self._onOff)

    @final
    def get_module_prop_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey": self._module_key,
            "propertyList": [
                {
                    "propertyKey": "onOff",
                    "propertyValue": str(int(self._onOff)),
                    "timestamp": timestamp_ms
                }
            ]
        }

    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        s = self._module_key
        if s.startswith("binary_sensor."):
            instance_module_name = s.split("binary_sensor.")[1]
        else:
            instance_module_name = self._module_name

        result = {
            "templateModuleKey": "switch_1",
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,
            "propertyList": [
                {
                    "propertyKey": "onOff",
                    "propertyValue": str(int(self._onOff)),
                    "timestamp": timestamp_ms
                }
            ]
        }
        _LOGGER.debug('binary_sensor module_json: %s', result)
        return result

    async def _entity_state_notify(self, newstate) -> None:
        """HA binary_sensor 状态变化 → 上报盈趣云端。"""
        if newstate is None:
            _LOGGER.debug("IntreBinarySensor received None newstate")
            return
        _LOGGER.debug('IntreBinarySensor state changed: %s = %s', newstate.entity_id, newstate.state)
        self._onOff = StateUtils.util_get_state_onoff(newstate)
        await self._intre_ss.report_prop_async(
            self._product.productKey,
            self._product.deviceId,
            self._module_key,
            'onOff',
            str(int(self._onOff))
        )

    def attr_change_req(self, properlist: list, msg_id: str) -> None:
        """
        云端下发属性控制命令 → binary_sensor 为只读设备，回复确认但不执行控制。
        保持与盈趣云端的协议握手，避免云端重试。
        """
        _LOGGER.debug(f"binary_sensor attr_change_req: {properlist}, msg_id={msg_id}")
        # binary_sensor 是只读的，不执行任何 HA 服务调用
        # 仅回复云端确认收到（避免云端超时重试）
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self._intre_ss.prop_set_reply_async(
                        self._product.productKey,
                        self._product.deviceId,
                        msg_id,
                        '1'  # code=1 表示成功
                    )
                )
        except Exception as e:
            _LOGGER.error(f"binary_sensor prop_set_reply failed: {e}")
        return
