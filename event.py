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
            #_LOGGER.debug('button create'+entity['entry'].entity_id)
            if entity['entry'].entity_id.split(".")[0]== 'event':
                module_info={}
                
                
                _LOGGER.debug('button create')
                module_info['moduleCode']='button'
                module_info['moduleKey']=entity['entry'].entity_id
                module_info['moduleName']= entity['entry'].name
                module_info['entity_id']= entity['entry'].entity_id
                button :IntreButton = IntreButton(intre_ss=intre_ss,product=product,module_info=module_info)
                #_LOGGER.debug(product.deviceSn)
                #_LOGGER.debug(product._name)
                product.add_modules(button)

class IntreButton(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine


    def __init__(self,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict) -> None:
        super().__init__(module_info=module_info)
        self._intre_ss=intre_ss
        self._product=product
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
    @final
    def get_module_prop_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        match = re.search(r'_(\d+)$', self._module_key)
        if match:
            index = match.group(1)
            instance_module_name = f"按键{index}"
        else:
            # 匹配失败时使用默认名称
            instance_module_name = "未知设备"
        # 构建propertyValue字典
        property_value = {
            'type': 0,  
            'deviceId': self._product.deviceId, 
            'moduleKey': 'button_1',
            'moduleCode': 'button',
            'action': {
                'propertyInfo': {
                    'propertyKey': 'click',
                    'propertyValue': '0'  
                }
            }
        }
        # 将 property_value 转换为 JSON 字符串
        property_value_json = json.dumps(property_value)

        return {
            "templateModuleKey": 'button_1',
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,  # 动态生成的名称
            "propertyList": [
                {
                    "propertyKey": "click",
                    "propertyValue": property_value_json,  
                    "timestamp": timestamp_ms  
                }
            ]
        }
    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        # 构建propertyValue字典
        property_value = {
            'type': 0,  
            'deviceId': self._product.deviceId, 
            'moduleKey': 'button_1',
            'moduleCode': 'button',
            'action': {
                'propertyInfo': {
                    'propertyKey': 'click',
                    'propertyValue': '0'  
                }
            }
        }
        # 将 property_value 转换为 JSON 字符串
        property_value_json = json.dumps(property_value)
        return {
            "templateModuleKey": 'button_1',
            "instanceModuleKey": self._module_key,
            "propertyList": [
                {
                    "propertyKey": "click",
                    "propertyValue": property_value_json,  
                    "timestamp": timestamp_ms  
                }
            ]
        }

    async def _entity_state_notify(self,newstate)->None:
        _LOGGER.debug(f"button状态: {newstate.state,newstate.entity_id}")  

        # 将 property_value 转换为 JSON 字符串
        
        await self._intre_ss.report_event_async(self._product.productKey,self._product.deviceId,self._module_key,'click','')

    
    def attr_change_req(self, properlist: list,msg_id: str) -> None:
        _LOGGER.debug(f"properlist: {properlist}")
        _LOGGER.debug(f"msg_id: {msg_id}")
        prop_value = None  # 初始化变量，避免可能的未定义错误
        
        for prop in properlist:
            # 只处理propertyKey为'click'的属性
            if prop.get('propertyKey') != 'click':
                continue
                
            # 获取原始propertyValue，默认为空JSON字符串
            property_value_str = prop.get('propertyValue', '{}')
            _LOGGER.debug(f"收到click属性，原始值: {property_value_str}")
            
            try:
                property_value = json.loads(property_value_str)
                _LOGGER.debug(f"解析click属性成功: {property_value}")
                
                # 重新序列化为字符串（确保与方法参数类型匹配）
                prop_value = json.dumps(property_value)
            except json.JSONDecodeError as e:
                _LOGGER.error(f"解析click属性失败: {e}")
                continue  # 如果解析失败，继续处理下一个属性

        # 如果有需要处理的click属性值
        if prop_value is not None:
            # 如果必须在同步函数中调用异步方法
            try:
                loop = asyncio.get_event_loop()
                # 定义要执行的异步任务列表
                tasks = [
                    self._intre_ss.prop_set_reply_async(
                        self._product.productKey,
                        self._product.deviceId,
                        msg_id,
                        '1'
                    ),
                    self._intre_ss.report_prop_async(
                        self._product.productKey,
                        self._product.deviceId,
                        self._module_key,
                        'click',
                        prop_value
                    )
                ]
                
                # 如果事件循环正在运行，使用create_task
                if loop.is_running():
                    for task in tasks:
                        loop.create_task(task)
                else:
                    # 否则直接运行直到完成
                    loop.run_until_complete(asyncio.gather(*tasks))
            except Exception as e:
                _LOGGER.error(f"Failed to report property: {e}")
        
        # 注释掉的代码段保留
        '''
        data={
            'entity_id':self._entity_id
        }
        for prop in properlist:
            if prop['propertyKey']=='click':
                service=prop['propertyValue']
                self._intre_ss.call_ha_service('event',service,data)
        '''   
        return

    


async def test_fun()->bool:
    _LOGGER.debug("test-button")  