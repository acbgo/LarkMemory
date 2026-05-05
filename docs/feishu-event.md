| 身份验证                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [撤销用户授权事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/authentication-management/auth-v4/user_access_token/events/revoked)auth.user_access_token.revoked_v4 | 当用户 user_access_token 或 refresh_token 被撤销后，会触发此事件。 |      |      |

| 通讯录                                                       |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [通讯录权限范围变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/scope/events/updated)contact.scope.updated_v3 | 当应用订阅该事件后，如果应用的通讯录权限范围发生变更，则会触发该事件。 |      |      |
| [员工入职](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/user/events/created)contact.user.created_v3 | 当应用订阅该事件后，如果有新员工入职（例如，通过管理后台添加成员、调用创建用户 API），则会触发该事件。 |      |      |
| [员工离职](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/user/events/deleted)contact.user.deleted_v3 | 当应用订阅该事件后，如果有员工离职（例如，通过管理后台离职成员、调用删除用户 API），则会触发该事件。 |      |      |
| [员工信息被修改](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/user/events/updated)contact.user.updated_v3 | 应用订阅该事件后，当员工信息（包括：ID、用户名、英文名、别名、邮箱、企业邮箱、职务、手机号、性别、头像、状态、所属部门、直属主管、城市、国家、工位、入职时间、工号、类型、排序、自定义字段、职级、序列、虚线上级）被修改时将会触发该事件。你可以在事件的 old_object 字段中查看修改前的用户信息；在事件的 object 字段中可以查看修改后的用户信息。 |      |      |
| [成员字段变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/custom_attr_event/events/updated)contact.custom_attr_event.updated_v3 | 当成员字段发生变更时（变更动作包括「打开/关闭」开关、「增加/删除」成员字段），会触发该事件。事件体的 old_object 展示字段的原始值，object 展示字段的更新值。 |      |      |
| [新建人员类型](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/employee_type_enum/events/created)contact.employee_type_enum.created_v3 | 当应用订阅该事件后，如果新增了人员类型中的选项，则会触发该事件。 |      |      |
| [启用人员类型](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/employee_type_enum/events/actived)contact.employee_type_enum.actived_v3 | 当应用订阅该事件后，如果将未激活的人员类型更新为激活状态，则会触发该事件。 |      |      |
| [停用人员类型](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/employee_type_enum/events/deactivated)contact.employee_type_enum.deactivated_v3 | 当应用订阅该事件后，如果将激活的人员类型更新为未激活状态，则会触发该事件。 |      |      |
| [删除人员类型](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/employee_type_enum/events/deleted)contact.employee_type_enum.deleted_v3 | 当应用订阅该事件后，如果删除某一人员类型，则会触发该事件。   |      |      |
| [修改人员类型名称](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/employee_type_enum/events/updated)contact.employee_type_enum.updated_v3 | 当应用订阅该事件后，如果更新了人员类型的选项内容（包括默认内容 content 参数和国际化内容 i18n_content），则会触发该事件。 |      |      |
| [部门新建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/department/events/created)contact.department.created_v3 | 当应用订阅该事件后，如果通讯录内有部门被创建，则会触发该事件。 |      |      |
| [部门被删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/department/events/deleted)contact.department.deleted_v3 | 应用订阅该事件后，如果通讯录内有部门被删除，则会触发该事件。 |      |      |
| [部门信息变化](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/department/events/updated)contact.department.updated_v3 | 当应用订阅该事件后，如果部门信息发生变化，则会触发该事件。部门信息发生变化的范围包括：企业管理员在管理后台修改部门信息。企业开发者调用[修改部门部分信息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/department/patch)、[更新部门所有信息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/department/update)、[更新部门ID](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/contact-v3/department/update_department_id) API 修改部门信息。 |      |      |

