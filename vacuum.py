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
from homeassistant.helpers.entity import (Entity, DeviceInfo)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .intreiot.intreIot_module import (IntreIoTProduct, IntreIoTModule)
from .intreiot.intre_manage_engine import (IntreManagementEngine)
from .intreiot.const import (DOMAIN, SUPPORTED_PLATFORMS)
from .intreiot.intreIot_client import IntreIoTClient
from .util import StateUtils
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
            # 筛选出vacuum领域的实体
            if entity['entry'].entity_id.split(".")[0] == 'vacuum':
                entity_id = entity['entry'].entity_id  # 从实体中获取entity_id
                entity_state = intre_ss._intre_ha.get_entity_state(entity_id)  # 获取实体状态
                _LOGGER.debug(f"vacuum entity_id: {entity_id}")
                _LOGGER.debug(f"vacuum entity_state: {entity_state}")
                module_info = {}
                _LOGGER.debug('vacuum create')
                module_info['moduleCode'] = 'robotVacuumCleaner'
                module_info['moduleKey'] = entity['entry'].entity_id
                module_info['moduleName'] = entity['entry'].name
                module_info['entity_id'] = entity['entry'].entity_id
                vacuum = IntreVacuum(intre_ss=intre_ss, product=product, module_info=module_info)
                _LOGGER.debug(product.deviceSn)
                _LOGGER.debug(product._name)
                product.add_modules(vacuum)

