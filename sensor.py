import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional, final
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .intreiot.intreIot_module import (IntreIoTProduct, IntreIoTModule)
from .intreiot.intre_manage_engine import (IntreManagementEngine)
from .intreiot.const import (DOMAIN)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    intre_ss: IntreManagementEngine = hass.data[DOMAIN]['intre_ss'][config_entry.entry_id]
    _hadevices = hass.data[DOMAIN]['config_data']['_hadevices']

    for hadevice in _hadevices:
        product = hadevice['product']
        entitys = hadevice['entitys']
        for entity in entitys:
            if entity['entry'].entity_id.split(".")[0] == 'sensor':
                module_info = {}
                _LOGGER.debug('sensor create: %s', entity['entry'].entity_id)
                module_info['moduleCode'] = 'sensor'
                module_info['moduleKey'] = entity['entry'].entity_id
                module_info['moduleName'] = entity['entry'].name or entity['entry'].entity_id
                module_info['entity_id'] = entity['entry'].entity_id
                sensor: IntreSensor = IntreSensor(intre_ss=intre_ss, product=product, module_info=module_info)
                product.add_modules(sensor)


class IntreSensor(IntreIoTModule):
    _product: IntreIoTProduct
    _intre_ss: IntreManagementEngine
    _sensor_value: str

    def __init__(self, intre_ss: IntreManagementEngine, product: IntreIoTProduct, module_info: dict) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing IntreSensor...')
        self._intre_ss = intre_ss
        self._product = product

        # 读取初始状态值
        state = intre_ss._intre_ha.get_entity_state(self._entity_id)
        self._sensor_value = str(state.state) if state and state.state is not None else '0'

        # 订阅状态变化
        self._intre_ss.sub_entity(self._entity_id, self._entity_state_notify)
        _LOGGER.debug('IntreSensor initialized: %s = %s', self._entity_id, self._sensor_value)

    @final
    def get_module_prop_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey": self._module_key,
            "propertyList": [
                {
                    "propertyKey": "temperatureValue",
                    "propertyValue": self._sensor_value,
                    "timestamp": timestamp_ms
                }
            ]
        }

    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        s = self._module_key
        if s.startswith("sensor."):
            instance_module_name = s.split("sensor.")[1]
        else:
            instance_module_name = self._module_name
        _LOGGER.debug('sensor instance_module_name=%s', instance_module_name)
        result = {
            "templateModuleKey": "switch_1",
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,
            "propertyList": [
                {
                    "propertyKey": "onOff",
                    "propertyValue": self._sensor_value,
                    "timestamp": timestamp_ms
                }
            ]
        }
        _LOGGER.debug('sensor module_json: %s', result)
        return result

    async def _entity_state_notify(self, newstate) -> None:
        if newstate is None:
            _LOGGER.debug("IntreSensor received None newstate")
            return
        _LOGGER.debug('IntreSensor state changed: %s = %s', newstate.entity_id, newstate.state)
        self._sensor_value = str(newstate.state) if newstate.state is not None else '0'
        await self._intre_ss.report_prop_async(
            self._product.productKey,
            self._product.deviceId,
            self._module_key,
            'temperatureValue',
            self._sensor_value
        )
