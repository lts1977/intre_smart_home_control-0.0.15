# Intre Smart Home Control LTS

**版本**: 0.0.15  
**域名**: `intre_smart_home_control`  
**作者**: 平头哥(Honey Badger) 和 坤哥(Kun Master)  
**集成类型**: hub（配置流 + 选项流）  
**依赖**: `qrcode>=8.1`

---

## 概述

Intre Smart Home Control LTS 是一个 Home Assistant 自定义集成，用于将 HA 中的设备（灯、开关、窗帘、空调、新风、扫地机、传感器等）同步到**盈趣智能（Intretech）云端**，通过盈趣智能 APP 实现对 HA 设备的远程控制。

该集成将 HA 设备映射为盈趣物模型产品，通过 MQTT 协议与云端通信，支持设备状态的双向同步。

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                   Home Assistant                         │
│                                                          │
│  ┌──────────────┐  ┌──────────────────────────────────┐  │
│  │  Config Flow  │  │       IntreManagementEngine      │  │
│  │  (配置流)      │  │  (核心引擎 - 设备同步/管理)       │  │
│  └──────────────┘  └──────────┬───────────────────────┘  │
│                                │                          │
│  ┌─────────────────────────────┼──────────────────────┐  │
│  │  Platform Entities          │                       │  │
│  │  ┌──────┐ ┌────┐ ┌──────┐  │                       │  │
│  │  │Light │ │Fan │ │Cover │  │  (每个实体继承         │  │
│  │  ├──────┤ ├────┤ ├──────┤  │   IntreIoTModule)     │  │
│  │  │Switch│ │HVAC│ │Sensor│  │                       │  │
│  │  ├──────┤ ├────┤ ├──────┤  │                       │  │
│  │  │Vacuum│ │Evt │ │Notify│  │                       │  │
│  │  └──────┘ └────┘ └──────┘  │                       │  │
│  └─────────────────────────────┘                       │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │           IntreIoT 核心库                          │  │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────────┐   │  │
│  │  │CloudClient│ │MQTTClient│ │IntreIotHa     │   │  │
│  │  │(HTTP API) │ │(Pub/Sub) │ │(HA设备发现)    │   │  │
│  │  ├───────────┤ ├──────────┤ ├───────────────┤   │  │
│  │  │Storage    │ │Network   │ │IntrepsCloud   │   │  │
│  │  │(持久化)   │ │(网络检测) │ │(Pub/Sub云端)   │   │  │
│  │  └───────────┘ └──────────┘ └───────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  辅助模块                                         │  │
│  │  ┌────────────┐ ┌──────────┐ ┌───────────────┐   │  │
│  │  │SetupLogger │ │LogSwitch │ │EngineManager  │   │  │
│  │  │(安装日志)   │ │(日志开关) │ │(全局引擎管理)   │   │  │
│  │  └────────────┘ └──────────┘ └───────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
   ┌──────────────┐     ┌──────────────────┐
   │  盈趣云端     │     │  盈趣智能 APP     │
   │  (HTTP API)  │     │  (MQTT 控制)     │
   └──────────────┘     └──────────────────┘
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **IntreManagementEngine** | `intreiot/intre_manage_engine.py` | 核心引擎，管理设备同步、订阅、物模型创建 |
| **IntreIotHttpClient** | `intreiot/intreIot_cloud.py` | 盈趣云端 HTTP API 客户端（OAuth2、Token、设备注册） |
| **IntreIoTClient** | `intreiot/intreIot_client.py` | MQTT 客户端，处理设备状态订阅和指令下发 |
| **IntreIotHa** | `intreiot/intreIot_ha.py` | HA 设备发现，扫描 HA 设备注册表和实体注册表 |
| **IntreIoTProduct** | `intreiot/intreIot_module.py` | 物模型产品类，每个产品对应一个 HA 设备 |
| **IntreIoTModule** | `intreiot/intreIot_module.py` | 物模型模块基类，所有实体类型继承自此类 |
| **IntrepsCloudClient** | `intreiot/intreIot_intreps.py` | 盈趣 Pub/Sub 云端客户端（1258行，核心通信模块） |
| **IntreIoTNetwork** | `intreiot/intreIot_network.py` | 网络检测和连接管理 |
| **IntreIoTStorage** | `intreiot/intreIot_storage.py` | 本地持久化存储（证书、配置等） |
| **IntreIoTEventLoop** | `intreiot/intreIot_ev.py` | 自定义事件循环管理 |
| **EngineManager** | `intreiot/engine_manager.py` | 全局引擎实例注册表（单例模式） |
| **SetupLogger** | `intreiot/setup_logger.py` | 安装运行日志记录器，输出到 `intre_setup.log` |