class IntreVacuum(IntreIoTModule):
    _product: IntreIoTProduct
    _intre_ss: IntreManagementEngine
    _cleanerStatus: str  # 0:空闲, 1:正在清洁, 2:暂停清洁

    def __init__(self, intre_ss: IntreManagementEngine, product: IntreIoTProduct, module_info: dict) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing IntreVacuum...')
        self._intre_ss = intre_ss
        self._product = product

        # 初始化扫地机器人状态
        ha_state = intre_ss._intre_ha.get_entity_state(self._entity_id)
        self._cleanerStatus = self._get_cleaner_status(ha_state)
        self._intre_ss.sub_entity(self._entity_id, self._entity_state_notify)
        self._product.sub_prop_set(self._module_key, self.attr_change_req)
        self._product.sub_service_call(self._module_key, self.service_call_req)
        self._product.sub_bacth_service_prop_call(self._module_key, self.batch_service_prop_call_req)
        _LOGGER.debug(f"Initial cleaner status: {self._cleanerStatus}")

    @final
    def get_module_prop_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey": self._module_key,
            "propertyList": [
                {
                    "propertyKey": "cleanerStatus",
                    "propertyValue": self._cleanerStatus,
                    "timestamp": timestamp_ms
                }
            ]
        }

    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        s = self._module_key
        if s.startswith("vacuum."):
            instance_module_name = s.split("vacuum.")[1]
        else:
            instance_module_name = "扫地机器人"  # 默认名称
        _LOGGER.debug(f'instance_module_name={instance_module_name}')
        result = {
            "templateModuleKey": 'robotVacuumCleaner',
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,
            "propertyList": [
                {
                    "propertyKey": "cleanerStatus",
                    "propertyValue": self._cleanerStatus,
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

    async def _entity_state_notify(self, newstate) -> None:
        if newstate is None:
            _LOGGER.debug("Received None as newstate in _entity_state_notify")
            return
        _LOGGER.debug(f"扫地机器人新状态: {newstate.state, newstate.entity_id}")
        self._cleanerStatus = self._get_cleaner_status(newstate)
        await self._intre_ss.report_prop_async(
            self._product.productKey,
            self._product.deviceId,
            self._module_key,
            'cleanerStatus',
            self._cleanerStatus
        )
        _LOGGER.debug(f"VACUUM state: {self._cleanerStatus}")
        return

    @final
    def get_tls_log_json(self, serverkey: str) -> list:
        """生成TSL日志上报的JSON数据"""
        timestamp_ms = str(int(time.time() * 1000))
        return [{
            "moduleKey": self._module_key,
            "service": {
                "serviceKey": serverkey,
                "serviceOutputValue": "",
                "timestamp": timestamp_ms
            }
        }]

    def service_call_req(self, service_call_data: dict) -> None:
        _LOGGER.debug(f"service_call_data: {service_call_data}")
        
        ha_service_data = {
            'entity_id': self._entity_id
        }
        
        try:
            # 提取msgId（用于服务响应）和核心数据
            msg_id = service_call_data.get('msgId')
            data = service_call_data.get('data', {})
            module = data.get('module', {})
            service = module.get('service', {})
            service_key = service.get('serviceKey')
            input_json_str = service.get('serviceInputValue')
            
            if not service_key:
                _LOGGER.warning("Missing serviceKey in service call data")
                return
            
            # 解析参数（若有）
            input_params = {}
            if input_json_str:
                try:
                    input_params = json.loads(input_json_str)
                except json.JSONDecodeError as e:
                    _LOGGER.error(f"Failed to parse serviceInputValue: {e}, input_str: {input_json_str}")
                    self._send_service_reply(msg_id, service_key, '0')
                    return
            
            target_service = None
            
            # ========== 修正核心：按设备定义映射status值 ==========
            if service_key == 'toggleCleanerWork':
                status = input_params.get('status')
                if status is None:
                    _LOGGER.warning(f"toggleCleanerWork requires 'status' parameter, got: {input_params}")
                    self._send_service_reply(msg_id, service_key, '0')
                    return
                
                # 设备定义：0=开始清洁，1=暂停清洁
                if status == 0:
                    target_service = 'start'  # HA启动清扫
                    _LOGGER.debug(f"设备指令：开始清洁 → 调用HA服务: vacuum.start")
                elif status == 1:
                    target_service = 'stop'  # HA暂停清扫
                    _LOGGER.debug(f"设备指令：暂停清洁 → 调用HA服务: vacuum.stop")
                else:
                    _LOGGER.warning(f"Invalid status value: {status} for toggleCleanerWork")
                    self._send_service_reply(msg_id, service_key, '0')
                    return
                
                # 执行HA服务调用
                self._intre_ss.call_ha_service('vacuum', target_service, ha_service_data)
            
            elif service_key == 'recharge':
                # 保持原有回充逻辑不变
                if not input_params:
                    target_service = 'return_to_base'
                    _LOGGER.debug(f"Call HA vacuum service (no params): {target_service}, data: {ha_service_data}")
                    self._intre_ss.call_ha_service('vacuum', target_service, ha_service_data)
                else:
                    status = input_params.get('status')
                    target_service = 'return_to_base' if status == 1 else 'stop'
                    _LOGGER.debug(f"Call HA vacuum service (with status): {target_service}, data: {ha_service_data}")
                    self._intre_ss.call_ha_service('vacuum', target_service, ha_service_data)
            
            else:
                _LOGGER.warning(f"Unsupported serviceKey: {service_key}")
                self._send_service_reply(msg_id, service_key, '0')
                return
            
            # TSL日志上报 + 服务响应
            try:
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
                        '1'  # 执行成功
                    )
                ]
                
                if hasattr(self._intre_ss, '_hass') and self._intre_ss._hass:
                    loop = self._intre_ss._hass.loop
                    for coro in coroutines:
                        loop.create_task(coro)
                else:
                    _LOGGER.warning("HASS loop not found, skip async report/reply")
                    
            except Exception as e:
                _LOGGER.error(f"Failed to send TSL log or service reply: {str(e)}", exc_info=True)
                self._send_service_reply(msg_id, service_key, '0')
        
        except HomeAssistantError as e:
            _LOGGER.error(f"HA service call failed: {str(e)}", exc_info=True)
            msg_id = service_call_data.get('msgId')
            self._send_service_reply(msg_id, service_key, '0')
        except Exception as e:
            _LOGGER.error(f"Error processing service call: {e}", exc_info=True)
            msg_id = service_call_data.get('msgId')
            self._send_service_reply(msg_id, service_key, '0')

    def _send_service_reply(self, msg_id, service_key, result_code):
        """兜底的同步服务回复方法"""
        if not msg_id or not service_key:
            return
        try:
            if hasattr(self._intre_ss, 'service_set_reply'):
                self._intre_ss.service_set_reply(
                    self._product.productKey,
                    self._product.deviceId,
                    self._module_key,
                    service_key,
                    msg_id,
                    result_code
                )
            else:
                _LOGGER.debug(f"Service reply (sync): msgId={msg_id}, service={service_key}, result={result_code}")
        except Exception as e:
            _LOGGER.error(f"Sync service reply failed: {str(e)}", exc_info=True)

    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        _LOGGER.debug(f"开始处理批量服务属性请求: {batch_service_prop_data}")
        data = {'entity_id': self._entity_id}
        _LOGGER.debug(f"使用实体ID处理: {self._entity_id}")
        
        # 从数据中提取deviceModuleList（服务列表嵌套在这里）
        device_modules = batch_service_prop_data.get('data', {}).get('deviceModuleList', [])
        _LOGGER.debug(f"发现{len(device_modules)}个设备模块需要处理")
        
        for module in device_modules:
            # 处理属性列表
            property_list = module.get('propertyList', [])
            _LOGGER.debug(f"模块{module.get('moduleKey')}发现{len(property_list)}个属性需要处理")
            for prop in property_list:
                prop_key = prop.get('propertyKey')
                prop_value = prop.get('propertyValue')
                _LOGGER.debug(f"处理属性 - Key: {prop_key}, Value: {prop_value}")
                
                if prop_key == 'cleanerStatus':
                    _LOGGER.debug(f"处理cleanerStatus属性，值为: {prop_value}")
                    if prop_value == '1':
                        _LOGGER.debug("发送启动清洁命令到HA")
                        self._intre_ss.call_ha_service('vacuum', 'start', data)
                    elif prop_value == '2':
                        _LOGGER.debug("发送停止清洁命令到HA")
                        self._intre_ss.call_ha_service('vacuum', 'stop', data)
                    elif prop_value == '0':
                        _LOGGER.debug("发送返回命令到HA")
                        self._intre_ss.call_ha_service('vacuum', 'return_to_base', data)
                    else:
                        _LOGGER.warning(f"收到未知cleanerStatus值: {prop_value}")
            
            # 处理服务列表
            service_list = module.get('serviceList', [])
            _LOGGER.debug(f"模块{module.get('moduleKey')}发现{len(service_list)}个服务需要处理")
            for service in service_list:
                input_value = service.get('serviceInputValue')
                input_str = input_value if isinstance(input_value, str) else '{}'
                service_key = service.get('serviceKey')
                msg_id = service.get('msgId') or batch_service_prop_data.get('msgId')
                _LOGGER.debug(f"处理服务 - Key: {service_key}, MsgId: {msg_id}, 输入参数: {input_str}")
                
                if not service_key:
                    _LOGGER.warning("服务数据缺少serviceKey，跳过处理")
                    continue
                
                try:
                    if service_key == 'toggleCleanerWork':
                        _LOGGER.debug("处理toggleCleanerWork服务")
                        input_data = json.loads(input_str)
                        status = input_data.get('status')
                        _LOGGER.debug(f"toggleCleanerWork状态参数: {status}")
                        
                        if status is not None:
                            target_service = 'start' if status == 0 else 'stop'
                            _LOGGER.debug(f"调用HA服务: vacuum.{target_service}")
                            self._intre_ss.call_ha_service('vacuum', target_service, data)
                        else:
                            _LOGGER.warning("toggleCleanerWork缺少status参数")
                            if msg_id:
                                self._send_service_reply(msg_id, service_key, '0')
                    
                    elif service_key == 'recharge':
                        _LOGGER.debug("处理recharge服务")
                        input_data = json.loads(input_str)
                        _LOGGER.debug(f"recharge输入参数: {input_data}")
                        
                        target_service = 'return_to_base' if (not input_data or input_data.get('status') == 1) else 'stop'
                        _LOGGER.debug(f"调用HA服务: vacuum.{target_service}")
                        self._intre_ss.call_ha_service('vacuum', target_service, data)
                    
                    else:
                        _LOGGER.warning(f"不支持的服务Key: {service_key}")
                        if msg_id:
                            self._send_service_reply(msg_id, service_key, '0')
                        continue
                    
                    # 发送服务响应和日志上报
                    _LOGGER.debug(f"准备发送服务响应 - MsgId: {msg_id}, 服务Key: {service_key}")
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
                            '1'  # 执行成功
                        )
                    ]
                    
                    if hasattr(self._intre_ss, '_hass') and self._intre_ss._hass:
                        loop = self._intre_ss._hass.loop
                        for coro in coroutines:
                            loop.create_task(coro)
                        _LOGGER.debug("异步任务已提交到HASS事件循环")
                    else:
                        _LOGGER.warning("HASS事件循环未找到，跳过异步上报和响应")
                    
                except json.JSONDecodeError as e:
                    _LOGGER.error(f"服务输入解析失败: {e}, 输入内容: {input_str}", exc_info=True)
                    if msg_id:
                        self._send_service_reply(msg_id, service_key, '0')
                except Exception as e:
                    _LOGGER.error(f"处理服务时发生错误: {e}", exc_info=True)
                    if msg_id:
                        self._send_service_reply(msg_id, service_key, '0')
        
        _LOGGER.debug("批量服务属性请求处理完成")

    def attr_change_req(self, properlist: list, msg_id: str) -> None:
        _LOGGER.debug(f"properlist: {properlist}")
        data = {
            'entity_id': self._entity_id
        }
        
        for prop in properlist:
            if prop['propertyKey'] == 'cleanerStatus':
                if prop['propertyValue'] == '1':
                    self._intre_ss.call_ha_service('vacuum', 'start', data)
                elif prop['propertyValue'] == '2':
                    self._intre_ss.call_ha_service('vacuum', 'stop', data)
                elif prop['propertyValue'] == '0':
                    self._intre_ss.call_ha_service('vacuum', 'return_to_base', data)
        return

    def _get_cleaner_status(self, ha_state) -> str:
        """将Home Assistant状态转换为自定义状态码"""
        if not ha_state:
            return "0"  # 默认空闲
        
        state = ha_state.state
        # 根据Home Assistant真空吸尘器的常见状态映射
        if state in ['cleaning', 'running']:
            return "1"  # 正在清洁
        elif state in ['paused']:
            return "2"  # 暂停清洁
        else:  # idle, docked等状态都视为空闲
            return "0"  # 空闲


async def test_fun() -> bool:
    _LOGGER.debug("test-vacuum")
    return True