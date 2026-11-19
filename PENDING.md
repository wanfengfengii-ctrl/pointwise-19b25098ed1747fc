# 待判载荷循环复核

台端和隔离端仍使用 README.md 中的两个独立 SQLite 连接、四个存储对象和各自的 `initialize()`。原入口继续办理 V1 确定件及定稿。以下是待判版的新增调用约定。

| 操作 | 入口与结果 |
| --- | --- |
| 冻结 | `trial.freeze.freeze_pending(revisions, plan, observations)` 返回固定修订号。仍用 `TrialPlan` 和 `Observation(slot, load)`。普通精确值和 `None` 沿用 V1。待判的 `load` 用含 2～3 个精确数的元组。按有理值核对互异，例如 `"0.5"` 和 `"1/2"` 属于同一值。整版允许 0～8 个待判拍。 |
| 签段 | `segments.issue.issue_pending(revisions, register, revision_id, span)` 接受 `SegmentRange` 并返回带 `manifest.segment_id` 和 `to_wire()` 的段件。只含确定值或缺测的范围也可以是待判版段件。同一台端、修订和范围重复签发返回同一固定件。 |
| 接纳 | `exchange.admission.receive(admissions, wire)` 同样接纳待判版段件并返回 `ReceiveReceipt`。同一出站号的同一规范内容重投沿用原回执，异件拒绝。 |
| 签发 | `reports.publication.publish_pending(admissions, catalog, revision_id, local_ids, *, query=None)` 返回待判报告。 |
| 复领 | `reports.readback.read_pending(catalog, report_id)` 返回已存的待判报告及原回执，只需打开隔离档案。 |

## 段件与选件

待判段件沿用 V1 信封的顶层字段及闭区间坐标，`version` 为整数 `2`。`payload` 的内部结构可自行定义。件内证据应能独立校验，固定本件范围内的候选、真实缺测和足以按任一完整判读还原转折与平台首拍的信息。若同件内连续三拍均为确定读数且三值严格单调，中间拍的精确读数不得随件传递或用可逆编码携带。例如整段签发 `[0,"1/2",2,(0,3),6]` 时，第 2 拍读数留台，第 4 拍取 0 时仍须在第 3 拍取到幅差为 2 的转折证据。选件边界可能需要更多原拍证据，例如第 2 拍单独成为一件的边界时。

只使用本次指定的本地件号。相同件号重复列出时使用一次。按原拍顺序核对同一来源、试验、指定修订和计划。选件均须属于待判版，彼此无重叠、无缺口，覆盖整个计划，合计至多 8 个待判拍。V1 的合法相交选件仍走原发布入口。真实缺测占拍并终止该连续区间。接缝两侧值相同且物理连续时，平台归最早的原拍。

## 报告

循环沿用 `cycles.counting.Cycle(first, last, range_kn, weight)`，以全部四个字段标识，幅差和权重为 `Fraction`。报告带 `report_id`、`trial_id`、`revision_id`、按范围排好的 `references` 及 `receipt`，引用和回执的字段沿用 V1。`possible` 为全部完整判读循环集合的并集，`certain` 为交集，均为按起拍、止拍、幅差、权重排序的无重复 `Cycle` 元组。没有循环的完整判读也参与交集。

`query` 为 `None` 或有序的两个 `Cycle`。查询的起止拍须为计划内严格递增的非布尔整数，幅差须为正 `Fraction`，权重为 `Fraction(1, 2)` 或 `Fraction(1)`。允许查询可能账之外的合法循环。报告保存查询原序。查询时 `cooccurs` 为布尔值，真时 `witness` 为按原拍升序排列的 `(slot, Fraction)` 元组，覆盖所有待判拍，且用这份选值确实可得两条循环。任选一个满足条件的见证。假时 `witness` 为 `None`，省略查询时 `cooccurs` 和 `witness` 均为 `None`。

非法观测、坏件、冲突、无效覆盖和非法查询以 `ValueError` 拒绝。签段遇未知修订、复领遇未知报告沿用 `LookupError`。冻结、发行与接纳失败不留各自的新业务记录。报告、所用引用和回执同时提交，写失败沿用 `RuntimeError('REPORT_COMMIT_FAILED')`，不留报告、引用或成功回执，可用原选件重试。更正后仍可按原修订签段。重开后按报告号直接领取存值。

## 手算与交班

`pending_examples.py` 内含两套切段、分支手算和 V1 对照。`[0,5,(1,2,5),6]` 必有 `(1,4,6,1/2)`，还可能有 `(2,3,3,1)` 和 `(2,3,4,1)`。两个全循环不可同时出现，后一条与必然半循环同现时，第 3 拍取 1。`[0,5,(5,6),2,6,None,5,2]` 的两个全循环分支分别从第 2、3 拍起，幅差分别为 3、4 kN，缺测后另有 `(7,8,3,1/2)`。

`pending_workflow.py` 给出待判入口接通后的断源调用与重开复领示例，并提供 `fail_report_write(connection, table)` 为实际报告或回执表注入写失败。沿 `.pointwise-runtime.json` 的现有 `version` 和 `kind` 保留运行入口约定，`setup` 继续使用命令 argv 列表，`verify` 与 `demo` 各使用一条 argv。核验入口须运行完整原回归并实测待判流程，包括切段不变、真实缺测、拒绝坏件及无效选件、失败重试和重开读回。演示入口展示真实签发值与按号复领结果。
