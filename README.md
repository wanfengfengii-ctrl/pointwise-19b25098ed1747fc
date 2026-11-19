# 澄衡载荷试验室循环核账

白班从台架接收单通道原拍，交班员分段签发，夜班在隔离库核算循环，管理者按报告原号复查端点与出处。项目使用 Python 3.11、SQLite 和标准库。

## 一天的工作

1. 试验员登记试验标识以及起止原拍，两个边界均包含在计划中。
2. 逐拍核对负载记录。每拍必须恰有一项精确读数或显式缺测。
3. 冻结完整批次，取得固定修订号。
4. 交班员用各自负责的原拍区间签发段件。相邻件尚未签发时也能独立交付，逐拍明细留在台端。
5. 夜班从固定信封接纳段件，取得本地件号和收件回执。
6. 选定本次使用的件，核对固定修订和计划覆盖。收件次序及重复列出的本地件号不影响覆盖。
7. 核算连续区间内的循环，提交逐循环账、实际选件出处及报告回执。
8. 白班更正后另行冻结。管理者在台端关闭和隔离库重开后按原号复领定稿。

## 公开接口

调用者提供两个独立 SQLite 连接。源库初始化 `RevisionStore(source_db, station)` 和 `IssueRegister(source_db, station)`，隔离库初始化 `AdmissionStore(review_db)` 和 `ReportCatalog(review_db)`。分别调用各实例的 `initialize()`。初始化可重复执行并保留既有内容。`station` 是台端稳定且唯一的名称。存储入口管理自己的 SQLite 事务，调用时使用无外部未提交事务的连接。关闭和重开连接由调用者管理。

| 操作 | 入口与结果 |
| --- | --- |
| 冻结 | `trial.freeze.freeze(revisions, TrialPlan(trial_id, first, last), observations)` 返回修订号。观测用 `Observation(slot, load)` 表示，`None` 是占用该拍的显式缺测。整数、`Fraction` 和精确数字文本均可用。 |
| 签发 | `segments.issue.issue(revisions, register, revision_id, SegmentRange(first, last))` 返回 `IssuedSegment`。`manifest.segment_id` 是固定出站号，`to_wire()` 生成可传递 JSON 对象。`IssueRegister.get(segment_id)` 可复领已签发件。 |
| 收件 | `exchange.admission.receive(admissions, wire)` 返回 `ReceiveReceipt`，其中 `local_id` 用于选件。对同一规范内容的重投返回原回执。 |
| 发布 | `reports.publication.publish(admissions, catalog, revision_id, local_ids)` 返回含 `report_id`、`ledger`、`references`、`receipt` 的不可变 `ReportSnapshot`。 |
| 复领 | `reports.readback.read(catalog, report_id)` 直接返回档案中的 `ReportSnapshot`，包含原回执。 |

`TrialPlan`、`Observation`、`SegmentRange` 分别在 `trial.plan`、`trial.observations`、`segments.ranges` 中定义。`RevisionStore.get` 可按号返回固定修订和观测，指定 `first` 和 `last` 时只读取该区间。

## 固定段件与计算

V1 信封使用 `version`、`segment_id`、`source`、`trial_id`、`revision_id`、`plan`、`span`、`payload`。`plan` 与 `span` 分别为计划和本件的两元素闭区间。`payload.valid` 的每项有 `span` 和 `platforms`，`payload.missing` 为真实缺测闭区间列表。有效片段和缺测区间分划本件范围。平台用 `[首拍, 末拍, 有理载荷文本]` 表示，有效片段保留首尾平台及段内严格极值平台。省略的有效拍位于两个已保留平台之间的单调部分。`samples/external.json` 给出独立制作的两套合法切分。收件校验信封及证据结构，使用来源声明和规范内容识别固定件。

夜班先按固定计划检查所选件的覆盖并集。合法相交范围的重复证据只使用一次，显式缺测占用已覆盖的拍。核账端跨文件合并相连的等值平台，以首拍代表，然后剔除单调路径中的内部候选。循环计算在同一连续有效区间内使用精确的三点差值。后幅差达到或超过前幅差时核销前幅差，涉及当前起点计半循环，否则计全循环。遇到显式缺测或试验结束时，剩余相邻转折计半循环。账目按起拍、止拍稳定排序。只有正幅差入账，单位为 kN。全缺测、单拍和平坦区间都可得到合法空账。

输入和覆盖错误使用带业务代码的 `ValueError`，包括 `DUPLICATE_SLOT`、`INCOMPLETE_OBSERVATIONS`、`INVALID_LOAD`、`SEGMENT_BOUNDS`、`INVALID_ENVELOPE`、`SEGMENT_CONFLICT`、`UNKNOWN_SELECTION`、`MIXED_REVISION`、`COVERAGE_GAP`、`CONFLICTING_EVIDENCE`。未知修订和报告分别用 `LookupError` 的 `REVISION_NOT_FOUND` 和 `REPORT_NOT_FOUND` 表示。报告提交失败用 `RuntimeError` 的 `REPORT_COMMIT_FAILED` 表示。报告、引用和成功回执一次提交，失败后可使用原选件重试，原有定稿仍可领取。

## 核验与演示

在项目根目录运行完整回归。`check_project.py` 由控制台在物化时提供。

```sh
python3 -B check_project.py
```

演示使用临时源库和隔离库。它真实冻结并签发样例，关闭源库后反序收件，发布后更正源修订，再重开隔离库核对定稿。`samples/expected.json` 为逐项手算账。

```sh
python3 -B demo.py
```
