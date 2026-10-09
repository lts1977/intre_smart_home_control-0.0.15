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
from .util import StateUtils
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
            #_LOGGER.debug('switch create'+entity['entry'].entity_id)
            if entity['entry'].entity_id.split(".")[0] in ('switch', 'input_boolean'):
                module_info={}
                _LOGGER.debug('switch create')
                module_info['moduleCode']='switch'
                module_info['moduleKey']=entity['entry'].entity_id
                module_info['moduleName']= entity['entry'].name
                module_info['entity_id']= entity['entry'].entity_id
                switch :IntreSwitch = IntreSwitch(intre_ss=intre_ss,product=product,module_info=module_info)
                _LOGGER.debug(product.deviceSn)
                _LOGGER.debug(product._name) 
                product.add_modules(switch)

class IntreSwitch(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine
    _onOff:bool

    def __init__(self,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing IntreSwitch...')
        self._intre_ss=intre_ss
        self._product=product

        self._onOff =StateUtils.util_get_state_onoff(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
        self._product.sub_service_call(self._module_key,self.service_call_req)
        self._product.sub_bacth_service_prop_call(self._module_key,self.batch_service_prop_call_req)
        _LOGGER.debug(self._onOff) 
    
    @final
    def get_module_prop_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey":self._module_key,
            "propertyList": [
                {
                "propertyKey": "onOff",
                "propertyValue":str(int(self._onOff)),  
                "timestamp": timestamp_ms
                }
            ]
        }
        

    @final
    def get_module_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        s = self._module_key
        if s.startswith("switch."):
            instance_module_name = s.split("switch.")[1]
        elif s.startswith("input_boolean."):
            instance_module_name = s.split("input_boolean.")[1]
        else:
            instance_module_name = "灯"  # 或者根据需要设置默认值
        _LOGGER.debug(f'instance_module_name={instance_module_name}')
        result= {
            "templateModuleKey":'switch_1',
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,  # 动态生成的名称
            "propertyList": [
                {
                "propertyKey": "onOff",
                "propertyValue":str(int(self._onOff)),  
                "timestamp": timestamp_ms
                }
            ]
        }
        _LOGGER.debug(
            f"productKey: {self._product.productKey}, deviceId: {self._product.deviceId} "
            f"_module_key: {self._module_key}, _module_name: {self._module_name}"          
        )

        _LOGGER.debug(result)
        return result

    async def _entity_state_notify(self,newstate)->None:
        if newstate is None:
            _LOGGER.debug("Received None as newstate in _entity_state_notify")
            return
        _LOGGER.debug(f"开关新状态: {newstate.state,newstate.entity_id}")  
        self._onOff=StateUtils.util_get_state_onoff(newstate)
        await self._intre_ss.report_prop_async(self._product.productKey,self._product.deviceId,self._module_key,'onOff',str(int(self._onOff)))
        
        _LOGGER.debug("SWITCH state" + str(self._onOff))
        return

    def service_call_req(self, service_call_data: dict) -> None:
        _LOGGER.debug(f"service_call_data: {service_call_data}")
        
        data = {
            'entity_id': self._entity_id
        }
        
        # 从data字段获取模块信息（根据日志结构修正路径）
        module = service_call_data.get('data', {}).get('module', {})
        service = module.get('service', {})
        
        # 检查服务键
        if service.get('serviceKey') == 'toggleOnOff':
            # 根据当前状态决定是开启还是关闭
            target_service = 'turn_off' if self._onOff else 'turn_on'
            
            _LOGGER.debug(f"call_service={target_service} {data}")  
            # onoff light 会复用 IntreSwitch 模板，调用HA服务时必须使用实体自身domain
            self._intre_ss.call_ha_service(self._entity_id.split('.')[0], target_service, data)
        

    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        data = {
            'entity_id': self._entity_id
        }
        entity_domain = self._entity_id.split('.')[0]
        
        # 步骤1：逐层解析嵌套数据，提取deviceModuleList（兼容键不存在的情况）
        # 先获取顶层的data，再获取deviceModuleList，默认空列表避免报错
        device_module_list = batch_service_prop_data.get('data', {}).get('deviceModuleList', [])
        
        # 步骤2：遍历deviceModuleList，处理每个deviceModule
        for device_module in device_module_list:
            # 从单个deviceModule中获取propertyList（兼容键不存在）
            for prop in device_module.get('propertyList', []):
                if prop['propertyKey'] == 'onOff':
                    service = 'turn_on' if prop['propertyValue'] == '1' else 'turn_off'
                    _LOGGER.debug("batch1_service=%s %s", service, data)  
                    self._intre_ss.call_ha_service(entity_domain, service, data)
            
            # 从单个deviceModule中获取serviceList（兼容键不存在）
            for service in device_module.get('serviceList', []):
                if service['serviceKey'] == 'toggleOnOff':
                    target_service = 'turn_off' if self._onOff else 'turn_on'
                    _LOGGER.debug("batch2_service=%s %s", target_service, data)  
                    self._intre_ss.call_ha_service(entity_domain, target_service, data)
        
    def attr_change_req(self, properlist: list,msg_id: str) -> None:
        _LOGGER.debug(f"properlist: {properlist}")
        data={
            'entity_id':self._entity_id
        }
        entity_domain = self._entity_id.split('.')[0]
        service='turn_on'
        for prop in properlist:
            if prop['propertyKey']=='onOff':
                if prop['propertyValue']=='0':
                    service='turn_off'
                _LOGGER.debug("change_service=%s %s",service,data)  
                self._intre_ss.call_ha_service(entity_domain,service,data)
        return

    


async def test_fun()->bool:
    _LOGGER.debug("test-switch")  