---

## 支持的平台和物模型映射

| HA 平台 | 物模型模块代码 | 对应文件 | 说明 |
|---------|---------------|---------|------|
| `light` | `dualColorTemperatureLight` | `dualColorTemperatureLight.py` | 双色温灯（色温+亮度） |
| `light` | `singleColorTemperatureLight` | `dualColorTemperatureLight.py` | 单色温灯（仅亮度） |
| `light` | `RGBWLight` | `dualColorTemperatureLight.py` | RGBW 灯带（RGB+白光） |
| `light` | `RGBCWLight` | `dualColorTemperatureLight.py` | RGBCW 灯（RGB+冷暖白） |
| `switch` / `input_boolean` | `switch` | `switch.py` | 开关 |
| `cover` | `liftCurtain` | `curtain.py` | 窗帘/卷帘 |
| `climate` | `airConditioner` | `climate.py` | 空调 |
| `climate` | `floorHeating` | `hvac.py` | 地暖 |
| `fan` | `freshAir` | `fan.py` | 新风系统 |
| `vacuum` | `robotVacuumCleaner` | `vacuum.py` | 扫地机器人 |
| `event` | `button` | `event.py` | 按钮/事件 |
| `sensor` | `sensor` | `sensor.py` | 传感器 |
| `notify` | — | `notify.py` | 通知转发（调用各平台 setup_entry） |
| — | `log_switch` | `log_switch.py` | 日志开关实体（SwitchEntity） |

---

## 安装

1. 将 `intre_smart_home_control` 目录复制到 HA 的 `custom_components/` 目录下
2. 重启 Home Assistant
3. 在 **设置 → 设备与服务 → 添加集成** 中搜索 "Intre Smart Home Control LTS"
4. 按照配置向导完成设置

---

## 配置流（首次安装）

配置流包含以下步骤：

### 1. EULA（风险告知）
显示风险告知和免责声明，用户需勾选同意后才能继续。

### 2. 选择同步类型
- **设备同步** — 同步 switch、light、cover 等设备
- **情景同步** — 同步 scene 类型实体
- 至少选择一种类型

### 3. 选择实体
- 全列表显示 HA 中所有实体（带搜索框过滤）
- 勾选需要同步到盈趣云端的实体
- 空列表表示同步全部

### 4. 二维码
- 生成盈趣智能 APP 扫码添加的二维码
- 使用盈趣 APP 扫码后即可在 APP 中看到和控制设备

---

## 选项流（配置修改）

安装后可通过 **集成卡片 → 配置** 进入选项流，修改以下设置：

### 同步类型设置
- 设备同步开关
- 情景同步开关
- 日志开关（是否记录日志到 `intre_setup.log`）

### 实体选择
- 重新选择需要同步的实体
- 保存后自动触发引擎重新同步（无需重启 HA）

---

## 功能特性

### 选择性同步
- 支持只同步选中的实体到云端，减少不必要的云端通信
- 空列表 = 同步全部（向后兼容）
- 在选项流中修改后立即生效，引擎自动增量同步

### 日志开关
- 集成卡片上显示一个 `日志开关` 实体（SwitchEntity）
- 开启时记录详细安装运行日志到 `intre_setup.log`
- 关闭时停止日志写入，减少磁盘 I/O
- 可在选项流中同步修改

### 设备自动发现
- `IntreIotHa` 自动扫描 HA 设备注册表和实体注册表
- 支持已绑定设备的实体和未绑定设备的独立实体（orphan 实体）
- 每3600秒自动刷新设备列表

### 状态双向同步
- HA 设备状态变化 → 上报盈趣云端 → APP 更新
- APP 操作 → MQTT 指令下发 → HA 设备执行

### 云端物模型
- 每个 HA 设备在云端注册为 `Intre.HA-Light` / `Intre.HA-Switch` 等产品
- 产品包含多个模块（module），每个模块对应一个实体
- 支持模块动态添加（add_dynamic_module）

---

## 文件结构

