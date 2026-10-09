"""Platform for light integration.
from __future__ import annotations
# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_EFFECT,
    LightEntity,
    LightEntityFeature,
    ColorMode
)
from homeassistant.util.color import (
    value_to_brightness,
    brightness_to_value
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
"""
import asyncio
import base64
import json
import logging
import re
import time
import hmac
import hashlib
import math
import paho.mqtt.client as mqtt
from .switch import IntreSwitch
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
from homeassistant.components.light import ColorMode  
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    intre_ss:IntreManagementEngine =hass.data[DOMAIN]['intre_ss'][config_entry.entry_id]
    _hadevices = hass.data[DOMAIN]['config_data']['_hadevices']

    # 遍历设备列表
    for hadevice in _hadevices:
        product = hadevice['product']
        entitys = hadevice['entitys']
        for entity in entitys:
            entity_entry = entity.get('entry')
            entity_state = entity.get('state')
            entity_id = entity_entry.entity_id
            
            # 仅处理light类型的实体
            if entity_id.split(".")[0] == 'light':
                _LOGGER.debug(f"entity_id: {entity_id}")
                _LOGGER.debug(f"entity_state: {entity_state}")
                
                # 获取HA中的实体状态
                state = hass.states.get(entity_id)
                _LOGGER.debug(f"Light state for {entity_id}: {state}")
                
                if state is not None:
                    attributes = state.attributes
                    # 获取支持的颜色模式和当前颜色模式
                    supported_color_modes = attributes.get('supported_color_modes', [])
                    current_color_mode = attributes.get('color_mode')
                    
                    # ========== 修复：兼容关闭状态的双色温灯判断 ==========
                    supported_modes_str = []
                    for mode in supported_color_modes:
                        if isinstance(mode, ColorMode):
                            supported_modes_str.append(mode.value)
                        else:
                            supported_modes_str.append(str(mode))
                    
                    # 判断是否为RGBW灯（rgbw模式，HA中为单一模式，如KNX RGBW灯带）
                    is_rgbw_mode = (
                        len(supported_modes_str) == 1 and
                        'rgbw' in supported_modes_str
                    )
                    # 判断是否为RGB+CW灯（支持色温 + 任意色彩模式：hs/rgb/xy/rgbw/rgbww）
                    has_color_mode = any(m in supported_modes_str for m in ['hs', 'rgb', 'xy', 'rgbw', 'rgbww'])
                    is_rgbcw = (
                        'color_temp' in supported_modes_str and
                        has_color_mode
                    )
                    # 判断是否为RGB+W灯（不支持color_temp）
                    is_rgbw = (
                        len(supported_modes_str) == 2 and
                        'color_temp' not in supported_modes_str and
                        ('hs' in supported_modes_str or 'rgb' in supported_modes_str)
                    )
                    # 判断是否为双色温灯（只有color_temp，没有色彩模式）
                    # 注意：Hue等支持XY色彩空间的灯不应被误判为双色温灯
                    is_dual_temp = (
                        'color_temp' in supported_modes_str and
                        'hs' not in supported_modes_str and
                        'rgb' not in supported_modes_str and
                        'xy' not in supported_modes_str and
                        'rgbw' not in supported_modes_str and
                        'rgbww' not in supported_modes_str
                    )
                    # 射灯（onoff开关型灯，无亮度无色温）
                    is_spotlight = (
                        len(supported_modes_str) == 1 and
                        'onoff' in supported_modes_str
                    )
                    # RGB灯（仅rgb模式，无亮度无色温）
                    is_rgb_only = (
                        len(supported_modes_str) == 1 and
                        'rgb' in supported_modes_str
                    )
                    # 单色温灯（仅brightness模式，有亮度无色温）
                    is_single_temp = (
                        len(supported_modes_str) == 1 and
                        'color_temp' not in supported_modes_str and
                        'brightness' in supported_modes_str
                    )
                    
                    if is_rgbcw:
                        _LOGGER.debug(f"Device {entity_id} is an RGB+CW light")
                        module_info = {
                            'moduleCode': 'RGBCWLight',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = RGBCWLight(
                            hass=hass,
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info,
                            entity_entry=entity_entry
                        )
                        product.add_modules(light)
                    elif is_rgbw_mode:
                        _LOGGER.debug(f"Device {entity_id} is an RGBW light (rgbw mode)")
                        module_info = {
                            'moduleCode': 'RGBWLight',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = RGBWLight(
                            hass=hass,
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info,
                            entity_entry=entity_entry
                        )
                        product.add_modules(light)
                    elif is_rgbw:
                        _LOGGER.debug(f"Device {entity_id} is an RGBW light")
                        module_info = {
                            'moduleCode': 'RGBWLight',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = RGBWLight(
                            hass=hass,
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info,
                            entity_entry=entity_entry
                        )
                        product.add_modules(light)
                    elif is_dual_temp:
                        _LOGGER.debug(f"Device {entity_id} is a dual color temperature light (strict match, current mode: {current_color_mode})")
                        module_info = {
                            'moduleCode': 'dualColorTemperatureLight',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = RGBCWLight(
                            hass=hass,
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info,
                            entity_entry=entity_entry
                        )
                        product.add_modules(light)
                    elif is_spotlight:
                        _LOGGER.debug(f"Device {entity_id} is a spotlight (onoff light)")
                        module_info = {
                            'moduleCode': 'switch',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = IntreSwitch(
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info
                        )
                        product.add_modules(light)
                    elif is_rgb_only:
                        _LOGGER.debug(f"Device {entity_id} is an RGB only light")
                        module_info = {
                            'moduleCode': 'RGBWLight',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = RGBWLight(
                            hass=hass,
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info,
                            entity_entry=entity_entry
                        )
                        product.add_modules(light)
                    elif is_single_temp:
                        _LOGGER.debug(f"Device {entity_id} is a single color temperature light")
                        module_info = {
                            'moduleCode': 'singleColorTemperatureLight',
                            'moduleKey': entity_entry.entity_id,
                            'moduleName': entity_entry.name,
                            'entity_id': entity_entry.entity_id
                        }
                        light = SingleColorTemperatureLight(
                            hass=hass,
                            intre_ss=intre_ss,
                            product=product,
                            module_info=module_info,
                            entity_entry=entity_entry
                        )
                        product.add_modules(light)
                    else:
                        _LOGGER.debug(
                            f"Device {entity_id} unsupported light type. "
                            f"Supported modes: {supported_modes_str}"
                        )

        # 继续处理下一个实体
        continue
        return


class RGBWLight(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine
    _hass:HomeAssistant
    def __init__(self,hass,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict,entity_entry) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing RGBWLight...')
        self._hass=hass
        self._intre_ss=intre_ss
        self._product=product
        self.state=None
        self._onOff=StateUtils.util_get_state_onoff(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._brightness=StateUtils.util_get_state_brightness(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._rgb=StateUtils.util_get_state_rgb_color(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._entity_entry=entity_entry
        self.module_info = {}
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
        self._product.sub_service_call(self._module_key,self.service_call_req)
        self._product.sub_bacth_service_prop_call(self._module_key,self.batch_service_prop_call_req)
        _LOGGER.debug('onOff:')
        _LOGGER.debug(self._onOff)
        _LOGGER.debug(self._brightness)
        _LOGGER.debug(self._rgb)
    
    @final 
    def get_module_prop_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey":self._module_key,
            "propertyList":[
                {
                    'propertyKey':'onOff',
                    'propertyValue':str(int(self._onOff)),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'brightness',
                    'propertyValue':str(self._brightness),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'hsColor',
                    'propertyValue':json.dumps(self._rgb if self._rgb is not None else [0, 0]),
                    'timestamp': timestamp_ms
                }
            ]
        }
    
    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "templateModuleKey": "RGBWLight_1",
            "instanceModuleKey": self._module_key,
            "instanceModuleName": self._entity_entry.name if self._entity_entry.name else self._entity_entry.entity_id,
            "propertyList":[
                {
                    'propertyKey':'onOff',
                    'propertyValue':str(int(self._onOff)),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'brightness',
                    'propertyValue':str(self._brightness),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'hsColor',
                    'propertyValue':json.dumps(self._rgb if self._rgb is not None else [0, 0]),
                    'timestamp': timestamp_ms
                }
            ]
        }
    
    async def _entity_state_notify(self,newstate) -> None:
        if newstate is None:
            return
        _LOGGER.debug(newstate.state)
        _LOGGER.debug(newstate.attributes)
        current_on_off = StateUtils.util_get_state_onoff(newstate)
        if current_on_off is not None:
            self._onOff = current_on_off
            await self._intre_ss.report_prop_async(
                self._product.productKey,
                self._product.deviceId,
                self._module_key,
                'onOff',
                str(int(current_on_off))
            )
        if 'brightness' in newstate.attributes:
            brightness = newstate.attributes['brightness']
            if isinstance(brightness, (int, float)):
                brightness_normalized = round(brightness / 2.55)
                await self._intre_ss.report_prop_async(
                    self._product.productKey,
                    self._product.deviceId,
                    self._module_key,
                    'brightness',
                    brightness_normalized
                )
        if 'rgb_color' in newstate.attributes:
            rgb_color = newstate.attributes['rgb_color']
            if rgb_color is not None:
                await self._intre_ss.report_prop_async(
                    self._product.productKey,
                    self._product.deviceId,
                    self._module_key,
                    'hsColor',
                    json.dumps(rgb_color)
                )
    
    def service_call_req(self,service_call_data:dict) ->None:
        _LOGGER.debug(service_call_data)
        data = {'entity_id': self._entity_id}
        try:
            module = service_call_data.get('data', {}).get('module', {})
            if not module:
                _LOGGER.warning("未从service_call_data中获取到有效的module信息")
                return
            service_key = module.get('service', {}).get('serviceKey')
            service_input_value = module.get('service', {}).get('serviceInputValue')
            
            if service_key == 'toggleOnOff':
                service='turn_on'
                if self._onOff==True:
                    service='turn_off'
                self._intre_ss.call_ha_service('light',service,data)
                return
            
            if service_input_value is None:
                return
            
            if isinstance(service_input_value, bytes):
                service_input_value = service_input_value.decode('utf-8')
            
            input_data = json.loads(service_input_value)
            
            if 'onOff' in input_data:
                on_off_status = input_data['onOff']
                if on_off_status == 1:
                    service = 'turn_on'
                elif on_off_status == 0:
                    service = 'turn_off'
                else:
                    return
                self._intre_ss.call_ha_service('light', service, data)
            
            if 'brightness' in input_data:
                brightness_data = input_data['brightness']
                if isinstance(brightness_data, (int, float)):
                    data['brightness'] = math.ceil(brightness_data * 2.55)
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
            
            if 'hue' in input_data and 'saturation' in input_data:
                hs_color = (input_data['hue'], input_data['saturation'])
                data['hs_color'] = hs_color
                self._intre_ss.call_ha_service('light', 'turn_on', data)
            
            if 'rgbColor' in input_data:
                rgb_val = input_data['rgbColor']
                if isinstance(rgb_val, list) and len(rgb_val) == 3:
                    data['rgb_color'] = rgb_val
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
            
            if 'rgb' in input_data:
                rgb_obj = input_data['rgb']
                if isinstance(rgb_obj, dict):
                    r = int(rgb_obj.get('red', 0))
                    g = int(rgb_obj.get('green', 0))
                    b = int(rgb_obj.get('blue', 0))
                    data['rgb_color'] = [r, g, b]
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
                    
        except Exception as e:
            _LOGGER.error(f"RGBWLight service_call_req error: {e}", exc_info=True)
    
    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        _LOGGER.debug(f"RGBWLight batch_service_prop_data: {batch_service_prop_data}")
        data = {'entity_id': self._entity_id}
        try:
            device_modules = batch_service_prop_data.get('data', {}).get('deviceModuleList', [])
            for device_module in device_modules:
                service_list = device_module.get('serviceList', [])
                for service_item in service_list:
                    service_key = service_item.get('serviceKey', '')
                    if service_key == 'toggleOnOff':
                        service='turn_on'
                        if self._onOff==True:
                            service='turn_off'
                        self._intre_ss.call_ha_service('light',service,data)
                        continue
                    
                    service_input_value = service_item.get('serviceInputValue', '')
                    if not service_input_value:
                        continue
                    if isinstance(service_input_value, bytes):
                        service_input_value = service_input_value.decode('utf-8')
                    input_values = json.loads(service_input_value)
                    
                    if 'onOff' in input_values:
                        on_off_val = input_values['onOff']
                        if not on_off_val:
                            service='turn_off'
                        else:
                            br = input_values.get('brightness')
                            if isinstance(br, (int, float)) and br == 0:
                                service='turn_off'
                                _LOGGER.debug(f"RGBW batch onOff=1,brightness=0 视为关灯")
                            else:
                                service='turn_on'
                    else:
                        service='turn_on'
                    
                    if 'brightness' in input_values:
                        br = input_values['brightness']
                        if isinstance(br, (int, float)):
                            data['brightness'] = math.ceil(br * 2.55)
                    
                    if 'hue' in input_values and 'saturation' in input_values:
                        data['hs_color'] = (input_values['hue'], input_values['saturation'])
                    
                    if 'rgbColor' in input_values:
                        rgb = input_values['rgbColor']
                        if isinstance(rgb, list) and len(rgb) == 3:
                            data['rgb_color'] = rgb
                    
                    if 'rgb' in input_values:
                        rgb_obj = input_values['rgb']
                        if isinstance(rgb_obj, dict):
                            r = int(rgb_obj.get('red', 0))
                            g = int(rgb_obj.get('green', 0))
                            b = int(rgb_obj.get('blue', 0))
                            data['rgb_color'] = [r, g, b]
                    
                    if data and (len(data) > 1 or service in ('turn_on', 'turn_off')):  # has keys beyond entity_id
                        self._intre_ss.call_ha_service('light', service, data)
        except Exception as e:
            _LOGGER.error(f"RGBWLight batch_service error: {e}", exc_info=True)
    
    def attr_change_req(self, properlist: list, msg_id: str) -> None:
        _LOGGER.debug(f"RGBWLight properlist: {properlist}")
        data = {'entity_id': self._entity_id}
        try:
            for prop in properlist:
                prop_key = prop.get('propertyKey')
                prop_value = prop.get('propertyValue')
                if not prop_key or prop_value is None:
                    continue
                if prop_key == 'onOff':
                    service = 'turn_on' if prop_value != '0' else 'turn_off'
                    self._intre_ss.call_ha_service('light', service, data)
                elif prop_key == 'brightness':
                    try:
                        br = int(prop_value)
                        data['brightness'] = int((br * 255) / 100)
                        self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError):
                        pass
                elif prop_key == 'hsColor':
                    try:
                        hs = json.loads(prop_value)
                        if isinstance(hs, (list, tuple)) and len(hs) >= 3:
                            data['rgb_color'] = [int(hs[0]), int(hs[1]), int(hs[2])]
                            self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
                elif prop_key == 'rgb':
                    try:
                        if isinstance(prop_value, str):
                            rgb_obj = json.loads(prop_value)
                        else:
                            rgb_obj = prop_value
                        if isinstance(rgb_obj, dict):
                            r = int(rgb_obj.get('red', 0))
                            g = int(rgb_obj.get('green', 0))
                            b = int(rgb_obj.get('blue', 0))
                            data['rgb_color'] = [r, g, b]
                            self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
        except Exception as e:
            _LOGGER.error(f"RGBWLight attr_change error: {e}", exc_info=True)


class RGBCWLight(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine
    _hass:HomeAssistant
    _state_cache: dict
    def __init__(self,hass,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict,entity_entry) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing RGBCWLight...')
        self._hass=hass
        self._intre_ss=intre_ss
        self._product=product
        self.state=None
        self._onOff=StateUtils.util_get_state_onoff(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._brightness=StateUtils.util_get_state_brightness(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._colorTemperature=StateUtils.util_get_state_colorTemperature(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._rgb=StateUtils.util_get_state_rgb_color(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._min_color_temp_kelvin=StateUtils.util_get_min_color_temperature(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._max_color_temp_kelvin=StateUtils.util_get_max_color_temperature(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._entity_entry=entity_entry
        self.module_info={}
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
        self._product.sub_service_call(self._module_key,self.service_call_req)
        self._product.sub_bacth_service_prop_call(self._module_key,self.batch_service_prop_call_req)
        _LOGGER.debug('onOff:')
        _LOGGER.debug(self._onOff)
        _LOGGER.debug(self._brightness)
        _LOGGER.debug(self._colorTemperature)
        _LOGGER.debug(self._rgb)
    
    @final
    def get_module_prop_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        result = {
            "moduleKey":self._module_key,
            "propertyList":[
                {
                    'propertyKey':'onOff',
                    'propertyValue':str(int(self._onOff)),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'brightness',
                    'propertyValue':str(self._brightness),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'colorTemperature',
                    'propertyValue':str(self._colorTemperature),
                    'timestamp': timestamp_ms
                }
            ]
        }
        # 双色温灯不包含hsColor属性
        if self._module_code != "dualColorTemperatureLight":
            result["propertyList"].append({
                'propertyKey':'hsColor',
                'propertyValue':json.dumps(self._rgb if self._rgb is not None else [0, 0]),
                'timestamp': timestamp_ms
            })
        return result
    
    @final
    def get_data_define_json(self) -> list:
        timestamp_ms = str(int(time.time() * 1000))
        return [{
            "moduleKey": self._module_key,
            "propertyKey": "colorTemperature",
            "dataDefineValue": f"{{\"dataType\":\"int\",\"specs\":{{\"min\":\"{self._min_color_temp_kelvin}\",\"max\":\"{self._max_color_temp_kelvin}\",\"step\":\"100\",\"unit\":\"K\",\"unitName\":\"开尔文\"}},\"required\":1}}",
            "timestamp": timestamp_ms
        }]
    
    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        _LOGGER.debug('get_module_json')
        s = self._module_key
        if s.startswith("light."):
            instance_module_name = s.split("light.")[1]
        else:
            instance_module_name = "RGB+CW"
        # 根据_module_code选择正确的模板：双色温灯用dualColorTemperatureLight_2，RGBCW用RGBCWLight_1
        template_key = "dualColorTemperatureLight_2" if self._module_code == "dualColorTemperatureLight" else "RGBCWLight_1"
        result = {
            "templateModuleKey": template_key,
            "instanceModuleKey": self._module_key,
            "instanceModuleName": instance_module_name,
            "propertyList":[
                {
                    'propertyKey':'onOff',
                    'propertyValue':str(int(self._onOff)),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'brightness',
                    'propertyValue':str(self._brightness),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'colorTemperature',
                    'propertyValue':str(self._colorTemperature),
                    'timestamp': timestamp_ms
                }
            ]
        }
        # 双色温灯不包含hsColor属性
        if self._module_code != "dualColorTemperatureLight":
            result["propertyList"].append({
                'propertyKey':'hsColor',
                'propertyValue':json.dumps(self._rgb if self._rgb is not None else [0, 0]),
                'timestamp': timestamp_ms
            })
        # 上报色温范围定义到云端（仅双色温灯需要）
        if self._module_code == "dualColorTemperatureLight":
            product_key = self._product.productKey
            device_id = self._product.deviceId
            if isinstance(product_key, str) and product_key and isinstance(device_id, str) and device_id:
                self._report_data_define(product_key, device_id)
        return result

    def _report_data_define(self, product_key: str, device_id: str) -> None:
        """上报色温范围定义到云端"""
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                run_manually = True
            else:
                run_manually = False

            report_task = self._intre_ss.data_define_report_async(
                product_key,
                device_id,
                self.get_data_define_json()
            )

            if loop.is_running():
                loop.create_task(report_task)
                _LOGGER.debug(f"Scheduled data define report for {product_key} (device {device_id})")
            else:
                loop.run_until_complete(report_task)
                _LOGGER.debug(f"Completed data define report for {product_key} (device {device_id})")

        except Exception as e:
            _LOGGER.error(f"Failed to report data define: {str(e)}", exc_info=True)
        finally:
            if 'run_manually' in locals() and run_manually:
                loop.close()

    async def _entity_state_notify(self,newstate)->None:
        if newstate is None:
            return
        if not self._product.productKey or not self._product.deviceId:
            _LOGGER.warning(f"Skip report: productKey={self._product.productKey}, deviceId={self._product.deviceId}")
            return
        if not hasattr(self, '_state_cache'):
            self._state_cache = {'onOff': None, 'brightness': None, 'colorTemperature': None}
        if self._module_code != "dualColorTemperatureLight":
            self._state_cache['hsColor'] = None
        
        attributes = newstate.attributes
        _LOGGER.debug(f"RGBCW state: {newstate.state}, brightness: {attributes.get('brightness')}, color_temp_kelvin: {attributes.get('color_temp_kelvin')}, color_temp: {attributes.get('color_temp')}, rgb_color: {attributes.get('rgb_color')}")
        
        # onOff
        current_on_off = StateUtils.util_get_state_onoff(newstate)
        self._onOff = current_on_off
        if current_on_off is not None:
            on_off_str = str(int(current_on_off))
            if on_off_str != self._state_cache.get('onOff'):
                await self._intre_ss.report_prop_async(self._product.productKey, self._product.deviceId, self._module_key, 'onOff', on_off_str)
                self._state_cache['onOff'] = on_off_str
        
        # brightness
        if 'brightness' in attributes:
            br_val = attributes['brightness']
            if isinstance(br_val, (int, float)):
                br_norm = round(br_val / 2.55)
                if br_norm != self._state_cache.get('brightness'):
                    await self._intre_ss.report_prop_async(self._product.productKey, self._product.deviceId, self._module_key, 'brightness', br_norm)
                    self._state_cache['brightness'] = br_norm
        
        # colorTemperature - 优先color_temp_kelvin
        ct_k = attributes.get('color_temp_kelvin')
        if ct_k is not None:
            try:
                ct_norm = int(float(ct_k) / 50) * 50
                if ct_norm != self._state_cache.get('colorTemperature'):
                    await self._intre_ss.report_prop_async(self._product.productKey, self._product.deviceId, self._module_key, 'colorTemperature', ct_norm)
                    self._state_cache['colorTemperature'] = ct_norm
            except (ValueError, TypeError):
                pass
        else:
            # 兼容旧版mired
            ct = attributes.get('color_temp')
            if ct is not None:
                try:
                    ct_norm = int((int(10**6 / float(ct))) / 50) * 50
                    if ct_norm != self._state_cache.get('colorTemperature'):
                        await self._intre_ss.report_prop_async(self._product.productKey, self._product.deviceId, self._module_key, 'colorTemperature', ct_norm)
                        self._state_cache['colorTemperature'] = ct_norm
                except (ValueError, TypeError, ZeroDivisionError):
                    pass
        
        # rgb_color - 仅非双色温灯上报
        if self._module_code != "dualColorTemperatureLight" and 'rgb_color' in attributes:
            rgb_color = attributes['rgb_color']
            if rgb_color is not None:
                await self._intre_ss.report_prop_async(self._product.productKey, self._product.deviceId, self._module_key, 'hsColor', json.dumps(rgb_color))
    
    def service_call_req(self, service_call_data: dict) -> None:
        data = {'entity_id': self._entity_id}
        _LOGGER.debug(f"RGBCWLight service_call_data: {service_call_data}")
        try:
            module = service_call_data.get('data', {}).get('module', {})
            if not module:
                _LOGGER.warning("未从service_call_data中获取到有效的module信息")
                return
            service_key = module.get('service', {}).get('serviceKey')
            service_input_value = module.get('service', {}).get('serviceInputValue')
            
            # 时间戳缓存
            if service_key in ('setBrightnessWithOn', 'toggleOnOff', 'setColorTemperatureWithOn'):
                current_ts = service_call_data.get('timestamp')
                if current_ts:
                    try:
                        current_ts = int(current_ts)
                        cache_key = '_last_ts_' + service_key
                        last_ts = getattr(self, cache_key, 0)
                        if current_ts <= last_ts:
                            _LOGGER.debug(f"RGBCW discard expired {service_key} timestamp={current_ts}")
                            return
                        setattr(self, cache_key, current_ts)
                    except (ValueError, TypeError):
                        pass
            
            if service_key == 'toggleOnOff':
                service='turn_on'
                if self._onOff==True:
                    service='turn_off'
                self._intre_ss.call_ha_service('light',service,data)
                return
            
            if service_input_value is None:
                return
            
            if isinstance(service_input_value, bytes):
                service_input_value = service_input_value.decode('utf-8')
            
            input_data = json.loads(service_input_value)
            _LOGGER.debug(f"RGBCW input_data: {input_data}")
            
            if 'onOff' in input_data:
                on_off_status = input_data['onOff']
                if on_off_status == 1:
                    service='turn_on'
                elif on_off_status == 0:
                    service='turn_off'
                else:
                    return
                self._intre_ss.call_ha_service('light', service, data)
            
            if 'brightness' in input_data:
                br = input_data['brightness']
                if isinstance(br, (int, float)):
                    data['brightness'] = math.ceil(br * 2.55)
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
            
            if 'colorTemperature' in input_data:
                ct_val = input_data['colorTemperature']
                if isinstance(ct_val, (int, float)) and self._min_color_temp_kelvin <= ct_val <= self._max_color_temp_kelvin:
                    data['color_temp_kelvin'] = ct_val
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
                    _LOGGER.debug(f"RGBCW 色温调节: {ct_val}K (color_temp_kelvin)")
                else:
                    _LOGGER.error(f"RGBCW 无效色温: {ct_val}, 范围{self._min_color_temp_kelvin}-{self._max_color_temp_kelvin}")
            
            if 'rgbColor' in input_data:
                rgb_val = input_data['rgbColor']
                if isinstance(rgb_val, list) and len(rgb_val) == 3:
                    data['rgb_color'] = [int(rgb_val[0]), int(rgb_val[1]), int(rgb_val[2])]
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
            
            if 'rgb' in input_data:
                rgb_obj = input_data['rgb']
                if isinstance(rgb_obj, dict):
                    r = int(rgb_obj.get('red', 0))
                    g = int(rgb_obj.get('green', 0))
                    b = int(rgb_obj.get('blue', 0))
                    data['rgb_color'] = [r, g, b]
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
            
            # daylight效果
            daylight_effect = input_data.get('daylightEffect')
            if daylight_effect is not None:
                self._handle_daylight_effect(daylight_effect, data)
        
        except Exception as e:
            _LOGGER.error(f"RGBCWLight service_call_req error: {e}", exc_info=True)
    
    def _handle_daylight_effect(self, effect, data):
        target_map = {1: (100, 6000), 2: (60, 4500), 3: (20, 3500)}
        if effect not in target_map:
            return
        target_brightness, target_temp = target_map[effect]
        final_temp = target_temp
        if effect == 1:
            final_temp = min(target_temp, self._max_color_temp_kelvin)
        elif effect == 3:
            final_temp = max(target_temp, self._min_color_temp_kelvin)
        elif effect == 2:
            if not (self._min_color_temp_kelvin <= target_temp <= self._max_color_temp_kelvin):
                data['brightness'] = math.ceil(target_brightness * 2.55)
                self._intre_ss.call_ha_service('light', 'turn_on', data)
                return
        data['brightness'] = math.ceil(target_brightness * 2.55)
        self._intre_ss.call_ha_service('light', 'turn_on', data)
        data['color_temp_kelvin'] = final_temp
        self._intre_ss.call_ha_service('light', 'turn_on', data)
    
    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        _LOGGER.debug(f"RGBCWLight batch_service_prop_data: {batch_service_prop_data}")
        data = {'entity_id': self._entity_id}
        try:
            device_modules = batch_service_prop_data.get('data', {}).get('deviceModuleList', [])
            for device_module in device_modules:
                service_list = device_module.get('serviceList', [])
                for service_item in service_list:
                    service_key = service_item.get('serviceKey', '')
                    if service_key == 'toggleOnOff':
                        service='turn_on'
                        if self._onOff==True:
                            service='turn_off'
                        self._intre_ss.call_ha_service('light',service,data)
                        continue
                    
                    if service_key != 'lightControlByBatchWithoutTransitionTime':
                        continue
                    
                    service_input_value = service_item.get('serviceInputValue', '')
                    if not service_input_value:
                        continue
                    if isinstance(service_input_value, bytes):
                        service_input_value = service_input_value.decode('utf-8')
                    input_values = json.loads(service_input_value)
                    _LOGGER.debug(f"RGBCW input_values: {input_values}")
                    
                    on_off_val = input_values.get('onOff')
                    if on_off_val is not None:
                        service='turn_on' if on_off_val else 'turn_off'
                    else:
                        service='turn_on'
                    
                    if 'brightness' in input_values:
                        br = input_values['brightness']
                        if isinstance(br, (int, float)):
                            data['brightness'] = math.ceil(br * 2.55)
                    
                    if 'colorTemperature' in input_values:
                        ct = input_values['colorTemperature']
                        if isinstance(ct, (int, float)) and self._min_color_temp_kelvin <= ct <= self._max_color_temp_kelvin:
                            data['color_temp_kelvin'] = ct
                            _LOGGER.debug(f"RGBCW batch 色温: {ct}K")
                    
                    if 'rgbColor' in input_values:
                        rgb = input_values['rgbColor']
                        if isinstance(rgb, list) and len(rgb) == 3:
                            data['rgb_color'] = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
                    
                    if 'rgb' in input_values:
                        rgb_obj = input_values['rgb']
                        if isinstance(rgb_obj, dict):
                            r = int(rgb_obj.get('red', 0))
                            g = int(rgb_obj.get('green', 0))
                            b = int(rgb_obj.get('blue', 0))
                            data['rgb_color'] = [r, g, b]
                    
                    if len(data) > 1 or service in ('turn_on', 'turn_off'):
                        self._intre_ss.call_ha_service('light', service, data)
        except Exception as e:
            _LOGGER.error(f"RGBCWLight batch_service error: {e}", exc_info=True)
    
    def attr_change_req(self, properlist: list, msg_id: str) -> None:
        _LOGGER.debug(f"RGBCWLight properlist: {properlist}")
        data = {'entity_id': self._entity_id}
        try:
            for prop in properlist:
                prop_key = prop.get('propertyKey')
                prop_value = prop.get('propertyValue')
                if not prop_key or prop_value is None:
                    continue
                if prop_key == 'onOff':
                    service = 'turn_on' if prop_value != '0' else 'turn_off'
                    self._intre_ss.call_ha_service('light', service, data)
                elif prop_key == 'brightness':
                    try:
                        br = int(prop_value)
                        data['brightness'] = int((br * 255) / 100)
                        self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError):
                        pass
                elif prop_key == 'colorTemperature':
                    try:
                        kelvin = int(prop_value)
                        if self._min_color_temp_kelvin <= kelvin <= self._max_color_temp_kelvin:
                            data['color_temp_kelvin'] = kelvin
                            self._intre_ss.call_ha_service('light', 'turn_on', data)
                            _LOGGER.debug(f"RGBCW attr 色温: {kelvin}K (color_temp_kelvin)")
                    except (ValueError, TypeError):
                        pass
                elif prop_key == 'hsColor':
                    try:
                        hs = json.loads(prop_value)
                        if isinstance(hs, (list, tuple)) and len(hs) >= 3:
                            data['rgb_color'] = [int(hs[0]), int(hs[1]), int(hs[2])]
                            self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
                elif prop_key == 'rgb':
                    try:
                        if isinstance(prop_value, str):
                            rgb_obj = json.loads(prop_value)
                        else:
                            rgb_obj = prop_value
                        if isinstance(rgb_obj, dict):
                            r = int(rgb_obj.get('red', 0))
                            g = int(rgb_obj.get('green', 0))
                            b = int(rgb_obj.get('blue', 0))
                            data['rgb_color'] = [r, g, b]
                            self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
        except Exception as e:
            _LOGGER.error(f"RGBCWLight attr_change error: {e}", exc_info=True)


class SingleColorTemperatureLight(IntreIoTModule):
    _product:IntreIoTProduct
    _intre_ss:IntreManagementEngine
    _hass:HomeAssistant
    def __init__(self,hass,intre_ss:IntreManagementEngine,product:IntreIoTProduct,module_info:dict,entity_entry) -> None:
        super().__init__(module_info=module_info)
        _LOGGER.debug('Initializing SingleColorTemperatureLight...')
        self._hass=hass
        self._intre_ss=intre_ss
        self._product=product
        self.state=None
        self._onOff=StateUtils.util_get_state_onoff(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._brightness=StateUtils.util_get_state_brightness(intre_ss._intre_ha.get_entity_state(self._entity_id))
        self._entity_entry=entity_entry
        self.module_info={}
        self._intre_ss.sub_entity(self._entity_id,self._entity_state_notify)
        self._product.sub_prop_set(self._module_key,self.attr_change_req)
        self._product.sub_service_call(self._module_key,self.service_call_req)
        self._product.sub_bacth_service_prop_call(self._module_key,self.batch_service_prop_call_req)
        _LOGGER.debug(self._onOff)
        _LOGGER.debug(self._brightness)
    
    @final
    def get_module_prop_json(self)->dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "moduleKey":self._module_key,
            "propertyList":[
                {
                    'propertyKey':'onOff',
                    'propertyValue':str(int(self._onOff)),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'brightness',
                    'propertyValue':str(self._brightness),
                    'timestamp': timestamp_ms
                }
            ]
        }
    
    @final
    def get_module_json(self) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        return {
            "templateModuleKey": "singleColorTemperatureLight_1",
            "instanceModuleKey": self._module_key,
            "instanceModuleName": self._entity_entry.name if self._entity_entry.name else self._entity_entry.entity_id,
            "propertyList":[
                {
                    'propertyKey':'onOff',
                    'propertyValue':str(int(self._onOff)),
                    'timestamp': timestamp_ms
                },
                {
                    'propertyKey':'brightness',
                    'propertyValue':str(self._brightness),
                    'timestamp': timestamp_ms
                }
            ]
        }
    
    async def _entity_state_notify(self,newstate) -> None:
        if newstate is None:
            return
        _LOGGER.debug(newstate.state)
        _LOGGER.debug(newstate.attributes)
        current_on_off = StateUtils.util_get_state_onoff(newstate)
        if current_on_off is not None:
            self._onOff = current_on_off
            await self._intre_ss.report_prop_async(
                self._product.productKey,
                self._product.deviceId,
                self._module_key,
                'onOff',
                str(int(current_on_off))
            )
        if 'brightness' in newstate.attributes:
            brightness = newstate.attributes['brightness']
            if isinstance(brightness, (int, float)):
                brightness_normalized = round(brightness / 2.55)
                await self._intre_ss.report_prop_async(
                    self._product.productKey,
                    self._product.deviceId,
                    self._module_key,
                    'brightness',
                    brightness_normalized
                )
    
    def service_call_req(self, service_call_data: dict) -> None:
        data = {'entity_id': self._entity_id}
        _LOGGER.debug(f"service_call_data: {service_call_data}")
        try:
            module = service_call_data.get('data', {}).get('module', {})
            if not module:
                _LOGGER.warning("未从service_call_data中获取到有效的module信息")
                return
            service_key = module.get('service', {}).get('serviceKey')
            service_input_value = module.get('service', {}).get('serviceInputValue')
            
            if service_key == 'toggleOnOff':
                service='turn_on'
                if self._onOff==True:
                    service='turn_off'
                self._intre_ss.call_ha_service('light',service,data)
                return
            
            if service_input_value is None:
                return
            
            if isinstance(service_input_value, bytes):
                service_input_value = service_input_value.decode('utf-8')
            
            input_data = json.loads(service_input_value)
            
            if 'onOff' in input_data:
                on_off_status = input_data['onOff']
                if on_off_status == 1:
                    service = 'turn_on'
                elif on_off_status == 0:
                    service = 'turn_off'
                else:
                    return
                self._intre_ss.call_ha_service('light', service, data)
            
            if 'brightness' in input_data:
                br = input_data['brightness']
                if isinstance(br, (int, float)):
                    data['brightness'] = math.ceil(br * 2.55)
                    self._intre_ss.call_ha_service('light', 'turn_on', data)
        
        except Exception as e:
            _LOGGER.error(f"SingleColorTemp service_call_req error: {e}", exc_info=True)
    
    def batch_service_prop_call_req(self, batch_service_prop_data: dict) -> None:
        _LOGGER.debug(f"SingleColorTemp batch: {batch_service_prop_data}")
        data = {'entity_id': self._entity_id}
        try:
            device_modules = batch_service_prop_data.get('data', {}).get('deviceModuleList', [])
            for device_module in device_modules:
                service_list = device_module.get('serviceList', [])
                for service_item in service_list:
                    service_key = service_item.get('serviceKey', '')
                    if service_key == 'toggleOnOff':
                        service='turn_on'
                        if self._onOff==True:
                            service='turn_off'
                        self._intre_ss.call_ha_service('light',service,data)
                        continue
                    
                    service_input_value = service_item.get('serviceInputValue', '')
                    if not service_input_value:
                        continue
                    if isinstance(service_input_value, bytes):
                        service_input_value = service_input_value.decode('utf-8')
                    input_values = json.loads(service_input_value)
                    
                    on_off_val = input_values.get('onOff')
                    if on_off_val is not None:
                        service='turn_on' if on_off_val else 'turn_off'
                    else:
                        service='turn_on'
                    
                    if 'brightness' in input_values:
                        br = input_values['brightness']
                        if isinstance(br, (int, float)):
                            data['brightness'] = math.ceil(br * 2.55)
                    
                    if len(data) > 1 or service in ('turn_on', 'turn_off'):
                        self._intre_ss.call_ha_service('light', service, data)
        except Exception as e:
            _LOGGER.error(f"SingleColorTemp batch error: {e}", exc_info=True)
    
    def attr_change_req(self, properlist: list, msg_id: str) -> None:
        _LOGGER.debug(f"SingleColorTemp properlist: {properlist}")
        data = {'entity_id': self._entity_id}
        try:
            for prop in properlist:
                prop_key = prop.get('propertyKey')
                prop_value = prop.get('propertyValue')
                if not prop_key or prop_value is None:
                    continue
                if prop_key == 'onOff':
                    service = 'turn_on' if prop_value != '0' else 'turn_off'
                    self._intre_ss.call_ha_service('light', service, data)
                elif prop_key == 'brightness':
                    try:
                        br = int(prop_value)
                        data['brightness'] = int((br * 255) / 100)
                        self._intre_ss.call_ha_service('light', 'turn_on', data)
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            _LOGGER.error(f"SingleColorTemp attr_change error: {e}", exc_info=True)


