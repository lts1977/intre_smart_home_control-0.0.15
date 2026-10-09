import asyncio
import base64
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries
from homeassistant.config_entries import ConfigEntry




_LOGGER = logging.getLogger(__name__)


class StateUtils:
    @staticmethod
    def util_get_state_onoff(state) -> bool:
        if state is not None:
            return state.state == 'on'
        return False

    @staticmethod
    def util_get_state_brightness(state) -> int:
        """安全获取亮度并转换为百分比"""
        # 先检查状态是否有效，以及是否存在 brightness 属性
        if not state or state.attributes.get('brightness') is None:
            return 0  # 或其他默认值，如 100
        
        # 确保获取到的值是数字类型
        brightness = state.attributes.get('brightness', 0)
        try:
            # 转换为 0-100 范围（HA 中亮度通常为 0-255）
            return round(brightness / 2.55)
        except (TypeError, ValueError):
            # 处理非数字的异常情况
            return False
    # 新增的 RGB 颜色获取方法
    @staticmethod
    def util_get_state_rgb_color(state) -> tuple | None:
        """
        安全获取 RGB 颜色值
        :param state: HA 设备状态对象
        :return: 标准化的 RGB 元组 (r, g, b)（0-255），无有效值时返回 None
        """
        # 1. 基础校验：状态无效直接返回 None
        if not state:
            _LOGGER.debug("获取RGB颜色：状态对象为空")
            return None
        
        # 2. 从属性中获取 rgb_color
        rgb_color = state.attributes.get('rgb_color')
        
        # 3. 处理 rgb_color 为 None 的情况（比如设备离线/关闭）
        if rgb_color is None:
            _LOGGER.debug(f"获取RGB颜色：{state.entity_id} 的 rgb_color 为 None")
            return None
        
        # 4. 校验并标准化 RGB 格式（确保是长度为3的数字列表/元组）
        try:
            # 转换为列表，兼容元组/列表类型
            rgb_list = list(rgb_color)
            # 检查长度是否为3
            if len(rgb_list) != 3:
                _LOGGER.warning(f"获取RGB颜色：{state.entity_id} 的 rgb_color 长度异常：{rgb_color}")
                return None
            
            # 转换为整数并限制在 0-255 范围（防止异常值）
            r = max(0, min(255, int(rgb_list[0])))
            g = max(0, min(255, int(rgb_list[1])))
            b = max(0, min(255, int(rgb_list[2])))
            
            return (r, g, b)
        
        except (TypeError, ValueError) as e:
            # 处理非数字、无法转换的情况
            _LOGGER.error(f"获取RGB颜色失败：{state.entity_id}，错误：{e}，原始值：{rgb_color}")
            return None
        
    @staticmethod
    def util_get_state_colorTemperature(state) -> int:
        """安全获取色温并转换，优先使用color_temp_kelvin（HA新版），
           兼容旧版color_temp（mired值）"""
        if not state:
            _LOGGER.debug("No state object")
            return 0
        
        # 优先使用HA新版的color_temp_kelvin（直接开尔文值）
        color_temp_kelvin = state.attributes.get('color_temp_kelvin')
        if color_temp_kelvin is not None:
            try:
                kelvin = int(float(color_temp_kelvin))
                result = int(kelvin / 50) * 50
                _LOGGER.debug(f"util_get_state_colorTemperature: from color_temp_kelvin={color_temp_kelvin} -> {result}")
                return result
            except (TypeError, ValueError) as e:
                _LOGGER.error(f"Error parsing color_temp_kelvin: {e}")
        
        # 兼容旧版HA：从color_temp（mired值）转换
        color_temp = state.attributes.get('color_temp')
        if color_temp is not None:
            try:
                kelvin = 10 ** 6 / float(color_temp)
                result = int(kelvin / 50) * 50
                _LOGGER.debug(f"util_get_state_colorTemperature: from color_temp(mired)={color_temp} -> {result}")
                return result
            except (TypeError, ValueError, ZeroDivisionError) as e:
                _LOGGER.error(f"Error calculating color temperature from mired: {e}")
        
        _LOGGER.debug("No color_temp_kelvin or color_temp attribute found in state")
        return 0
    @staticmethod
    def util_get_min_color_temperature(state) -> int:
        """获取最小色温（开尔文）"""
        try:
            if state and state.attributes.get('min_color_temp_kelvin') is not None:
                min_kelvin = state.attributes['min_color_temp_kelvin']
                return int(min_kelvin / 50) * 50
            
            if state and state.attributes.get('min_mireds') is not None:
                min_mireds = state.attributes['min_mireds']
                kelvin = 10 ** 6 / float(min_mireds)
                return int(kelvin / 50) * 50
        except (TypeError, ValueError, ZeroDivisionError) as e:
            _LOGGER.error(f"Error getting min color temperature: {e}")
        
        _LOGGER.debug("No min_color_temp_kelvin or min_mireds attribute found in state, using default 2700")
        return 2700  # 默认最小色温2700K

    @staticmethod
    def util_get_max_color_temperature(state) -> int:
        """获取最大色温（开尔文）"""
        try:
            if state and state.attributes.get('max_color_temp_kelvin') is not None:
                max_kelvin = state.attributes['max_color_temp_kelvin']
                return int(max_kelvin / 50) * 50
            
            if state and state.attributes.get('max_mireds') is not None:
                max_mireds = state.attributes['max_mireds']
                kelvin = 10 ** 6 / float(max_mireds)
                return int(kelvin / 50) * 50
        except (TypeError, ValueError, ZeroDivisionError) as e:
            _LOGGER.error(f"Error getting max color temperature: {e}")
        
        _LOGGER.debug("No max_color_temp_kelvin or max_mireds attribute found in state, using default 6500")
        return 6500  # 默认最大色温6500K
     
        
    @staticmethod
    def util_get_state_positionPercentage(state) -> int:
        """安全获取位置百分比（适用于窗帘、百叶窗等设备）"""
        # 检查状态是否有效
        if not state:
            _LOGGER.debug("Invalid or empty state object")
            return 0  # 返回默认值或根据业务逻辑调整
        
        # 尝试从常见属性中获取位置信息（不同设备可能使用不同属性名）
        position_attrs = ['position', 'current_position', 'position_percentage']
        position = None
        
        for attr in position_attrs:
            if attr in state.attributes and state.attributes[attr] is not None:
                position = state.attributes[attr]
                break
        
        if position is None:
            _LOGGER.debug("No position attribute found in state")
            return 0  # 无位置信息时返回默认值
        
        try:
            # 转换为数值并校验范围（百分比通常为0-100）
            position_val = float(position)
            if not (0 <= position_val <= 100):
                _LOGGER.warning(f"Position value {position_val} out of 0-100 range")
                # 限制值在有效范围内
                clamped_val = max(0, min(100, position_val))
                return int(round(clamped_val))
            
            # 返回四舍五入后的整数百分比
            return int(round(position_val))
        
        except (TypeError, ValueError) as e:
            _LOGGER.error(f"Error parsing position value: {e}")
            return 0  # 解析失败时返回默认值
