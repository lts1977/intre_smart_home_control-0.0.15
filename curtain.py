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
            entity_entry = entity.get('entry')
            entity_id = entity_entry.entity_id
            #_LOGGER.debug('cover create11111'+entity['entry'].entity_id)
            if entity_id.split(".")[0]== 'cover':
                #state = hass.states.get(entity_id)
                #_LOGGER.debug(state)
                #if entity['entry'].supported_features & 7:
                module_info={}
                module_info['moduleCode']='liftCurtain'
                module_info['moduleKey']=entity['entry'].entity_id
                module_info['moduleName']= entity['entry'].name
                module_info['entity_id']= entity['entry'].entity_id
                cover :IntreCover = IntreCover(intre_ss=intre_ss,product=product,module_info=module_info)
                #_LOGGER.debug(product.deviceSn)
                #_LOGGER.debug(product._name)
                product.add_modules(cover)
                    
class IntreCover(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine
    _positionPercentage:str
    _service_close_cover:int
    _finally_complementary_value:int
    _server_open_close_toggle:str
    def __init__(self,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing IntreCover...')
        self._intre_ss=intre_ss
        self._product=product
        self.state = None
        self.attributes = dict
        self._service_close_cover = 0
        self._positionPercentage = 100 - StateUtils.util_get_state_positionPercentage(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
        self._product.sub_service_call(self._module_key,self.service_call_req)
        self._product.sub_bacth_service_prop_call(self._module_key,self.batch_service_prop_call_req)
        self._finally_complementary_value = self._positionPercentage
        _LOGGER.debug(self._positionPercentage)
        # 根据行程位置设置self._server_open_close_toggle 
        if self._positionPercentage == 100:
            self._server_open_close_toggle = 'open'
        elif self._positionPercentage == 0:
            self._server_open_close_toggle = 'close'
        else:
            self._server_open_close_toggle = 'open'

    @final
    def get_module_prop_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey":self._module_key,
            "propertyList": [
                {
                "propertyKey": "positionPercentage",
                "propertyValue": str(int(self._positionPercentage)),  
                "timestamp": timestamp_ms
                }
            ]
        }
   
    @final
    def get_tls_log_json(self,serverkey:str)->list:
        timestamp_ms = str(int(time.time() * 1000))
        return[{
            "moduleKey":self._module_key,
            "service": 
                {
                "serviceKey": serverkey,
                "serviceOutputValue": "",  
                "timestamp": timestamp_ms
                }
        }]
        
    @final
    def get_module_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        match = re.search(r'_(\d+)$', self._module_key)
        s = self._module_key
        if s.startswith("curtain."):
            instance_module_name = s.split("curtain.")[1]
        else:
            instance_module_name = "窗帘"  # 或者根据需要设置默认值
        _LOGGER.debug(f'curtaininstance_module_name={instance_module_name}')
        return {
            "templateModuleKey":'liftCurtain_2',
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,  # 动态生成的名称
            "propertyList": [
                {
                "propertyKey": "positionPercentage",
                "propertyValue": str(int(self._positionPercentage)),  
                "timestamp": timestamp_ms
                }
            ]
        } 
    async def _entity_state_notify(self,newstate)->None:

        #_LOGGER.debug(f"窗帘新状态: {newstate.state,newstate.entity_id,newstate.attributes['current_position']}")   
        #await self._intre_ss.report_prop_async(self._product.productKey,self._product.deviceId,self._module_key,'positionPercentage',newstate.attributes['current_position'])
        #supported_features = attributes.get('supported_features', 'N/A')
        #_LOGGER.debug(f"Supported features for : {supported_features}")
        # 先检查 newstate 是否为 None
        if newstate is None:
            _LOGGER.debug("Received None as newstate in _entity_state_notify")
            return


        if 'current_position' not in newstate.attributes:
            _LOGGER.debug("current_position key not found in state attributes.")
        else:
            current_position= newstate.attributes['current_position']
            current_position_int = int(current_position)
            _LOGGER.debug(
                f"Curtain Current state: {newstate.state}, Entity ID: {newstate.entity_id}, "
                f"Current_position= : {current_position},service_close_cover= : {self._service_close_cover}"
            )
            complementary_value = 100 - current_position_int
            if not isinstance(current_position, (int, float)):
                _LOGGER.debug("current_position value is not a number.")
            _LOGGER.debug(
                f"complementary_value= : {complementary_value}"
            )
            if self._service_close_cover != 0:
                self._service_close_cover -= 1
                # 可选：确保值不会小于0（双重保险）
                if self._service_close_cover < 0:
                    self._service_close_cover = 0
            else: 
                _LOGGER.debug(
                    f"self._finally_complementary_value= : {self._finally_complementary_value}"
                )
                if  self._finally_complementary_value != complementary_value:
                    self._finally_complementary_value = complementary_value

                    if current_position == 100:
                        self._server_open_close_toggle = 'close'
                    elif current_position == 0:
                        self._server_open_close_toggle = 'open'
                    else:
                        self._server_open_close_toggle = 'open' 
                    await self._intre_ss.report_prop_async(
                        self._product.productKey,
                        self._product.deviceId,
                        self._module_key,
                        'positionPercentage',
                        complementary_value
                    )
                    _LOGGER.debug(
                        f"self._server_open_close_toggle= : {self._server_open_close_toggle}"
                    )     
        return   
    def service_call_req(self, service_call_data: dict) -> None:
        data = {'entity_id': self._entity_id}
        service_mapping = {
            'close': 'close_cover',
            'open': 'open_cover',
            'pause': 'stop_cover'  # 映射到HA标准的"停止"服务
        }

        try:
            # 提取关键参数（从日志结构匹配）
            msg_id = service_call_data.get('msgId')
            data_layer = service_call_data.get('data', {})
            module_data = data_layer.get('module', {})
            service_data = module_data.get('service', {})
            service_key = service_data.get('serviceKey')

            _LOGGER.debug(
                f"处理服务调用: msgId={msg_id}, service_key={service_key}, "
                f"目标实体={self._entity_id}"
            )

            if not service_key:
                _LOGGER.warning("service_call_data中未找到serviceKey")
                return

            # 处理toggle逻辑（单独处理，不依赖mapping）
            if service_key == 'toggle':
                _LOGGER.debug(f"当前toggle状态: {self._server_open_close_toggle}")
                # 根据当前状态切换服务
                target_service = 'close_cover' if self._server_open_close_toggle == 'open' else 'open_cover'
                new_toggle_state = 'close' if self._server_open_close_toggle == 'open' else 'open'
                
                # 更新状态并调用服务
                self._server_open_close_toggle = new_toggle_state
                self._intre_ss.call_ha_service('cover', target_service, data)
                _LOGGER.debug(f"执行toggle，调用服务: {target_service}")
                return  # 避免后续重复处理

            # 处理mapping中的服务（open/close/pause）
            if service_key not in service_mapping:
                _LOGGER.warning(f"不支持的serviceKey: {service_key}")
                return

            # 获取映射后的HA标准服务
            ha_service = service_mapping[service_key]

            # 处理TSL日志上报和回复（异步操作）
            try:
                # 准备异步任务（使用HA的事件循环，避免手动创建）
                coroutines = [
                    self._intre_ss.report_device_tsl_log_async(
                        self._product.productKey,
                        self._product.deviceId,
                        self.get_tls_log_json(service_key)
                    ),
                    self._intre_ss.service_set_reply_async(
                        self._product.productKey,
                        self._product.deviceId,
                        self._module_key,
                        service_key,
                        msg_id,
                        '1'
                    )
                ]

                # 使用Home Assistant的事件循环（关键优化）
                # 避免手动创建/关闭循环，防止与HA主循环冲突
                loop = self._intre_ss._hass.loop  # 假设_intre_ss持有hass实例
                for coro in coroutines:
                    loop.create_task(coro)  # 加入HA的循环，自动处理

            except Exception as e:
                _LOGGER.error(f"TSL日志上报失败: {str(e)}", exc_info=True)

            # 调用HA标准服务（核心操作）
            try:
                self._intre_ss.call_ha_service('cover', ha_service, data)
                _LOGGER.debug(f"成功调用HA服务: cover.{ha_service}, 实体: {self._entity_id}")
                
                # 记录自定义状态（添加注释说明用途）
                if service_key != 'pause':
                    self._service_close_cover = 2  # 示例：标记为"已执行开关操作"
            except HomeAssistantError as e:
                # 捕获服务调用失败（如实体不支持服务）
                _LOGGER.error(
                    f"调用服务失败: cover.{ha_service} 实体 {self._entity_id} 不支持该服务。错误: {str(e)}"
                )

        except KeyError as e:
            _LOGGER.error(f"service_call_data缺少关键参数: {str(e)}", exc_info=True)
        except Exception as e:
            _LOGGER.error(f"service_call_req执行出错: {str(e)}", exc_info=True) 

    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        # 初始化基础数据
        data = {
            'entity_id': self._entity_id
        }
        _LOGGER.debug(f"batch_service_prop_data: {batch_service_prop_data}")
        
        # 步骤1：安全提取嵌套的 deviceModuleList（多层键校验，避免 KeyError）
        # 使用 dict.get() 方法，键不存在时返回默认值（空字典/空列表），不抛出异常
        top_level_data = batch_service_prop_data.get('data', {})
        device_module_list = top_level_data.get('deviceModuleList', [])
        
        # 步骤2：遍历设备模块列表，再访问每个模块内的 propertyList
        for device_module in device_module_list:
            # 安全提取当前模块的 propertyList，默认空列表
            property_list = device_module.get('propertyList', [])
            for prop in property_list:
                if prop.get('propertyKey') == 'positionPercentage':  # 同样使用 get 避免键不存在
                    prop_value = prop.get('propertyValue', '')
                    # 增加数值转换容错
                    try:
                        position = int(prop_value)
                    except (ValueError, TypeError):
                        _LOGGER.warning(f"无效的 positionPercentage 值：{prop_value}，无法转换为整数")
                        continue
                    
                    if 0 <= position <= 100:
                        data['position'] = 100 - position
                        _LOGGER.debug("Setting cover position to %d", position)
                        self._service_close_cover = 1
                        self._intre_ss.call_ha_service('cover', 'set_cover_position', data)
                        _LOGGER.debug("batch1_service=%s ", data)
            
            # 步骤3：遍历当前模块内的 serviceList（同样安全提取）
            service_list = device_module.get('serviceList', [])
            for service in service_list:
                service_key = service.get('serviceKey', '')
                if service_key == 'close':
                    self._server_open_close_toggle = 'open'
                    service_name = 'close_cover'  # 避免覆盖循环变量 service
                    self._intre_ss.call_ha_service('cover', service_name, data)
                    _LOGGER.debug("batch2_service=%s %s", service_name, data)
                elif service_key == 'open':
                    self._server_open_close_toggle = 'close'
                    service_name = 'open_cover'
                    self._intre_ss.call_ha_service('cover', service_name, data)
                    _LOGGER.debug("batch2_service=%s %s", service_name, data)
                elif service_key == 'stop':
                    service_name = 'stop_cover'
                    self._intre_ss.call_ha_service('cover', service_name, data)
                    _LOGGER.debug("batch2_service=%s %s", service_name, data)
                else:
                    if service_key:  # 仅当 serviceKey 非空时打印警告，避免无意义日志
                        _LOGGER.debug(f'Unsupported serviceKey: {service_key}')  

    def attr_change_req(self, properlist: list,msg_id: str) -> None:
        _LOGGER.debug(f"properlist: {properlist}")
        data={
            'entity_id':self._entity_id
        }
        for prop in properlist:
            if prop['propertyKey'] == 'positionPercentage':
                position = int(prop['propertyValue'])  
                if 0 <= position <= 100: 
                    data['position'] = 100 - position
                    _LOGGER.debug("Setting cover position to %d", position)
                    self._service_close_cover = 1
                    self._intre_ss.call_ha_service('cover', 'set_cover_position', data)
                else:
                    _LOGGER.debug("Invalid position percentage: %d", prop['propertyValue'])
        return

async def test_fun()->bool:
    _LOGGER.debug("test-curtain")  