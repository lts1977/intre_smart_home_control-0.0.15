import asyncio
import base64
import json
import logging
import re
import time
import hmac
import hashlib
import paho.mqtt.client as mqtt
from typing import Any, Callable, Optional, final
from urllib.parse import urlencode
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import (Entity,DeviceInfo)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .intreiot.intreIot_module import (IntreIoTProduct,IntreIoTModule)
from .intreiot.intre_manage_engine import (IntreManagementEngine)
from .intreiot.const   import (DOMAIN, SUPPORTED_PLATFORMS)
from .intreiot.intreIot_client import IntreIoTClient

_LOGGER = logging.getLogger(__name__)
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    intre_ss:IntreManagementEngine =hass.data[DOMAIN]['intre_ss'][config_entry.entry_id]
    _hadevices = hass.data[DOMAIN]['config_data']['_hadevices']
    
    for hadevice in _hadevices:
        product = hadevice['product']
        entitys = hadevice['entitys']
        for entity in entitys:
            entity_entry = entity.get('entry')
            entity_id = entity_entry.entity_id
            
            if entity_id.split(".")[0]== 'climate':
                _LOGGER.debug(f"entity_id: {entity_id}")
                state = hass.states.get(entity_id)
                _LOGGER.debug("climate.")
                _LOGGER.debug(state)
                if state is not None:
                    attributes = state.attributes
                    supported_features = attributes.get('supported_features', 'N/A')
                    if HVACAction.HEATING in supported_features:# 判断是否空调
                        module_info={} 
                        module_info['moduleCode']='airConditioner'
                        module_info['moduleKey']=entity['entry'].entity_id
                        module_info['moduleName']= entity['entry'].name
                        module_info['entity_id']= entity['entry'].entity_id
                        fan :IntreHavc = IntreHavc(intre_ss=intre_ss,product=product,module_info=module_info)
                        product.add_modules(fan)
class IntreHavc(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine
    _onOff:bool

    def __init__(self,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict) -> None:
        super().__init__(module_info=module_info)
        self._intre_ss=intre_ss
        self._product=product
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
    
    @final
    def get_module_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
         match = re.search(r'_(\d+)$', self._module_key)
        if match:
            index = match.group(1)
            instance_module_name = f"climate{index}"
        else:
            # 匹配失败时使用默认名称
            instance_module_name = "未知设备" 
        return {
            "templateModuleKey":'airConditioner',
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,  # 动态生成的名称
            "propertyList": [
                {
                "propertyKey": "onOff",
                "propertyValue": "1",
                "timestamp": timestamp_ms
                },                
                {
                "propertyKey": "environmentTemperature",
                "propertyValue": "0",
                "timestamp": timestamp_ms
                },                
                {
                "propertyKey": "settingTemperature",
                "propertyValue": "16",
                "timestamp": timestamp_ms
                },                
                {
                "propertyKey": "ACMode",
                "propertyValue": "1",
                "timestamp": timestamp_ms
                },                
                {
                "propertyKey": "swing",
                "propertyValue": "0",
                "timestamp": timestamp_ms
                }
            ]
        }
    async def _entity_state_notify(self,newstate)->None:
        _LOGGER.debug(f"AIR新状态: {newstate.state,newstate.entity_id}") 
        attributes = newstate.attributes
  
        if newstate.state =='on':
            await self._intre_ss.report_prop_async(self._product.productKey,self._product.deviceId,self._module_key,'onOff','1')
        else:
            await self._intre_ss.report_prop_async(self._product.productKey,self._product.deviceId,self._module_key,'onOff','0')
        return
    
    def attr_change_req(self, properlist: list,msg_id: str) -> None:
        _LOGGER.debug(f"properlist: {properlist}")
        data={
            'entity_id':self._entity_id
        }
        service='turn_on'
        for prop in properlist:
            if prop['propertyKey']=='onOff':
                if prop['propertyValue']=='0':
                    service='turn_off'
                _LOGGER.debug("service=%s %s",service,data)  
                self._intre_ss.call_ha_service('fan',service,data)
        return

async def test_fun()->bool:
    _LOGGER.debug("test-air")  