| 消息与群组                                                   |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [接收消息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive)im.message.receive_v1 | 机器人部分场景接收消息后触发此事件。                         |      |      |
| [消息已读](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/message_read)im.message.message_read_v1 | 用户阅读机器人发送的单聊消息后触发此事件。                   |      |      |
| [撤回消息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/recalled)im.message.recalled_v1 | 机器人所在会话内的消息被撤回时触发此事件。                   |      |      |
| [新增消息表情回复](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message-reaction/events/created)im.message.reaction.created_v1 | 应用订阅该事件后，消息被添加表情回复时会触发此事件。事件体包含被添加表情回复的消息 message_id、添加表情回复的操作人 ID、表情类型、添加时间等信息。 |      |      |
| [删除消息表情回复](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message-reaction/events/deleted)im.message.reaction.deleted_v1 | 应用订阅该事件后，消息被删除表情回复时会触发此事件。事件体包含被删除表情回复的消息 message_id、删除表情回复的操作人 ID、表情类型、添加时间等信息。 |      |      |
| [群解散](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat/events/disbanded)im.chat.disbanded_v1 | 群组被解散后触发此事件，在该群组内的、已订阅当前事件的应用机器人将会收到事件通知。 |      |      |
| [群配置修改](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat/events/updated)im.chat.updated_v1 | 群组配置被修改后触发此事件，在该群组内的、已订阅当前事件的应用机器人将会收到事件通知。修改操作包含：转移群主修改群基本信息，包括：群头像、群名称、群描述、群国际化名称修改群权限，包括：加人入群权限、群编辑权限、at 所有人权限、群分享权限等 |      |      |
| [用户进群](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat-member-user/events/added)im.chat.member.user.added_v1 | 新用户进群（包含话题群）时触发此事件，在群组内的、已订阅该事件的机器人会收到事件数据。 |      |      |
| [用户出群](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat-member-user/events/deleted)im.chat.member.user.deleted_v1 | 用户主动退出群聊或被移出群聊时推触发此事件，在群组内的、已订阅该事件的机器人会收到事件数据。 |      |      |
| [撤销拉用户进群](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat-member-user/events/withdrawn)im.chat.member.user.withdrawn_v1 | 撤销拉用户进群后触发此事件，在群组内的、已订阅该事件的机器人会收到事件消息。撤销操作是指如下图所示的群内 **撤销邀请**。![image.png](https://sf3-cn.feishucdn.com/obj/open-platform-opendoc/2faba42d3e4203e1dd899931da6dbfc8_DFXlHNscdw.png?height=278&maxWidth=550&width=1383) |      |      |
| [机器人进群](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat-member-bot/events/added)im.chat.member.bot.added_v1 | 机器人被用户添加至群聊时触发此事件，在群组内的、已订阅该事件的机器人会收到事件消息。 |      |      |
| [机器人被移出群](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat-member-bot/events/deleted)im.chat.member.bot.deleted_v1 | 机器人被移出群聊后触发此事件，仅被移除群组且订阅该事件的机器人会收到事件数据。 |      |      |
| [用户和机器人的会话首次被创建](https://open.feishu.cn/document/ukTMukTMukTM/uYDNxYjL2QTM24iN0EjN/bot-events)p2p_chat_create | 首次会话是用户了解应用的重要机会，你可以发送操作说明、配置地址来指导用户开始使用你的应用。 |      |      |
| [用户进入与机器人的会话](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat-access_event/events/bot_p2p_chat_entered)im.chat.access_event.bot_p2p_chat_entered_v1 | 用户进入与机器人的会话时触发此事件。                         |      |      |

| 云文档                                                       |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [文件夹下文件创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/events/created_in_folder)drive.file.created_in_folder_v1 | 当用户订阅的文件夹下有新建文件时将触发此事件。               |      |      |
| [文件标题变更](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/file-title-update)drive.file.title_updated_v1 | 文件标题变更时将触发此事件。                                 |      |      |
| [文件已读](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/file-read)drive.file.read_v1 | 文件被打开将触发此事件。                                     |      |      |
| [文件编辑](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/file-edited)drive.file.edit_v1 | 文件编辑将触发此事件。                                       |      |      |
| [文件协作者权限申请](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/events/permission_member_applied)drive.file.permission_member_applied_v1 | 当用户发起申请文件协作者权限时将触发此事件，协作者权限包括阅读、编辑和管理权限。 |      |      |
| [文件协作者添加](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/file-collaborator-add)drive.file.permission_member_added_v1 | 文件协作者添加用户/群时将触发此事件。                        |      |      |
| [文件协作者移除](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/file-collaborator-remove)drive.file.permission_member_removed_v1 | 文件协作者移除用户/群时将触发此事件。                        |      |      |
| [文件删除到回收站](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/delete-file-to-trash-can)drive.file.trashed_v1 | 文件被删除到回收站将触发此事件。                             |      |      |
| [文件彻底删除](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/event/file-deleted-completely)drive.file.deleted_v1 | 文件被彻底删除将触发此事件。                                 |      |      |
| [添加评论、回复通知事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/notice/events/comment_add)drive.notice.comment_add_v1 | 当用户有新文档评论或回复通知会触发此事件。                   |      |      |
| [多维表格记录变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/events/bitable_record_changed)drive.file.bitable_record_changed_v1 | 多维表格记录变更事件。被订阅的多维表格记录发生变更时，将会触发此事件。了解事件订阅的配置流程和使用场景，参考[事件概述](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)。 |      |      |
| [多维表格字段变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/drive-v1/file/events/bitable_field_changed)drive.file.bitable_field_changed_v1 | 多维表格字段变更事件。被订阅的多维表格字段发生变更时，将会触发此事件。了解事件订阅的配置流程和使用场景，参考[事件概述](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)。 |      |      |

| 日历                                                         |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [日历变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/calendar-v4/calendar/events/changed)calendar.calendar.changed_v4 | 当用户订阅日历变更事件后，如果用户日历列表内发生了日历变动，则会触发该事件。 |      |      |
| [创建 ACL](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/calendar-v4/calendar-acl/events/created)calendar.calendar.acl.created_v4 | 当订阅的日历上有访问控制被创建时，将会触发此事件。           |      |      |
| [删除 ACL](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/calendar-v4/calendar-acl/events/deleted)calendar.calendar.acl.deleted_v4 | 当订阅的日历上有访问控制被删除时，将会触发此事件。           |      |      |
| [日程变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/calendar-v4/calendar-event/events/changed)calendar.calendar.event.changed_v4 | 当用户订阅日程变更事件后，被订阅的日历下有日程发生变更时，将会触发该事件。 |      |      |

| 视频会议                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [企业会议开始](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/all_meeting_started)vc.meeting.all_meeting_started_v1 | 发生在会议开始时，包含企业内所有会议开始事件。               |      |      |
| [企业会议结束](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/all_meeting_ended)vc.meeting.all_meeting_ended_v1 | 发生在会议结束时，包含企业内所有会议结束事件。               |      |      |
| [会议开始](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/meeting_started)vc.meeting.meeting_started_v1 | 发生在会议开始时【仅通过Open API预约的会议会产生此类事件】   |      |      |
| [会议结束](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/meeting_ended)vc.meeting.meeting_ended_v1 | 发生在会议结束时【仅通过Open API预约的会议会产生此类事件】   |      |      |
| [加入会议](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/join_meeting)vc.meeting.join_meeting_v1 | 发生在有人加入会议时【仅通过Open API预约的会议会产生此类事件】 |      |      |
| [离开会议](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/leave_meeting)vc.meeting.leave_meeting_v1 | 发生在有人离开会议时【仅通过Open API预约的会议会产生此类事件】 |      |      |
| [开始录制](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/recording_started)vc.meeting.recording_started_v1 | 发生在开始录制时【仅通过Open API预约的会议会产生此类事件】   |      |      |
| [停止录制](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/recording_ended)vc.meeting.recording_ended_v1 | 发生在录制结束时【仅通过Open API预约的会议会产生此类事件】   |      |      |
| [录制完成](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/recording_ready)vc.meeting.recording_ready_v1 | 发生在录制文件上传完毕时【仅通过Open API预约的会议会产生此类事件】 |      |      |
| [开始屏幕共享](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/share_started)vc.meeting.share_started_v1 | 发生在屏幕共享开始时【仅通过Open API预约的会议会产生此类事件】 |      |      |
| [结束屏幕共享](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/meeting/events/share_ended)vc.meeting.share_ended_v1 | 发生在屏幕共享结束时【仅通过Open API预约的会议会产生此类事件】 |      |      |
| [创建会议室层级](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/room_level/events/created)vc.room_level.created_v1 | 当创建会议室层级时，会触发该事件。                           |      |      |
| [删除会议室层级](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/room_level/events/deleted)vc.room_level.deleted_v1 | 当删除会议室层级时，会触发该事件。                           |      |      |
| [更新会议室层级](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/room_level/events/updated)vc.room_level.updated_v1 | 当更新会议室层级时，会触发该事件。                           |      |      |
| [创建会议室](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/room/events/created)vc.room.created_v1 | 当创建会议室时，会触发该事件。                               |      |      |
| [更新会议室](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/room/events/updated)vc.room.updated_v1 | 当更新会议室时，会触发该事件。                               |      |      |
| [删除会议室](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/room/events/deleted)vc.room.deleted_v1 | 当删除会议室时，会触发该事件。                               |      |      |
| [更新会议室预定限制](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/vc-v1/reserve_config/events/updated)vc.reserve_config.updated_v1 | 当更新会议室预定限制时，会触发该事件。                       |      |      |

| 会议室                                                       |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [会议室状态信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/meeting_room-v1/meeting_room/events/status_changed)meeting_room.meeting_room.status_changed_v1 | 会议室被创建、更新、删除或者被预定时，将会触发此事件。       |      |      |
| [第三方会议室日程变动](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/meeting_room-v1/event/third-room-event-changes)third_party_meeting_room_event_created | 当添加了第三方会议室的日程发生变动时（创建/更新/删除）触发此事件。 |      |      |
| [会议室创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/meeting_room-v1/meeting_room/events/created)meeting_room.meeting_room.created_v1 | 会议室被创建将触发此事件。                                   |      |      |
| [会议室属性变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/meeting_room-v1/meeting_room/events/updated)meeting_room.meeting_room.updated_v1 | 会议室属性更新将触发此事件。                                 |      |      |
| [会议室删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/meeting_room-v1/meeting_room/events/deleted)meeting_room.meeting_room.deleted_v1 | 会议室被删除将触发此事件。                                   |      |      |

| 审批                                                         |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [审批定义更新](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/custom-approval-event)approval.approval.updated_v4 | 「审批」定义更新时触发此事件。                               |      |      |
| [外出审批](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/out-of-office)out_approval | 「审批」应用的表单里如果包含 外出控件组，则在此表单审批通过后触发此事件。 |      |      |
| [出差审批](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/business-trip)trip_approval | 「审批」应用的表单里如果包含 出差控件组，则在此表单审批通过后触发此事件。 |      |      |
| [补卡审批](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/attendance-record-correction)remedy_approval | 补卡申请审批通过后触发此事件。 你可以在「打卡」应用里提交补卡申请。 |      |      |
| [换班审批](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/shift-change)shift_approval | 换班申请审批通过后触发此事件。 你可以在「打卡」应用里提交换班申请。 |      |      |
| [加班审批](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/overtime)work_approval | 「审批」应用的表单里如果包含 加班控件组，则在此表单审批通过后触发此事件。 |      |      |
| [请假审批](https://open.feishu.cn/document/ukTMukTMukTM/uIDO24iM4YjLygjN/event/leave)leave_approvalV2 | 「审批」应用的表单里如果包含 请假控件组，则在此表单审批通过后触发此事件。 |      |      |

| 服务台                                                       |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [创建工单](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/ticket/events/created)helpdesk.ticket.created_v1 | 可监听服务台的工单创建事件。需使用订阅接口订阅：[事件订阅](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/event/subscribe) |      |      |
| [工单状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/ticket/events/updated)helpdesk.ticket.updated_v1 | 可监听工单状态和阶段变更事件。需使用订阅接口订阅：[事件订阅](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/event/subscribe)。如果你需要监听工单的阶段变更，可以使用该事件。例如，使用该事件监听工单阶段由机器人变更为人工。 |      |      |
| [工单消息事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/ticket_message/events/created)helpdesk.ticket_message.created_v1 | 该消息事件属于工单消息事件。需使用订阅接口订阅：[事件订阅](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/event/subscribe)。 |      |      |
| [推送审核通知](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/helpdesk-v1/notification/events/approve)helpdesk.notification.approve_v1 | 推送审核状态通知事件。                                       |      |      |

| 任务                                                         |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [任务信息变更（租户维度）](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/task-v1/task/events/update_tenant)task.task.update_tenant_v1 | APP 订阅此事件后可接收到该 APP 所在租户的所有来源接口创建的任务的变更事件。事件体为发生变更任务的相关用户的 open_id，可用此 open_id ，通过 获取任务列表接口获取与该用户相关的所有任务。 |      |      |
| [任务信息变更（应用维度）](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/task-v1/task/events/updated)task.task.updated_v1 | 当 APP 订阅此事件后可以接收到由该 APP 创建的任务发生的变更，包括任务标题、描述、截止时间、协作者、关注者、提醒时间、状态（完成或取消完成）。**特别注意**: 订阅该事件只能接收到该 APP 创建的任务发生的变更，如果订阅后未收到事件，可以检查是否是下面几种不会推送的情况:任务是user_access_token方式创建或者其他应用创建的。任务是通过客户端或者文档创建的。 |      |      |
| [任务评论信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/task-v1/task-comment/events/updated)task.task.comment.updated_v1 | 当 APP 创建的任务评论信息发生变更时触发此事件，包括任务评论的创建、回复、更新、删除。**特别注意**: 订阅该事件只能接收到该 APP 创建的任务发生的评论信息变更，如果订阅后未收到事件，可以检查是否是下面几种不会推送的情况:任务是user_access_token方式创建或者其他应用创建的。任务是通过客户端或者文档创建的。 |      |      |

| 邮箱                                                         |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [收信通知](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/mail-v1/user_mailbox-event/events/message_received)mail.user_mailbox.event.message_received_v1 | 前提条件你需要在应用中配置事件订阅，这样才可以在事件触发时接收到事件数据。了解事件订阅可参见 [事件概述](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)。 |      |      |

| 应用信息                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [机器人自定义菜单事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/bot/events/menu)application.bot.menu_v6 | 当用户点击类型为事件的机器人菜单时触发                       |      |      |
| [新增应用反馈](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/application-feedback/events/created)application.application.feedback.created_v6 | 当应用收到新反馈时，触发该事件                               |      |      |
| [反馈更新](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/application-feedback/events/updated)application.application.feedback.updated_v6 | 当反馈的处理状态被更新时，触发该事件                         |      |      |
| [应用创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/application/events/created)application.application.created_v6 | 当企业内有新的自建应用被创建时推送此事件（创建就会产生此事件，不需要发版） |      |      |
| [首次启用应用](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/event/app-first-enabled)app_open | 当租户第一次安装并启用此应用时触发此事件。                   |      |      |
| [应用停启用](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/event/app-enabled-or-disabled)app_status_change | 当企业管理员在管理员后台启用、停用应用，或应用被平台停用时，开放平台推送 app_status_change 事件到请求网址。 |      |      |
| [应用商店应用购买](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/event/public-app-purchase)order_paid | 用户购买应用商店付费应用成功后发送给应用ISV的通知事件。      |      |      |
| [app_ticket 事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/event/app_ticket-events)app_ticket | 对于应用商店应用，开放平台会每隔1小时推送一次 app_ticket ，应用通过该 app_ticket 获取 app_access_token。 |      |      |
| [应用卸载](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/event/app-uninstalled)app_uninstalled | 企业解散后会推送此事件。商店应用开发者可在收到此事件后进行相应的账户注销、数据清理等处理。自建应用无此事件。 |      |      |
| [员工免审安装应用](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/event/app-availability-scope-extended)application.application.visibility.added_v6 | 仅当企业的用户通过「普通成员安装」方式获得应用可用性时推送此事件。 |      |      |
| [申请发布应用](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/application-app_version/events/publish_apply)application.application.app_version.publish_apply_v6 | 通过订阅该事件，可接收应用提交发布申请事件                   |      |      |
| [撤回应用发布申请](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/application-app_version/events/publish_revoke)application.application.app_version.publish_revoke_v6 | 通过订阅该事件，可接收应用撤回发布申请事件                   |      |      |
| [应用审核](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/application-v6/application-app_version/events/audit)application.application.app_version.audit_v6 | 通过订阅该事件，可接收应用审核（通过 / 拒绝）事件            |      |      |

| 招聘                                                         |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [人才进展变更事件](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/talent/events/tag_subscription)hire.talent.tag_subscription_v1 | 支持单独订阅有指定标签的人才进展，人才进展包括阶段变更、锁定、解锁，需要提前在「飞书招聘」-「设置」- 「候选人标签管理」里对指定标签勾选支持事件订阅 |      |      |
| [删除人才](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/talent/events/deleted)hire.talent.deleted_v1 | 当人才被删除时，触发该事件。                                 |      |      |
| [删除投递](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/application/events/deleted)hire.application.deleted_v1 | 当投递被删除时，触发该事件的推送。                           |      |      |
| [投递阶段变更](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/application/events/stage_changed)hire.application.stage_changed_v1 | 当投递阶段发生变更时，会触发此事件。了解事件订阅的使用场景和配置流程，请点击查看 [事件订阅概述](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)。 |      |      |
| [Offer 状态变更](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/offer/events/status_changed)hire.offer.status_changed_v1 | 当 Offer 状态发生变更时发送该事件。除 Offer 创建时不会发送以外，其它 Offer 状态变更均会发送事件，Offer 状态变更场景可参考「Offer 状态流转图」。注意：仅推送正式 Offer 的状态变更信息，实习 Offer 相关状态不推送。 |      |      |
| [导入 e-HR](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/ehr_import_task/events/imported)hire.ehr_import_task.imported_v1 | 当用户在招聘系统中对候选人的投递操作「导入 e-HR」后，将会触发该事件，推送候选人信息至订阅系统。如需接收到该事件，则需先配置事件订阅。详情参考 [事件订阅概述](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)。 |      |      |
| [导入 e-HR（实习 Offer）](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/ehr_import_task_for_internship_offer/events/imported)hire.ehr_import_task_for_internship_offer.imported_v1 | 飞书招聘系统内用户选择实习 Offer 导入 e-HR 系统之后，将通过该事件推送候选人信息。 |      |      |
| [账号绑定](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_account/events/created)hire.eco_account.created_v1 | 飞书招聘客户在「飞书招聘」-「设置」-「生态对接」-「笔试/背景调查」添加三方服务商账号时，系统会推送「账号绑定」事件给服务商。服务商可通过本事件获取客户添加的**账号类型**、**飞书招聘账号 ID** 和 **账号自定义字段信息**，并根据这些信息识别出客户在服务商处的身份，从而完成客户的服务商账号和飞书招聘账号之间的绑定。之后服务商可依据账号绑定关系向客户推送对应的背调套餐或试卷列表。 |      |      |
| [创建背调](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_background_check/events/created)hire.eco_background_check.created_v1 | 飞书招聘客户在招聘系统给候选人安排背调后，系统会推送「创建背调」事件给对应的背调服务商。服务商可根据此事件获取该背调的候选人、委托人和自定义字段等信息，并根据这些信息完成内部的背调订单的创建和绑定，之后可通过[更新背调订单进度](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_background_check/update_progress)、[回传背调订单的最终结果](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_background_check/update_result)将背调信息回传给招聘系统。 |      |      |
| [终止背调](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_background_check/events/canceled)hire.eco_background_check.canceled_v1 | 飞书招聘客户在招聘系统内终止背调后，系统会推送「终止背调」事件给对应的背调服务商，服务商可根据此事件获取背调 ID，完成服务商内部的订单取消等后续操作。 |      |      |
| [创建笔试](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_exam/events/created)hire.eco_exam.created_v1 | 飞书招聘客户在招聘系统安排笔试后，系统会推送「创建笔试」事件给对应的笔试服务商应用。服务商可根据此事件获取该场笔试的候选人信息和试卷信息，并根据这些信息为候选人安排笔试，之后可通过[回传笔试安排结果](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/eco_exam/login_info)将笔试安排结果回传给招聘系统。 |      |      |
| [内推账户余额变更](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/referral_account/events/assets_update)hire.referral_account.assets_update_v1 | 当内推账户余额发生变更（增加或者减少）时，触发该事件。该事件将推送变更后的账户余额信息。收到事件后，如需将余额提现到三方平台发放给用户，请使用接口 [全额提取内推账户余额](https://open.feishu.cn/document/ukTMukTMukTM/uMzM1YjLzMTN24yMzUjN/hire-v1/referral_account/withdraw)。 |      |      |

| 智能门禁                                                     |                                              |      |      |
| ------------------------------------------------------------ | -------------------------------------------- | ---- | ---- |
| [用户信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/acs-v1/user/events/updated)acs.user.updated_v1 | 智能门禁用户特征值变化时，发送此事件。       |      |      |
| [新增门禁访问记录](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/acs-v1/access_record/events/created)acs.access_record.created_v1 | 门禁设备识别用户成功后发送该事件给订阅应用。 |      |      |

| 绩效                                                         |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [绩效结果开通](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/performance-v2/stage_task/events/open_result)performance.stage_task.open_result_v2 | 当员工的绩效结果开通时，订阅这个事件的应用会收到该事件。     |      |      |
| [绩效详情变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/performance-v2/review_data/events/changed)performance.review_data.changed_v2 | 当员工的绩效详情发生变更时，订阅这个事件的应用会收到该事件。 |      |      |

| 飞书人事                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [元数据信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/common_data-meta_data/events/updated)corehr.common_data.meta_data.updated_v1 | People元数据定义变更会对外推送事件。例如在People系统中，设置-人员档案配置-个人信息-基本信息 中添加一个字段。就会收到person相关的元数据变更推送。可通过[获取飞书人事对象列表](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/custom_field/list_object_api_name)查询对象列表，包括了预置对象的字段变更以及自定义对象的字段变更，不保证顺序，所以要使用的话当监听到变更事件后需要判断是否关心该对象然后查询对象的字段来做业务逻辑。 |      |      |
| [用户ID映射变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/common_data-id/events/user_mapping_changed)corehr.common_data.id.user_mapping_changed_v1 | 用户ID映射变更事件                                           |      |      |
| [【事件】个人信息创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/person/events/created)corehr.person.created_v1 | 目前以下场景会触发该事件：调用[【创建个人信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/person/create)、[【添加人员】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/employee/create)接口人事系统【添加人员】、【导入人员】功能 |      |      |
| [【事件】更新个人信息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/person/events/updated)corehr.person.updated_v1 | 员工个人信息发生变更时发送该事件，场景举例：调用[【更新个人信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/person/patch)接口人事系统【编辑个人信息】、【导入编辑人员】功能计算字段变更注：籍贯、政治面貌、户口类型、户口所在地变化不会触发该事件 |      |      |
| [【事件】个人信息删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/person/events/deleted)corehr.person.deleted_v1 | 个人信息删除                                                 |      |      |
| [【事件】创建雇佣信息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/events/created)corehr.employment.created_v1 | 员工雇佣信息被创建时发送该事件，场景举例：调用[【创建雇佣信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/create)、[【添加人员】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/employee/create)接口人事系统【添加人员】、【导入人员】功能 |      |      |
| [【事件】更新雇佣信息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/events/updated)corehr.employment.updated_v1 | 员工雇佣信息变更时发送该事件，场景举例：调用[【更新雇佣信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/patch)接口人事系统【编辑工作信息】、【导入编辑人员】功能计算字段变更 |      |      |
| [【事件】删除雇佣信息](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/events/deleted)corehr.employment.deleted_v1 | 员工在飞书人事的「雇佣信息被删除」时将触发此事件。           |      |      |
| [任职信息创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/events/created)corehr.job_data.created_v1 | 目前以下场景会触发该事件：调用[【创建任职信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/create)、[【更新任职信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/patch)、[【添加人员】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/employee/create)接口人事系统【添加人员】、【发起异动】、【导入任职】、【创建兼职】功能 |      |      |
| [任职信息删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/events/deleted)corehr.job_data.deleted_v1 | 目前以下场景会触发事件：调用[【删除任职信息】](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/delete)接口人事系统【删除任职】【删除兼职】功能 |      |      |
| [任职信息更新](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/events/updated)corehr.job_data.updated_v1 | 目前以下场景会触发该事件：人事系统【编辑任职】【编辑兼职】【导入编辑任职】【发起异动】功能仅对于当前生效的任职记录数据 |      |      |
| [创建部门](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/department/events/created)corehr.department.created_v1 | 飞书人事中「部门被创建」时将触发此事件。                     |      |      |
| [更新部门](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/department/events/updated)corehr.department.updated_v1 | 飞书人事中「部门信息被更新」时将触发此事件。                 |      |      |
| [删除部门](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/department/events/deleted)corehr.department.deleted_v1 | 飞书人事中「部门被删除」时将触发此事件。                     |      |      |
| [创建职务](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job/events/created)corehr.job.created_v1 | 飞书人事中「职务被创建」时将触发此事件。注意：触发时间为职务实际生效时间，如在 2022-01-01 创建职务，职务生效时间设置为 2022-05-01，事件将在 2022-05-01 进行推送。 |      |      |
| [更新职务](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job/events/updated)corehr.job.updated_v1 | 飞书人事中「职务信息被更新」时将触发此事件。注意：触发时间为职务实际生效时间，如在 2022-01-01 更新职务，职务生效时间设置为 2022-05-01，事件将在 2022-05-01 进行推送。 |      |      |
| [删除职务](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job/events/deleted)corehr.job.deleted_v1 | 飞书人事中「职务被删除」时将触发此事件。                     |      |      |
| [入职信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/pre_hire/events/updated)corehr.pre_hire.updated_v1 | 待入职人员任职信息更新后，触发此事件，包括两种场景：通过开放平台接口创建待入职、更新待入职在飞书人事-入职系统，HR 补充任职信息如果有创建待入职后，更新数据的场景，请收到创建事件后延迟10s时间再执行更新操作 |      |      |
| [员工完成入职](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/events/employed)corehr.job_data.employed_v1 | 以下业务场景会触发此事件：开放平台[操作员工完成入职](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/pre_hire/complete)接口开放平台[添加人员](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/employee/create)接口「飞书人事-人员管理-入职」将待入职员工操作“完成入职”「飞书人事-人员管理-花名册」操作”添加人员”或”导入人员” |      |      |
| [员工完成转正](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/events/converted)corehr.employment.converted_v1 | 当员工转正生效时触发该事件                                   |      |      |
| [员工完成异动](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_data/events/changed)corehr.job_data.changed_v1 | 员工在飞书人事异动生效后（到达异动生效时间）将触发该事件。   |      |      |
| [异动状态变更（不推荐）](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/job_change/events/updated)corehr.job_change.updated_v1 | 在异动审批状态变更、异动生效时都会触发该事件，审批结果产生的场景包括撤销、审批通过、审批拒绝。本事件没有数据范围鉴权。 |      |      |
| [合同创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/contract/events/created)corehr.contract.created_v1 | 通过开放平台创建合同或飞书人事系统中员工新签一份合同时，会触发合同创建事件 |      |      |
| [合同删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/contract/events/deleted)corehr.contract.deleted_v1 | 通过开放平台删除合同时，会触发该事件。注意：删除后，无法通过搜索接口查询到合同信息。 |      |      |
| [合同更新](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/contract/events/updated)corehr.contract.updated_v1 | 通过开放平台更新合同或者在飞书人事系统进行变更和续约等业务操作时，会触发本事件 |      |      |
| [组织角色授权变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/org_role_authorization/events/updated)corehr.org_role_authorization.updated_v1 | 当组织上的角色授权发生变更时，触发该事件。例如在部门上修改了角色，并在 2030-01-01 年生效，则事件将在 2030-01-01 触发。注意：当前事件只返回在飞书人事中组织角色的变化，下游组织的影响，可以通过 「获取组织类角色授权列表」获取。 |      |      |
| [员工完成离职](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/employment/events/resigned)corehr.employment.resigned_v1 | 员工完成离职，即离职日期的次日凌晨时，员工雇佣状态更改为“离职”后触发该事件。 |      |      |
| [离职申请状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/offboarding/events/updated)corehr.offboarding.updated_v1 | 在发起离职审批、产生审批结果、离职生效、离职状态回退等离职申请状态变更时触发该事件推送对应消息。审批结果产生的场景包括撤销、通过、拒绝审批。 |      |      |

| 飞书人事（企业版）                                           |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [人员信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/employee/events/domain_event)corehr.employee.domain_event_v2 | 人员领域事件变更，通过业务界面、开放平台接口对个人信息、工作信息（雇佣信息）、任职信息、兼职信息等进行操作时会触发相应事件 |      |      |
| [创建部门V2](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/department/events/created)corehr.department.created_v2 | 飞书人事中「部门被创建」时将触发此事件。                     |      |      |
| [更新部门V2](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/department/events/updated)corehr.department.updated_v2 | 飞书人事中「部门信息被更新」时将触发此事件。                 |      |      |
| [删除地点](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/location/events/deleted)corehr.location.deleted_v2 | 飞书人事中「地点被删除」时将触发此事件。                     |      |      |
| [更新地点](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/location/events/updated)corehr.location.updated_v2 | 飞书人事中「地点被更新」时将触发此事件。                     |      |      |
| [创建地点](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/location/events/created)corehr.location.created_v2 | 飞书人事中「地点被创建」时将触发此事件。                     |      |      |
| [删除公司](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/company/events/deleted)corehr.company.deleted_v2 | 飞书人事中「公司被删除」时将触发此事件。                     |      |      |
| [更新公司](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/company/events/updated)corehr.company.updated_v2 | 飞书人事中「公司被更新」时将触发此事件。                     |      |      |
| [创建公司](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/company/events/created)corehr.company.created_v2 | 飞书人事中「公司被创建」时将触发此事件。                     |      |      |
| [创建成本中心](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/cost_center/events/created)corehr.cost_center.created_v2 | 飞书人事中「成本中心被创建」时将触发此事件。                 |      |      |
| [更新成本中心](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/cost_center/events/updated)corehr.cost_center.updated_v2 | 飞书人事中「成本中心信息被更新」时将触发此事件。             |      |      |
| [删除成本中心](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/cost_center/events/deleted)corehr.cost_center.deleted_v2 | 飞书人事中「成本中心被删除」时将触发此事件。                 |      |      |
| [自定义组织被创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/custom_org/events/created)corehr.custom_org.created_v2 | 飞书人事中「自定义组织被创建」时将触发此事件。               |      |      |
| [自定义组织被更新](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/custom_org/events/updated)corehr.custom_org.updated_v2 | 飞书人事中「自定义组织被更新」时将触发此事件。               |      |      |
| [自定义组织被删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/custom_org/events/deleted)corehr.custom_org.deleted_v2 | 飞书人事中「自定义组织被删除」时将触发此事件。               |      |      |
| [组织架构调整状态变更事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/approval_groups/events/updated)corehr.approval_groups.updated_v2 | 当用户在『飞书人事-我的团队/人员管理-组织架构』，查看调整链接可以获取到 该用户发起的所有组织架构调整， 进入可找到审批流程。当该审批单状态发生变更后， 用户会收到流程状态变更事件。延迟说明：数据库主从延迟2s以内，即：用户接收到流程状态变更消息后2s内调用查询状态接口可能查不到变更信息。前提条件你需要在应用中配置事件订阅，这样才可以在事件触发时接收到事件数据。了解事件订阅可参见[事件订阅概述](https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM)。 |      |      |
| [创建序列](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_family/events/created)corehr.job_family.created_v2 | 飞书人事中「序列被创建」时将触发此事件。                     |      |      |
| [更新序列](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_family/events/updated)corehr.job_family.updated_v2 | 飞书人事中「序列信息被更新」时将触发此事件。                 |      |      |
| [删除序列](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_family/events/deleted)corehr.job_family.deleted_v2 | 飞书人事中「序列被删除」时将触发此事件。                     |      |      |
| [删除职级](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_level/events/deleted)corehr.job_level.deleted_v2 | 飞书人事中「职级被删除」时将触发此事件。                     |      |      |
| [更新职级](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_level/events/updated)corehr.job_level.updated_v2 | 飞书人事中「职级信息被更新」时将触发此事件。                 |      |      |
| [创建职级](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_level/events/created)corehr.job_level.created_v2 | 飞书人事中「职级被创建」时将触发此事件。                     |      |      |
| [删除职等](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_grade/events/deleted)corehr.job_grade.deleted_v2 | 飞书人事中「职等被删除」时将触发此事件。                     |      |      |
| [更新职等](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_grade/events/updated)corehr.job_grade.updated_v2 | 飞书人事中「职等被更新」时将触发此事件。                     |      |      |
| [创建职等](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_grade/events/created)corehr.job_grade.created_v2 | 飞书人事中「职等被创建」时将触发此事件。                     |      |      |
| [通道创建](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/pathway/events/created)corehr.pathway.created_v2 | 通道创建后会发送该事件                                       |      |      |
| [通道更新](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/pathway/events/updated)corehr.pathway.updated_v2 | 通道更新后会发送该事件                                       |      |      |
| [通道删除](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/pathway/events/deleted)corehr.pathway.deleted_v2 | 通道删除后会发送该事件                                       |      |      |
| [创建岗位事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/position/events/created)corehr.position.created_v2 | 飞书人事中「岗位被创建」时将触发此事件。注意：触发时间为岗位实际生效时间，如在 2022-01-01 创建岗位，岗位生效时间设置为 2022-05-01，事件将在 2022-05-01 进行推送。 |      |      |
| [更新岗位事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/position/events/updated)corehr.position.updated_v2 | 飞书人事中「岗位信息被更新」时将触发此事件。注意：触发时间为岗位更新实际生效时间，如在 2022-01-01 更新岗位，岗位更新生效时间设置为 2022-05-01，事件将在 2022-05-01 进行推送。 |      |      |
| [删除岗位事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/position/events/deleted)corehr.position.deleted_v2 | 飞书人事中「岗位被删除」时将触发此事件。                     |      |      |
| [入职流程状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/pre_hire/events/onboarding_task_changed)corehr.pre_hire.onboarding_task_changed_v2 | 待入职员工的入职流程流转时，例如调用[流转入职任务](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/pre_hire/transit_task)接口会触发本事件。 |      |      |
| [试用期状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/probation/events/updated)corehr.probation.updated_v2 | 当试用期记录状态发生变更时，触发该事件。                     |      |      |
| [异动状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_change/events/status_updated)corehr.job_change.status_updated_v2 | 在异动审批状态变更、异动生效时都会触发该事件，审批结果产生的场景包括撤销、审批通过、审批拒绝 |      |      |
| [异动信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/job_change/events/updated)corehr.job_change.updated_v2 | 员工发起异动后，异动信息变更会触发该事件                     |      |      |
| [离职信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/offboarding/events/updated)corehr.offboarding.updated_v2 | 当员工的离职信息变更会发送消息。例如在 [离职管理](https://people.feishu.cn/people/members/dimission/management) > 离职详情页 > 编辑 中修改了离职信息，该事件会推送对应变更的消息。 |      |      |
| [离职申请状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/offboarding/events/status_updated)corehr.offboarding.status_updated_v2 | 在发起离职审批、产生审批结果、离职生效、离职状态回退等离职申请状态变更时触发该事件推送对应消息。审批结果产生的场景包括撤销、通过、拒绝审批。与原事件[离职申请状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/corehr-v1/offboarding/events/updated)相比，该事件多了直接离职产生的事件，且支持「员工数据」范围控制 |      |      |
| [离职流转状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/offboarding/events/checklist_updated)corehr.offboarding.checklist_updated_v2 | 离职流转流程的状态变更消息，当离职流转流程发起和产生审批结果时，会触发该事件。离职流转流程是在离职申请审批通过之后发起的流程，一般用于审批核实离职员工的交接事宜。 |      |      |
| [电子签文件状态发生变更事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/signature_file/events/status_updated)corehr.signature_file.status_updated_v2 | 当电子签文件状态发生变更的时候，会推送变更事件，包含文件变更前后的状态等信息 |      |      |
| [流程实例状态变化](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/process-status/events/update)corehr.process.status.update_v2 | 流程实例是指用户发起的具体流程(process_id是其唯一标识)，流程实例状态变化时会触发该事件（此功能不受数据权限范围控制）。 |      |      |
| [流程实例信息变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/process/events/updated)corehr.process.updated_v2 | 流程实例是指用户发起的具体流程(process_id是其唯一标识)，流程实例在以下时机会触发信息变更事件：流程中有审批人操作、流程数据更新、流程状态变化等。注意事项：若节点中有多个人时，可能会同时触发多个事件。例如流程运行到该节点，同时为多个人都生成了待办任务，就会导致触发多次事件（此功能不受数据权限范围控制）。 |      |      |
| [流程节点状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/process-node/events/updated)corehr.process.node.updated_v2 | 流程中节点状态发生变化会触发该事件。配置的节点为节点定义（node_definition_id 是唯一标识）。在流程实例中，每个流程实例生成的节点实例会不同（此功能不受数据权限范围控制）。 |      |      |
| [审批任务状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/process-approver/events/updated)corehr.process.approver.updated_v2 | 单个审批任务的状态变化会触发该事件。例如，审批任务从待办变为已完成。审批任务（approver_id 是唯一标识），比如一个多人会签节点，会分别生成多人的审批任务（此功能不受数据权限范围控制）。 |      |      |
| [抄送单据状态变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/process-cc/events/updated)corehr.process.cc.updated_v2 | 流程中生成抄送单据后会触发该事件。抄送节点会生成抄送单据任务。如果一个节点有多个人抄送人，则会生成多个抄送单据（此功能不受数据权限范围控制）。 |      |      |
| [流程下评论事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/corehr-v2/process_comment_info/events/updated)corehr.process_comment_info.updated_v2 | 流程新增评论时会触发该事件，该事件包含评论所在的流程ID（process_id是其唯一标识）和评论唯一ID（comment_id）,此功能不受数据权限范围控制 |      |      |

| eLearning                                                    |                        |      |      |
| ------------------------------------------------------------ | ---------------------- | ---- | ---- |
| [课程学习进度新增事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/elearning-v2/course_registration/events/created)elearning.course_registration.created_v2 | 课程学习进度新增时触发 |      |      |
| [课程学习进度更新事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/elearning-v2/course_registration/events/updated)elearning.course_registration.updated_v2 | 课程学习进度更新时触发 |      |      |
| [课程学习进度删除事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/elearning-v2/course_registration/events/deleted)elearning.course_registration.deleted_v2 | 课程学习进度删除时触发 |      |      |

| 公司圈                                                       |                                      |      |      |
| ------------------------------------------------------------ | ------------------------------------ | ---- | ---- |
| [发布帖子](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/post/events/created)moments.post.created_v1 | 公司圈用户发布帖子时触发此事件。     |      |      |
| [删除帖子](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/post/events/deleted)moments.post.deleted_v1 | 公司圈用户删除帖子时触发此事件。     |      |      |
| [发布评论](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/comment/events/created)moments.comment.created_v1 | 公司圈用户发布评论时触发此事件。     |      |      |
| [删除评论](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/comment/events/deleted)moments.comment.deleted_v1 | 公司圈用户删除评论时触发此事件。     |      |      |
| [表情互动](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/reaction/events/created)moments.reaction.created_v1 | 公司圈用户表情互动时触发此事件。     |      |      |
| [取消表情互动](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/reaction/events/deleted)moments.reaction.deleted_v1 | 公司圈用户取消表情互动时触发此事件。 |      |      |
| [帖子统计数据变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/moments-v1/post_statistics/events/updated)moments.post_statistics.updated_v1 | 公司圈帖子统计数据变更时触发此事件。 |      |      |

| 安全合规                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [设备信息变更事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/security_and_compliance-v2/device_record/events/device_change_event)security_and_compliance.device_record.device_change_event_v2 | 使用该接口，可以订阅接收设备管理变更记录通知，包含设备新增、设备删除、设备归属变更、可信状态变更、设备特征如生产序列号、硬盘序列号等相关信息发生变化时事件通知 |      |      |
| [设备申报事件](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/security_and_compliance-v2/device_apply_record/events/device_apply_event)security_and_compliance.device_apply_record.device_apply_event_v2 | 订阅此事件后，成员提交设备自主申报后会收到通知，通知包含申报设备的参数以及申报人等信息 |      |      |

| 飞书 aPaaS                                                   |                                    |      |      |
| ------------------------------------------------------------ | ---------------------------------- | ---- | ---- |
| [数据记录变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/apaas-v1/workspace/events/record_change)apaas.workspace.record_change_v1 | 当数据表记录发生变更时将触发此事件 |      |      |

| 薪酬管理                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [薪资档案变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/compensation-v1/archive/events/changed)compensation.archive.changed_v1 | 当应用订阅该事件后，如果员工薪资档案发生变更（例如，通过管理后台对员工定薪、调薪、更正或删除），则会触发该事件。 |      |      |

| Payroll                                                      |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [发薪活动变更](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/payroll-v1/payment_activity/events/status_changed)payroll.payment_activity.status_changed_v1 | 当发薪活动发生变更后，订阅这个事件的应用会收到事件。当前仅审批通过、审批撤销、跳过审批、封存、取消封存，会发送该事件。 |      |      |
| [发薪活动封存](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/payroll-v1/payment_activity/events/approved)payroll.payment_activity.approved_v1 | 当发薪活动封存后，订阅这个事件的应用会收到事件。一个发薪活动封存后，可能会向事件监听方发送多条 `activity_id` 相同的事件通知，事件监听方需要针对 `activity_id` 做好幂等处理。 |      |      |

| 历史版本                                                     |                                                              |      |      |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ---- | ---- |
| [用户状态变更](https://open.feishu.cn/document/ukTMukTMukTM/uETNz4SM1MjLxUzM//event/user-status-changed)user_status_change | 当员工的激活、暂停账号/恢复账号、操作离职时会触发此事件。此事件不依赖于任何权限。 |      |      |
| [员工变更](https://open.feishu.cn/document/ukTMukTMukTM/uETNz4SM1MjLxUzM//event/employee-change)user_add | 当员工加入企业（user_add）、离职（user_leave）、个人信息发生变化（user_update）时，推送此事件。 |      |      |
| [部门变更](https://open.feishu.cn/document/ukTMukTMukTM/uETNz4SM1MjLxUzM//event/department-update)dept_add | 当新建部门（dept_add）、删除部门（dept_delete）、修改部门（dept_update）时，推送此事件。 |      |      |
| [授权范围变更](https://open.feishu.cn/document/ukTMukTMukTM/uETNz4SM1MjLxUzM//event/scope-change)contact_scope_change | 当应用申请了 以应用身份访问通讯录 权限后，管理员可以配置应用的通讯录授权范围。 |      |      |