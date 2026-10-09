"""
Button 平台 — 将 HA 的 button.* 实体同步到盈趣云端。

映射关系：
  HA button 实体       →  盈趣 switch 模块（moduleCode='button'）
  HA button 按下事件   →  盈趣属性: onOff = "1"（触发上报）
  云端 toggleOnOff    →  调用 HA button.press 服务

工作流程：
  1. 扫描 HA 中所有 button.* 实体
  2. 包装为 IntreButtonEntity 模块，注册到对应的 Product
  3. 订阅 HA 实体状态变化（button 按下后会有短暂状态变化）→ 上报盈趣云端
  4. 接收云端 property/set 或 service/call 命令 → 调用 HA button.press 服务

与 event.py 的区别：
  - event.py 处理的是 HA event.* 域实体（ZHA 等触发型事件），使用 report_event_async 上报
  - button.py 处理的是 HA button.* 域实体（原生按钮），使用 report_prop_async 上报 onOff
  - button.py 额外支持云端反向控制（云端下发命令 → 按下 HA 按钮）
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    # 防御：首次由 HA async_forward_entry_setup 调用时 config_data 可能尚未初始化
    if DOMAIN not in hass.data or 'config_data' not in hass.data[DOMAIN]:
        _LOGGER.debug('button async_setup_entry: config_data not ready, skip')
        return
    if 'intre_ss' not in hass.data[DOMAIN] or config_entry.entry_id not in hass.data[DOMAIN]['intre_ss']:
        _LOGGER.debug('button async_setup_entry: intre_ss not ready, skip')
        return

    intre_ss: IntreManagementEngine = hass.data[DOMAIN]['intre_ss'][config_entry.entry_id]
    _hadevices = hass.data[DOMAIN]['config_data']['_hadevices']

    for hadevice in _hadevices:
        product = hadevice['product']
        entitys = hadevice['entitys']
        for entity in entitys:
            if entity['entry'].entity_id.split(".")[0] == 'button':
                module_info = {}
                _LOGGER.debug('button create: %s', entity['entry'].entity_id)
                module_info['moduleCode'] = 'button'
                module_info['moduleKey'] = entity['entry'].entity_id
                module_info['moduleName'] = entity['entry'].name or entity['entry'].entity_id
                module_info['entity_id'] = entity['entry'].entity_id
                button_entity: IntreButtonEntity = IntreButtonEntity(
                    intre_ss=intre_ss, product=product, module_info=module_info
                )
                product.add_modules(button_entity)


class IntreButtonEntity(IntreIoTModule):
    """将 HA button 实体映射为盈趣开关模块，上报 onOff 并接收云端控制。"""

    _product: IntreIoTProduct
    _intre_ss: IntreManagementEngine
    _last_press_time: float

    def __init__(self, intre_ss: IntreManagementEngine, product: IntreIoTProduct, module_info: dict) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing IntreButtonEntity...')
        self._intre_ss = intre_ss
        self._product = product
        self._last_press_time = 0.0

        # 订阅 HA 实体状态变化（button 按下时 HA 会触发状态变化事件）
        self._intre_ss.sub_entity(self._entity_id, self._entity_state_notify)

        # 订阅云端属性设置命令（云端下发 onOff 控制命令）
        self._product.sub_prop_set(self._module_key, self.attr_change_req)

        # 订阅云端服务调用命令（云端下发 toggleOnOff 服务）
        self._product.sub_service_call(self._module_key, self.service_call_req)

        # 订阅云端批量属性/服务控制
        self._product.sub_bacth_service_prop_call(self._module_key, self.batch_service_prop_call_req)

        _LOGGER.debug('IntreButtonEntity initialized: %s', self._entity_id)

    @final
    def get_module_prop_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey": self._module_key,
            "propertyList": [
                {
                    "propertyKey": "onOff",
                    "propertyValue": "0",
                    "timestamp": timestamp_ms
                }
            ]
        }

    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        s = self._module_key
        if s.startswith("button."):
            instance_module_name = s.split("button.")[1]
        else:
            instance_module_name = self._module_name

        result = {
            "templateModuleKey": "switch_1",
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,
            "propertyList": [
                {
                    "propertyKey": "onOff",
                    "propertyValue": "0",
                    "timestamp": timestamp_ms
                }
            ]
        }
        _LOGGER.debug('button module_json: %s', result)
        return result

    async def _entity_state_notify(self, newstate) -> None:
        """
        HA button 状态变化 → 上报盈趣云端。
        button 实体按下后状态会短暂变化，上报 onOff="1" 表示一次触发。
        """
        if newstate is None:
            _LOGGER.debug("IntreButtonEntity received None newstate")
            return

        _LOGGER.debug('IntreButtonEntity state changed: %s = %s', newstate.entity_id, newstate.state)

        # 防抖：同一秒内多次触发只上报一次
        now = time.time()
        if now - self._last_press_time < 1.0:
            _LOGGER.debug('button debounced, skip report')
            return
        self._last_press_time = now

        # 上报触发事件到云端
        await self._intre_ss.report_prop_async(
            self._product.productKey,
            self._product.deviceId,
            self._module_key,
            'onOff',
            '1'
        )

    def service_call_req(self, service_call_data: dict) -> None:
        """云端下发服务调用（toggleOnOff）→ 触发 HA button.press。"""
        _LOGGER.debug(f"button service_call_data: {service_call_data}")

        data = {'entity_id': self._entity_id}

        module = service_call_data.get('data', {}).get('module', {})
        service = module.get('service', {})

        if service.get('serviceKey') == 'toggleOnOff':
            _LOGGER.debug(f"button toggleOnOff → press: {data}")
            self._intre_ss.call_ha_service('button', 'press', data)

    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        """云端批量控制命令 → 处理 button 相关的 onOff 和 toggleOnOff。"""
        data = {'entity_id': self._entity_id}

        device_module_list = batch_service_prop_data.get('data', {}).get('deviceModuleList', [])

        for device_module in device_module_list:
            # 处理 propertyList 中的 onOff 命令
            for prop in device_module.get('propertyList', []):
                if prop.get('propertyKey') == 'onOff' and prop.get('propertyValue') == '1':
                    _LOGGER.debug("button batch onOff=1 → press: %s", data)
                    self._intre_ss.call_ha_service('button', 'press', data)

            # 处理 serviceList 中的 toggleOnOff 命令
            for service in device_module.get('serviceList', []):
                if service.get('serviceKey') == 'toggleOnOff':
                    _LOGGER.debug("button batch toggleOnOff → press: %s", data)
                    self._intre_ss.call_ha_service('button', 'press', data)

    def attr_change_req(self, properlist: list, msg_id: str) -> None:
        """云端下发属性设置命令 → 按下 HA button。"""
        _LOGGER.debug(f"button attr_change_req: {properlist}, msg_id={msg_id}")

        data = {'entity_id': self._entity_id}

        for prop in properlist:
            if prop.get('propertyKey') == 'onOff' and prop.get('propertyValue') == '1':
                _LOGGER.debug("button attr_change onOff=1 → press: %s", data)
                self._intre_ss.call_ha_service('button', 'press', data)

        return