```
intre_smart_home_control/
├── __init__.py                  # 插件入口，async_setup / async_setup_entry
├── manifest.json                # 插件清单（版本0.0.15）
├── config_flow.py               # 配置流 + 选项流（EULA、实体选择、二维码）
├── const.py                     # 本地常量（selected_entities, debug_log）
├── strings.json                 # 配置流字符串翻译
├── MODIFY_LOG.md                # 修改日志
├── WORKLOG_*.md                 # 工作日志
├── README.md                    # 本文件
│
├── dualColorTemperatureLight.py # 灯平台（单色温/双色温/RGBW/RGBCW）
├── switch.py                    # 开关平台
├── curtain.py                   # 窗帘平台
├── climate.py                   # 空调平台
├── hvac.py                      # 地暖平台
├── fan.py                       # 新风平台
├── vacuum.py                    # 扫地机平台
├── sensor.py                    # 传感器平台
├── event.py                     # 事件/按钮平台
├── notify.py                    # 通知转发平台（模块分发器）
├── log_switch.py                # 日志开关实体
├── util.py                      # 工具类（StateUtils）
│
├── intreiot/                    # IntreIoT 核心库
│   ├── __init__.py
│   ├── const.py                 # 全局常量（域名、服务器地址、产品Key等）
│   ├── common.py                # 通用工具（IntreIoTMatcher）
│   ├── intre_manage_engine.py   # 核心引擎（设备同步、订阅、管理）
│   ├── intreIot_cloud.py        # HTTP API 客户端
│   ├── intreIot_client.py       # MQTT 客户端
│   ├── intreIot_ha.py           # HA 设备发现
│   ├── intreIot_module.py       # 物模型产品/模块基类
│   ├── intreIot_intreps.py      # Pub/Sub 云端客户端
│   ├── intreIot_network.py      # 网络检测
│   ├── intreIot_storage.py      # 持久化存储
│   ├── intreIot_ev.py           # 事件循环
│   ├── intreIot_error.py        # 错误码和异常
│   ├── mqttMsgdef.py            # MQTT 消息定义
│   ├── engine_manager.py        # 全局引擎管理器
│   ├── setup_logger.py          # 安装运行日志记录器
│   ├── i18n/                    # 多语言翻译
│   │   ├── zh-Hans.json
│   │   ├── zh-Hant.json
│   │   ├── en.json
│   │   ├── de.json, es.json, fr.json, ja.json, ...
│   └── └── ...
│
└── translations/
    └── zh-Hans.json             # HA 配置流翻译（中文）
```

---

## 开发说明

### 修改规则
1. **只修改需要改动的位置**，不需要修改的代码坚决不动
2. 修改前先 git 备份：`cd <插件目录> && git add -A && git commit -m "备份：描述"`
3. 修改后写工作日志到 `WORKLOG_YYYYMMDD.md` 并 git 提交
4. 不要使用三引号注释代码块（Python 三引号内缩进不一致会引发 IndentationError），用 `#` 单行注释替代

### 关键常量
- `INTREIOT_HTTP_SERVER_URL` = `https://mars.intreplus.com`
- `MQTT_ToH` = `""`（空字符串）
- `INTRE_SECURE_KEY` = `"intre-prod"`
- 产品 Key: `Intre.HA-Light`、`Intre.HA-Switch`、`Intre.HA-Curtain` 等

### 云端物模型模板
- 云端只存在 V1 版本的物模型模板
- 灯模板：`RGBWLight_1`、`RGBCWLight_1`、`singleColorTemperatureLight_1`、`dualColorTemperatureLight_2`
- 不要使用 V1.3 / V2 等不存在的版本号，否则云端返回 6018 错误

### 色温参数
- HA 新版（Core 2026.6.2+）使用 `color_temp_kelvin`（开尔文）参数，非 `color_temp`（mired）
- 双色温灯色温范围：2700K–6500K

---

## 已知问题和注意事项

1. **ConfigEntryControl API**: HA 2026.6.2 中 `homeassistant.helpers.config_entry_control` 模块不存在，集成卡片上的自定义控制按钮已临时注释
2. **传感器同步**: 盈趣云端没有 `Intre.HA-Sensor` 产品类型和 `temperature_1` 模板，传感器同步功能已封存
3. **config_flow_done 推断覆盖**: `config_flow_done()` 中通过 entity_id 推断 `device_sync`/`scene_sync` 可能覆盖用户在 `configs_select` 步骤的显式选择
4. **sync 缩进问题**: `sync_ha_device_and_scene_cloud` 中 device_sync 代码可能嵌套在 scene_sync 的 if 块内，导致 scene_sync=False 时设备同步也被跳过
5. **重复 add_dynamic_module**: 每30秒定时同步时，已同步过的设备不应重复调用 add_dynamic_module（已修复，通过 `_intre_devicesn_add` 判断）

---

## 许可证

本集成基于 Intretech 提供的许可协议使用，仅限 Home Assistant 非商业用途。
