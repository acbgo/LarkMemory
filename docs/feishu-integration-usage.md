# LarkMemory 飞书事件与 API 使用清单

> 最后更新：2026-05-05
>
> 本文档面向 LarkMemory 项目实现，列出当前需要用到的飞书 Webhook/长连接事件、卡片回调和 OpenAPI，并说明各自使用场景、项目入口和实现注意事项。
>
> 官方文档入口：
>
> - [事件与回调](https://open.feishu.cn/llms-docs/zh-CN/llms-events-and-callbacks.txt)
> - [消息](https://open.feishu.cn/llms-docs/zh-CN/llms-messaging.txt)
> - [飞书卡片](https://open.feishu.cn/llms-docs/zh-CN/llms-feishu-card.txt)
> - [日历](https://open.feishu.cn/llms-docs/zh-CN/llms-calendar.txt)
> - [云文档](https://open.feishu.cn/llms-docs/zh-CN/llms-docs.txt)
> - [视频会议](https://open.feishu.cn/llms-docs/zh-CN/llms-video-conferencing.txt)
> - [妙记](https://open.feishu.cn/llms-docs/zh-CN/llms-minutes.txt)
> - [任务](https://open.feishu.cn/llms-docs/zh-CN/llms-tasks.txt)

## 1. 总体接入方式

LarkMemory 的飞书侧接入采用 Source Adapter 方式：

```text
飞书 WebSocket 长连接 / OpenAPI
-> src/sources/feishu/client
-> src/sources/feishu/events
-> NormalizedEvent
-> MemoryService.ingest_event()
-> domain handlers
```

当前项目优先使用 `lark-oapi` Python SDK：

- `src/sources/feishu/client/sdk.py`：创建 OpenAPI client 和 WebSocket client。
- `src/sources/feishu/client/listener.py`：注册事件和回调处理器。
- `src/sources/feishu/events/*_normalizer.py`：将飞书事件转为项目统一 `NormalizedEvent`。
- `src/sources/feishu/proactive/`：将 MemoryService 主动建议渲染并发送为飞书消息/卡片。

## 2. Webhook / 长连接事件清单

### 2.1 IM 消息接收

| 项目 | 内容 |
| --- | --- |
| 官方事件类型 | `im.message.receive_v1` |
| 官方文档 | [接收消息](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive.md) |
| SDK 注册方法 | `register_p2_im_message_receive_v1` |
| 项目入口 | `src/sources/feishu/client/listener.py::_message_event_from_lark()` |
| 标准化入口 | `src/sources/feishu/events/normalizer.py::normalize_message_event()` |
| 目标 source/event | `source_type="feishu_chat"`，`event_type="chat_message"` |

使用场景：

- 机器人所在群或单聊中出现与项目决策、团队风险、长期提醒相关的消息时，自动写入 Memory Engine。
- 群聊中的关键客户要求、风险点、约定、后续动作被归档为候选长期记忆。
- 后续可配合 `team_retention` 复习提醒，避免团队关键事项遗忘。

关键字段：

- `event.sender.sender_id.open_id`
- `event.message.message_id`
- `event.message.chat_id`
- `event.message.chat_type`
- `event.message.message_type`
- `event.message.content`
- `event.message.create_time`

注意事项：

- 官方建议有幂等需求时使用 `message_id` 去重，不要依赖 `event_id`。
- 群消息权限有多种粒度：单聊、群 @ 机器人、群全部消息。比赛 Demo 若要完整采集群消息，需要确认应用已申请对应权限。
- `content` 是不同消息类型对应的 JSON 字符串，文本消息可取 `text`，富文本 `post` 需要递归解析文本片段。

### 2.2 飞书卡片回传交互

| 项目 | 内容 |
| --- | --- |
| 官方回调类型 | `card.action.trigger` |
| 官方文档 | [卡片回传交互回调](https://open.feishu.cn/document/feishu-cards/card-callback-communication.md) |
| SDK 注册方法 | `register_p2_card_action_trigger` |
| 项目入口 | `src/sources/feishu/client/listener.py::_card_action_from_lark()` |
| 业务处理 | `src/sources/feishu/proactive/callbacks.py::FeishuCardActionHandler` |

使用场景：

- 用户点击团队记忆复习卡片上的“已复习”“明天提醒”“废弃记忆”等按钮。
- 将飞书卡片按钮动作映射为 MemoryService 的 `reviewed`、`snooze`、`expire`、`forget` 更新操作。
- 形成主动服务闭环：系统提醒 -> 用户反馈 -> 更新复习计划或记忆状态。

关键字段：

- `event.operator.open_id`
- `event.action.value`
- `event.action.tag`
- `event.action.form_value`

响应格式：

- 当前项目只需要返回 Toast，格式为：

```json
{
  "toast": {
    "type": "info",
    "content": "操作已完成"
  }
}
```

注意事项：

- 官方要求回调在 3 秒内响应。涉及耗时操作时应先快速返回，再异步处理。
- `value` 可以是 object 或 string。项目中建议统一使用 object，并放入 `source/action/memory_id/snooze_days`。

### 2.3 日程变更

| 项目 | 内容 |
| --- | --- |
| 官方事件类型 | `calendar.calendar.event.changed_v4` |
| 官方文档 | [日程变更](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/events/changed.md) |
| 官方 SDK 示例方法 | `register_p2_calendar_calendar_event_changed_v4` |
| 当前项目入口 | `src/sources/feishu/client/listener.py::_calendar_event_from_lark()` |
| 标准化入口 | `src/sources/feishu/events/calendar_normalizer.py` |
| 目标 source/event | `source_type="feishu_calendar"`，`event_type="calendar_event"` |

使用场景：

- 捕捉项目会议、客户评审、上线窗口、复盘会议等日历事件。
- 将日程标题、时间、参与人和地点转为长期协作上下文。
- 后续可用于会议前主动提醒：“这个项目上次决策是什么”“会议有哪些历史风险”。

官方事件字段：

- `calendar_id`
- `user_id_list`
- `calendar_event_id`，灰度字段
- `change_type`，灰度字段
- `rsvp_infos`，灰度字段

注意事项：

- 官方说明：需要先调用“订阅日程变更事件”接口订阅指定日历，再在开发者后台添加事件。
- 该事件本身通常不是完整日程详情。若需要 `summary/start_time/end_time/description/attendees`，应在收到事件后再调用日历详情或列表接口补齐。
- 当前代码中直接从事件读取 `summary/start_time/end_time` 的实现假设偏乐观，真实环境建议改为“事件触发 -> 拉取日程详情 -> 标准化”。

### 2.4 文档编辑

| 项目 | 内容 |
| --- | --- |
| 官方事件类型 | `drive.file.edit_v1` |
| 官方文档 | [文件编辑](https://open.feishu.cn/document/server-docs/docs/drive-v1/event/list/file-edited.md) |
| 官方 SDK 示例方法 | `register_p2_drive_file_edit_v1` |
| 当前项目处理目标 | 文档变更后拉取纯文本内容并切分为 `doc_section` 事件 |
| 当前处理器 | `src/sources/feishu/events/doc_processor.py::DocProcessor` |
| 目标 source/event | `source_type="feishu_doc"`，`event_type="doc_section"` |

使用场景：

- 项目方案、需求文档、接口说明、复盘文档发生变更后，自动更新 Memory Engine 中的文档章节记忆。
- 文档被拆分成章节后写入，便于后续按主题召回，而不是把整篇文档塞入单条记忆。
- 结合 `SourceStateStore` 对文档内容 hash 去重，避免每次事件重复写入相同内容。

官方事件字段：

- `file_token`
- `file_type`
- `operator_id_list`
- `subscriber_id_list`

注意事项：

- 飞书云文档事件需要先调用“订阅云文档事件”API 订阅具体文件。
- 文档事件是 Drive 维度事件，不是 Docx 专属事件。需要用 `file_type == "docx"` 过滤新版文档。
- 当前代码若使用 `doc_token` 字段，应改为从 `file_token` 映射。

### 2.5 会议结束

| 项目 | 内容 |
| --- | --- |
| 官方事件类型 | `vc.meeting.meeting_ended_v1` |
| 官方文档 | [会议结束](https://open.feishu.cn/document/server-docs/vc-v1/meeting/events/meeting_ended.md) |
| 官方 SDK 示例方法 | `register_p2_vc_meeting_meeting_ended_v1` |
| 当前项目入口 | `src/sources/feishu/client/listener.py::_meeting_ended_from_lark()` |
| 后续处理器 | `src/sources/feishu/events/meeting_processor.py::MeetingProcessor` |
| 目标 source/event | `source_type="feishu_vc"`，`event_type="meeting_summary/meeting_todo/meeting_chapter"` |

使用场景：

- 会议结束后记录会议基础信息。
- 等待妙记 AI 产物生成后，拉取会议总结、待办和逐字稿章节，写入 Memory Engine。
- 用于赛后 Demo 中展示“会议内容自动沉淀为长期记忆”。

官方事件字段：

- `topic`
- `meeting_no`
- `meeting_source`
- `start_time`
- `end_time`
- `host_user`
- `owner`

注意事项：

- `vc.meeting.meeting_ended_v1` 主要适用于通过 OpenAPI 预约的会议。
- 若要监听企业内所有会议结束，应使用 `vc.meeting.all_meeting_ended_v1`，但权限更高。
- 官方事件文档没有明确暴露 `meeting_id` 字段时，不能直接假设可用。需要根据真实 payload 或改用会议号/时间范围查询会议详情。

### 2.6 录制完成

| 项目 | 内容 |
| --- | --- |
| 官方事件类型 | `vc.meeting.recording_ready_v1` |
| 官方文档 | [录制完成](https://open.feishu.cn/document/server-docs/vc-v1/meeting/events/recording_ready.md) |
| 当前项目状态 | 建议补充订阅；当前主要靠会议结束后延迟扫描 |

使用场景：

- 当会议录制文件上传完毕时触发，比固定 sleep 更可靠。
- 收到该事件后再调用“获取录制文件”API，避免会议刚结束时妙记尚未生成。
- 可减少 `MeetingProcessor` 中的长时间等待和重试。

注意事项：

- 录制文件需要会议结束且收到录制完成事件后再获取。
- 如果比赛 Demo 依赖妙记内容，建议将该事件作为主触发，`meeting_scanner` 作为兜底。

### 2.7 任务变更（应用维度）

| 项目 | 内容 |
| --- | --- |
| 官方事件类型 | `task.task.updated_v1` |
| 官方文档 | [任务信息变更（应用维度）](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/task-v1/task/events/updated) |
| SDK 注册方法 | `register_p2_task_task_updated_v1`（已通过 lark-oapi 1.5.5 验证） |
| 当前项目入口 | `src/sources/feishu/client/listener.py::_task_event_from_lark()` |
| 标准化入口 | `src/sources/feishu/events/task_normalizer.py` |
| 目标 source/event | `source_type=”feishu_task”`，`event_type=”task_created/task_updated/task_completed”` |

使用场景：

- 捕捉项目任务创建、任务完成、任务延期、负责人变化。
- 将任务标题、描述、截止时间、负责人、关注者写入长期记忆。
- 支撑主动提醒和协作断点恢复：”这个任务谁负责、什么时候到期、为什么延期”。

注意事项：

- **仅收到该 APP 创建的任务变更**，用户通过客户端或文档创建的任务不推送。
- 通过 `user_access_token` 方式创建的任务不会推送。
- 如需更广泛的任务变更，可考虑使用任务清单动态订阅 API 作为补充。

## 3. OpenAPI 清单

### 3.1 发送飞书消息/卡片

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `POST /open-apis/im/v1/messages?receive_id_type=chat_id` |
| 官方文档 | [发送消息](https://open.feishu.cn/document/server-docs/im-v1/message/create.md) |
| SDK 调用 | `client.im.v1.message.create()` |
| 项目入口 | `src/sources/feishu/proactive/notifier.py::FeishuNotifier` |

使用场景：

- 主动推送团队记忆复习提醒。
- 向指定群发送文本消息或互动卡片。
- 比赛 Demo 中展示 AI 不是被动检索，而是能主动服务。

关键请求：

- 查询参数：`receive_id_type=chat_id`
- 请求体：`receive_id`、`msg_type`、`content`
- `content` 必须是 JSON 结构序列化后的字符串。

消息类型：

- `text`：文本消息，内容形如 `{"text": "..."}`
- `interactive`：互动卡片，内容为卡片 JSON 字符串

注意事项：

- 机器人需要在目标群内且有发言权限。
- 卡片/富文本消息体最大限制更小，生成卡片时要避免内容过长。

### 3.2 订阅日程变更

| 项目 | 内容 |
| --- | --- |
| 官方 API | 订阅日程变更事件 |
| 官方文档 | [订阅日程变更事件](https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/subscription.md) |
| 项目状态 | 需要在接入真实日历前补充调用或人工配置 |

使用场景：

- 对用户或团队关键日历建立日程变更订阅。
- 没有订阅时，即使开发者后台添加了事件，也无法收到指定日历下的日程变更。

注意事项：

- 该 API 通常需要用户具备对应日历访问权限。
- 对个人主日历、共享日历、会议室日历的权限边界不同，Demo 时建议先固定一个测试日历。

### 3.3 订阅云文档事件

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `POST /open-apis/drive/v1/files/:file_token/subscribe` |
| 官方文档 | [订阅云文档事件](https://open.feishu.cn/document/server-docs/docs/drive-v1/event/subscribe.md) |
| 项目状态 | 需要在处理文档编辑事件前补充 |

使用场景：

- 对项目 PRD、架构文档、接口文档建立编辑事件订阅。
- 文档被编辑后触发 `drive.file.edit_v1`，再拉取纯文本内容入库。

关键参数：

- 路径参数：`file_token`
- 查询参数：`file_type=docx`

注意事项：

- 文档通知事件仅支持文档拥有者和文档管理者订阅。
- 使用 `tenant_access_token` 时，应用通常还需要被添加为文档协作者或文档应用。

### 3.4 获取新版文档纯文本内容

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `GET /open-apis/docx/v1/documents/:document_id/raw_content` |
| 官方文档 | [获取文档纯文本内容](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/raw_content.md) |
| 项目入口 | `src/sources/feishu/client/doc_client.py::FeishuDocClient.fetch_doc_content()` |

使用场景：

- 文档编辑后拉取全文。
- 文档内容经过 `split_by_headings()` 切分为章节。
- 每个章节作为 `doc_section` 事件进入 Memory Engine。

响应字段：

- `data.content`：文档纯文本内容

注意事项：

- 当前调用身份必须有文档阅读权限。
- 对大文档可能触发内容大小限制，需要后续改为分块 API 或按块分页读取。

### 3.5 获取会议录制文件

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `GET /open-apis/vc/v1/meetings/:meeting_id/recording` |
| 官方文档 | [获取录制文件](https://open.feishu.cn/document/server-docs/vc-v1/meeting-recording/get.md) |
| 项目入口 | `src/sources/feishu/client/vc_client.py::FeishuVcClient.get_recording()` |

使用场景：

- 会议结束或录制完成后获取录制文件信息。
- 从录制 URL 中提取妙记 `minute_token`。
- 继续调用妙记 API 获取文字记录或基础信息。

响应字段：

- `data.recording.url`
- `data.recording.duration`

注意事项：

- 官方要求会议结束并收到录制完成事件后再获取录制文件。
- 响应中是 `url`，不是 `minute_token`。项目中应从 URL 的 `/minutes/{token}` 解析 token。

### 3.6 获取妙记基础信息

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `GET /open-apis/minutes/v1/minutes/:minute_token` |
| 官方文档 | [获取妙记信息](https://open.feishu.cn/document/server-docs/minutes-v1/minute/get.md) |

使用场景：

- 获取妙记标题、时长、URL、note_id 等基础信息。
- 作为会议记忆的来源说明和跳转链接。

响应字段：

- `title`
- `cover`
- `duration`
- `url`
- `note_id`

注意事项：

- 妙记未生成完成时会返回 “minute not ready” 类错误，需要重试或延迟扫描。

### 3.7 导出妙记文字记录

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `GET /open-apis/minutes/v1/minutes/:minute_token/transcript` |
| 官方文档 | [导出妙记文字记录](https://open.feishu.cn/document/minutes-v1/minute-transcript/get.md) |

使用场景：

- 获取会议逐字稿。
- 按章节或长度切分为 `meeting_chapter` 事件。
- 为后续会议总结、待办、项目决策抽取提供原始文本。

关键参数：

- 路径参数：`minute_token`
- 查询参数：`file_format=txt` 或 `srt`

注意事项：

- 该接口返回的是导出文件内容，而不是结构化 `summary/todo/chapter` JSON。
- 如果需要结构化总结和待办，可能需要项目侧 LLM 二次抽取，或确认是否有额外内测/灰度 API。

### 3.8 下载妙记音视频文件

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `GET /open-apis/minutes/v1/minutes/:minute_token/media` |
| 官方文档 | [下载妙记音视频文件](https://open.feishu.cn/document/minutes-v1/minute-media/get.md) |

使用场景：

- 需要保留会议音视频证据或做后续离线转写时使用。
- 当前 LarkMemory 主链路暂不必须下载音视频，优先使用 transcript。

响应字段：

- `download_url`

注意事项：

- 音视频下载权限更敏感，比赛 Demo 阶段建议默认不启用。

### 3.9 任务清单动态订阅

| 项目 | 内容 |
| --- | --- |
| HTTP 方法与路径 | `POST /open-apis/task/v2/tasklists/:tasklist_guid/activity_subscriptions` |
| 官方文档 | [创建动态订阅](https://open.feishu.cn/document/task-v2/tasklist-activity_subscription/create.md) |

使用场景：

- 对项目任务清单建立动态订阅，接收任务创建、更新、完成等动态。
- 将任务动态转为 Memory Engine 的任务事件，沉淀负责人、截止时间、状态变化。

注意事项：

- 每个清单最多可创建一定数量的动态订阅。
- 当前项目如果继续使用 `task.updated_v2`，需要先从真实开发者平台确认该事件是否可订阅；否则建议切到任务清单动态订阅路线。

## 4. 项目内处理关系

| 飞书能力 | 项目模块 | 输出到 Memory 的事件 |
| --- | --- | --- |
| IM 消息 | `events/normalizer.py` | `chat_message` |
| 卡片按钮 | `proactive/callbacks.py` | 更新已有 memory 状态 |
| 日程变更 | `events/calendar_normalizer.py` | `calendar_event` |
| 任务动态 | `events/task_normalizer.py` | `task_created/task_updated/task_completed` |
| 会议结束 | `events/meeting_normalizer.py` | `meeting_summary` |
| 妙记文字记录 | `events/meeting_processor.py` | `meeting_summary/meeting_todo/meeting_chapter` |
| 文档编辑 | `events/doc_processor.py` | `doc_section` |

## 5. 已修正项（2026-05-05 经 SDK 1.5.5 验证）

### 事件注册与 API 类名

| # | 修正项 | 改动文件 |
|---|--------|---------|
| 1 | 日历事件：`register_p2_calendar_event_changed_v4` → `register_p2_calendar_calendar_event_changed_v4` | listener.py |
| 2 | 文档事件：`register_p2_doc_updated_v1` → `register_p2_drive_file_edit_v1` | listener.py |
| 3 | 文档模型：`doc_token/title/change_type` → `file_token/file_type`，operator → `operator_id_list[0].open_id` | doc_models.py, listener.py, doc_processor.py |
| 4 | 任务事件：`register_p2_task_updated_v2` → `register_p2_task_task_updated_v1` | listener.py |
| 5 | 会议事件：`register_p2_vc_meeting_ended_v1` → `register_p2_vc_meeting_meeting_ended_v1` | listener.py |
| 6 | 文档 API：`RawDocumentRequest` / `.document.raw()` → `RawContentDocumentRequest` / `.document.raw_content()` | doc_client.py |
| 7 | 纪要 API：SDK 未封装，改用底层 raw request 调用 `GET /vc/v1/notes/{note_id}` | vc_client.py |

### 功能缺陷修复

| # | 修正项 | 改动文件 |
|---|--------|---------|
| 8 | event_id 用 chunk_id（SHA256 内容指纹）替代位置索引，文档/会议章节内容变更后正确更新而非静默丢弃 | doc_normalizer.py, meeting_normalizer.py, doc_processor.py, meeting_processor.py, meeting_scanner.py |
| 9 | DocProcessor 空文档时更新 SourceStateStore（记录空 hash），避免旧 hash 残留导致后续变更判断错误 | doc_processor.py |
| 10 | `_ingest_notes` 重复代码提取到 `meeting_normalizer.ingest_notes_to_events()`，processor 和 scanner 复用 | meeting_normalizer.py, meeting_processor.py, meeting_scanner.py |
| 11 | MeetingScanner 增加 3 次重试（间隔 2 min），避免 AI 产物未就绪时直接 mark_error | meeting_scanner.py |
| 12 | `main()` 创建 SourceStateStore/VcClient/DocClient 并注入；`on_doc_changed` processor 不可用时 fallback dispatch `doc_changed` 事件 | listener.py |

## 6. 仍需关注的项

1. 获取会议录制响应中是 `recording.url`，不是 `recording.minute_token`，需从 URL 中 `minutes/` 路径段解析。
2. 纪要 API（`GET /vc/v1/notes/{id}`）当前用 raw request 方式调用，SDK 升级后应改为强类型调用。
3. 任务事件仅收到 APP 创建的任务变更，如需更广覆盖，可补充任务清单动态订阅 API。
4. 所有外部事件写入前建议做 raw payload 脱敏，避免敏感内容无边界落库。

## 6. Demo 推荐最小权限与配置

为了比赛 Demo 稳定，建议优先启用以下能力：

1. IM 消息接收：用于群聊和单聊记忆采集。
2. 发送消息：用于主动提醒和卡片推送。
3. 卡片回调：用于复习、顺延、废弃记忆。
4. 文档编辑事件 + 文档纯文本读取：用于项目文档记忆。
5. 会议录制完成 + 妙记 transcript：用于会议记忆。

日历和任务建议作为第二优先级：它们很有产品价值，但需要更多权限和订阅配置，真实环境下比 IM/文档/妙记更容易被权限边界卡住。
