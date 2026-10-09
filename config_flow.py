# custom_components/my_integration/config_flow.py
from typing import Optional, Set, Tuple
import voluptuous as vol
import traceback
import qrcode
from io import BytesIO
import base64
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
import homeassistant.helpers.config_validation as cv
from .intreiot.intreIot_cloud import IntreIotHttpClient
import logging
from .intreiot.const import (
    DOMAIN,
    DEFAULT_CLOUD_SERVER,
    DEFAULT_CTRL_MODE,
    DEFAULT_INTEGRATION_LANGUAGE,
    DEFAULT_NICK_NAME,
    DEFAULT_OAUTH2_API_HOST,
    DOMAIN,
    OAUTH2_AUTH_URL,
    OAUTH2_CLIENT_ID,
    CLOUD_SERVERS,
    OAUTH_REDIRECT_URL,
    INTEGRATION_LANGUAGES,
    SUPPORT_CENTRAL_GATEWAY_CTRL,
    NETWORK_REFRESH_INTERVAL,
    SYNC_FUN_TYPE,
    SYNC_AREA_TYPE,
)
from .const import CONF_SELECTED_ENTITIES, CONF_ENABLE_DEBUG_LOG, DEFAULT_ENABLE_DEBUG_LOG

# 导入日志模块
from .intreiot.setup_logger import log_setup_event
_LOGGER = logging.getLogger(__name__)

class IntreHomeControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for My Integration."""

    VERSION = 2

    _device_sync: bool
    _scene_sync: bool
    _show_qr_code: bool

    def __init__(self) -> None:
        self._cc_home_list_show = {}
        self._device_sync = False
        self._scene_sync = False
        self._show_qr_code = False
        self._selected_entities = []

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        log_setup_event("配置流", "async_step_user 开始", "info")
        errors = {}

        return await self.async_step_eula(user_input)

    async def async_step_eula(
        self, user_input: Optional[dict] = None
    ):
        log_setup_event("配置流", "async_step_eula 执行", "debug")
        if user_input:
            if user_input.get('eula', None) is True:
                log_setup_event("配置流", "用户同意EULA，跳转到配置选择", "info")
                return await self.async_step_configs_select(user_input)
            return await self.__show_eula_form('eula_not_agree')
        return await self.__show_eula_form('')

    async def __show_eula_form(self, reason: str):
        return self.async_show_form(
            step_id='eula',
            data_schema=vol.Schema({
                vol.Required('eula', default=False): bool,  # type: ignore
            }),
            last_step=False,
            errors={'base': reason},
        )

    async def async_step_configs_select(
        self, user_input: Optional[dict] = None
    ):
        log_setup_event("配置流", "async_step_configs_select 执行", "info")
        _LOGGER.debug('async_step_configs_select')
        try:
            if user_input is None:
                return await self.__show_configs_select_form('')
            if user_input.get('device', None) is False:
                if user_input.get('scene', None) is False:
                    return await self.__show_configs_select_form('请至少选择一种类型！')
            self._device_sync = user_input.get('device', False)
            self._scene_sync = user_input.get('scene', False)
            log_setup_event("配置流", f"用户选择: device_sync={self._device_sync}, scene_sync={self._scene_sync}", "info")
            # 直接跳到 entity_select 步骤
            return await self.async_step_entity_select()

        except Exception as err:
            _LOGGER.debug(
                'async_step_configs_select, %s, %s',
                err, traceback.format_exc())
            raise AbortFlow(
                reason='config_flow_error',
                description_placeholders={
                    'error': f'config_flow error, {err}'
                }) from err

    async def __show_configs_select_form(self, reason: str):
        return self.async_show_form(
            step_id='configs_select',
            data_schema=vol.Schema({
                vol.Required('device', default=False): bool,
                vol.Required('scene', default=False): bool,
            }),
            errors={'base': reason},
            last_step=False,
        )

    async def async_step_entity_select(self, user_input=None):
        """Handle the selection of specific entities to synchronize (initial setup)."""
        log_setup_event("配置流", "async_step_entity_select 执行", "info")
        if user_input is None:
            entities = {}
            for state in self.hass.states.async_all():
                friendly = state.name if state.name else state.entity_id
                entities[state.entity_id] = f'{state.entity_id} ({friendly})'
            return self.async_show_form(
                step_id='entity_select',
                data_schema=vol.Schema({
                    vol.Required('entities', default=[]): cv.multi_select(entities)
                }),
                last_step=False
            )
        self._selected_entities = user_input.get('entities', [])
        log_setup_event("配置流", f"初始配置流 - 用户选择的实体: {self._selected_entities}", "info")
        # 直接跳到 show_qrcode 步骤（用 return 调用，不用 progress_done）
        return await self.async_step_show_qrcode()

    def generate_qr_code_base64(self, data):
        """Generate a QR code and return it as a Base64-encoded string."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save the image to a BytesIO buffer
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return img_str

    async def async_step_show_qrcode(
        self, user_input: Optional[dict] = None
    ):
        """Show the QR code step."""
        log_setup_event("配置流", "async_step_show_qrcode 执行", "info")
        if self._show_qr_code:
            log_setup_event("配置流", "二维码已展示，配置流完成", "info")
            return await self.config_flow_done()
        self._show_qr_code = True
        return await self.__show_show_qrcode_form('')

    async def __show_show_qrcode_form(self, reason: str):
        client = IntreIotHttpClient()
        lanip = client.get_local_ip()
        devicesn = self.flow_id
        _LOGGER.debug('--------------------------------------------------')
        _LOGGER.debug(devicesn)
        await client.getToken(devicesn=devicesn)
        qr_code_rsp = await client.getQRcode()
        await client.deinit_async()
        qr_code_data = self.generate_qr_code_base64(qr_code_rsp['qrCode'])
        return self.async_show_form(
            step_id='show_qrcode',
            description_placeholders={
                "qr_code": "请使用盈趣智能APP扫码添加\r\n ![](data:image/png;base64," + qr_code_data + ")"
            },
            errors={'base': reason},
            last_step=False,
        )

    async def config_flow_done(self):
        # 根据用户选择的实体自动推断device_sync和scene_sync
        for entity_id in self._selected_entities:
            if entity_id.startswith('scene.'):
                self._scene_sync = True
            else:
                self._device_sync = True
        log_setup_event("配置流", f"配置流完成 - device_sync={self._device_sync}, scene_sync={self._scene_sync}, selected_entities={self._selected_entities}", "info")
        _LOGGER.debug('初始配置流完成 - 保存选项: selected_entities=%s', self._selected_entities)
        # 注意：HA的async_create_entry中options参数不会被持久化！
        # selected_entities必须写入data中，否则引擎同步时无法读取
        return self.async_create_entry(title="Intre Smart Home Control LTS", data={
            'device_sync': self._device_sync,
            'scene_sync': self._scene_sync,
            'devicesn': self.flow_id,
            CONF_SELECTED_ENTITIES: self._selected_entities
        })

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return IntreHomeControlOptionsFlow(config_entry)


class IntreHomeControlOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for My Integration."""
    _device_sync: bool
    _scene_sync: bool
    _selected_entities: list[str]
    _log_enabled: bool

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # 不调用 super().__init__(config_entry)，因为新版HA中
        # OptionsFlow.config_entry 是只读property，super().__init__() 会尝试赋值导致
        # AttributeError: property 'config_entry' has no setter
        self._config_entry = config_entry
        self._device_sync = config_entry.data.get('device_sync', False)
        self._scene_sync = config_entry.data.get('scene_sync', False)
        # 优先从data读取，备用从options读取，符合配置流的保存方式
        self._selected_entities = config_entry.data.get(CONF_SELECTED_ENTITIES, 
                          config_entry.options.get(CONF_SELECTED_ENTITIES, []))
        self._show_qr_code = False
        self._log_enabled = config_entry.data.get(CONF_ENABLE_DEBUG_LOG, DEFAULT_ENABLE_DEBUG_LOG)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        log_setup_event("配置", "OptionsFlow.async_step_init 执行", "info")
        return await self.async_step_device_scene_select()

    async def async_step_device_scene_select(self, user_input: Optional[dict] = None):
        """Handle the selection of device/sync types."""
        log_setup_event("配置", "OptionsFlow.async_step_device_scene_select 执行", "info")
        if user_input is None:
            return await self.__show_device_scene_select_form('')
        if user_input.get('device', None) is False:
            if user_input.get('scene', None) is False:
                return await self.__show_device_scene_select_form('请至少选择一种类型！')
        self._device_sync = user_input.get('device', False)
        self._scene_sync = user_input.get('scene', False)
        self._log_enabled = user_input.get('log_enabled', DEFAULT_ENABLE_DEBUG_LOG)
        log_setup_event("配置", f"选项流 - 用户选择: device_sync={self._device_sync}, scene_sync={self._scene_sync}, log_enabled={self._log_enabled}", "info")
        # Proceed to entity selection
        return await self.async_step_entity_select()

    async def __show_device_scene_select_form(self, reason: str):
        return self.async_show_form(
            step_id='device_scene_select',
            data_schema=vol.Schema({
                vol.Required('device', default=self._device_sync): bool,
                vol.Required('scene', default=self._scene_sync): bool,
                vol.Optional('log_enabled', default=self._log_enabled): bool,
            }),
            description_placeholders={
                "log_enabled_desc": "勾选=记录日志到文件(intre_setup.log)"
            },
            errors={'base': reason},
            last_step=False,
        )

    async def async_step_log_settings(self, user_input: Optional[dict] = None):
        """Handle logging settings."""
        log_setup_event("配置", "OptionsFlow.async_step_log_settings 执行", "info")
        if user_input is not None:
            self._log_enabled = user_input.get('log_enabled', DEFAULT_ENABLE_DEBUG_LOG)
            log_setup_event("配置", f"选项流 - 日志设置: log_enabled={self._log_enabled}", "info")
            return await self.async_step_entity_select()
        return self.async_show_form(
            step_id='log_settings',
            data_schema=vol.Schema({
                vol.Optional('log_enabled', default=DEFAULT_ENABLE_DEBUG_LOG): bool,
            }),
            description_placeholders={
                "log_enabled_desc": "勾选=记录日志到文件(intre_setup.log)，取消=关闭日志\n日志默认开启，可随时在选项中修改"
            },
            last_step=False
        )

    async def async_step_entity_select(self, user_input: Optional[dict] = None):
        """Handle the selection of specific entities to synchronize."""
        log_setup_event("配置", "OptionsFlow.async_step_entity_select 执行", "info")
        if user_input is None:
            # Build entity selector
            entities = {}
            for state in self.hass.states.async_all():
                friendly = state.name if state.name else state.entity_id
                entities[state.entity_id] = f'{state.entity_id} ({friendly})'
            return self.async_show_form(
                step_id='entity_select',
                data_schema=vol.Schema({
                    vol.Required('entities', default=self._selected_entities): cv.multi_select(entities)
                }),
                last_step=True
            )
        # user_input contains list of selected entity_ids under key 'entities'
        self._selected_entities = user_input.get('entities', [])
        log_setup_event("配置", f"选项流 - 用户选择的实体: {self._selected_entities}", "info")
        # 保存配置，将selected_entities写入data（options也会写，作为备用）
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            title="Intre Smart Home Control LTS",
            data={
                **self._config_entry.data,
                'device_sync': self._device_sync,
                'scene_sync': self._scene_sync,
                CONF_SELECTED_ENTITIES: self._selected_entities,
                CONF_ENABLE_DEBUG_LOG: self._log_enabled
            },
            options={
                **self._config_entry.options,
                CONF_SELECTED_ENTITIES: self._selected_entities
            }
        )
        # 动态应用日志开关
        from .intreiot.setup_logger import set_logging_enabled
        set_logging_enabled(self._log_enabled)
        # 直接通知运行中的引擎重新同步（不reload，避免初始化失败）
        try:
            from .intreiot.engine_manager import EngineManager
            engine = EngineManager.get_instance("intre_manage_engine")
            if engine and hasattr(engine, 'request_sync_refresh'):
                engine.request_sync_refresh(2) # 2秒后重新同步
                log_setup_event("配置", "选项流保存完成，已触发引擎重新同步", "info")
        except Exception:
            pass # 引擎未运行时忽略
        return self.async_create_entry(title='', data={})

    async def async_step_show_qrcode(self, user_input: Optional[dict] = None):
        """Show the QR code step."""
        log_setup_event("配置", "OptionsFlow.async_step_show_qrcode 执行", "info")
        if self._show_qr_code:
            # Update entry config, 将selected_entities写入data和options
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                title="Intre Smart Home Control LTS",
                data={
                    **self._config_entry.data,
                    'device_sync': self._device_sync,
                    'scene_sync': self._scene_sync,
                    CONF_SELECTED_ENTITIES: self._selected_entities,
                    CONF_ENABLE_DEBUG_LOG: self._log_enabled
                },
                options={
                    **self._config_entry.options,
                    CONF_SELECTED_ENTITIES: self._selected_entities
                }
            )
            # 直接通知引擎重新同步（不reload）
            try:
                from .intreiot.engine_manager import EngineManager
                engine = EngineManager.get_instance("intre_manage_engine")
                if engine and hasattr(engine, 'request_sync_refresh'):
                    engine.request_sync_refresh(2)
            except Exception:
                pass
            return self.async_create_entry(title='', data={})
        self._show_qr_code = True
        return await self.__show_show_qrcode_form('')

    async def __show_show_qrcode_form(self, reason: str):
        client: IntreIotHttpClient = IntreIotHttpClient()
        devicesn = self._config_entry.data.get('devicesn', self.flow_id)
        await client.getToken(devicesn=devicesn)
        qrcodestr = await client.getQRcode()
        await client.deinit_async()
        qr_code_data = self.generate_qr_code_base64(qrcodestr)
        return self.async_show_form(
            step_id='show_qrcode',
            description_placeholders={
                "qr_code": "请使用盈趣智能APP扫码添加\r\n ![](data:image/png;base64," + qr_code_data + ")"
            },
            errors={'base': reason},
            last_step=False,
        )

    def generate_qr_code_base64(self, data):
        """Generate a QR code and return it as a Base64-encoded string."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save the image to a BytesIO buffer
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return img_str
