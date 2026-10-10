# 60＋100＋60 m 四车道真实运行算例

本目录保存 2026-10-10 从指定 V0.12 Windows 程序包运行后挑选的 **34 个原始成果文件**。文件内容未经手工修改；本页的格式化数值直接读取 `设计结果.json`。[返回项目首页](../../README.md)。

## 桥型与输入

- 三跨：60＋100＋60 m，总长 220 m。
- 全桥 4 车道，分离两幅，每幅 2 车道、单箱单室。
- 单幅宽 9 m，全桥宽 19 m（包含幅间净距）。
- 跨中梁高 2.8 m、墩顶梁高 5.8 m，变化指数 1.8。
- 绘图人“示例演示”、学号“00000000”为展示值；相对高程不是现场实测值。
- 主计算、验算与控制内力按单幅口径，不能将表中内力再视为全桥两幅合计。

输入见 [输入参数.json](输入参数.json)，完整结果见 [设计结果.json](设计结果.json)。

## 本次结果

| 项目 | 结果 |
| --- | --- |
| 主程序状态 | `COURSE_SCOPE_COMPLETE` |
| 六类具名验算 | 6 / 6 通过 |
| 独立复核 | `CONSISTENT_WITHIN_SCOPE` |
| 数值对照 | PASS 219 / WARN 0 / FAIL 0 / ERROR 0 |
| 规则 / 覆盖 | `PARTIAL` / `PARTIAL` |
| DWG | 3 张，ODA 转换及回转语义检查通过 |
| PDF / PPT | 28 页计算书 / 23 页汇报、8 个嵌入数据工作簿 |
| 正常本地运行用时 | 173.9 s；这是本机单次记录，不是性能保证 |

## 控制值与来源

| 数值 | 本次结果 | 单位 | 设计结果 JSON 路径 |
| --- | --- | --- | --- |
| 最大负弯矩 | -401.307 | MN·m | `presentation_summary.critical_effects.negative_moment_knm` |
| 最大正弯矩 | 120.855 | MN·m | `presentation_summary.critical_effects.positive_moment_knm` |
| 最大剪力绝对值 | 22.934 | MN | `presentation_summary.critical_effects.shear_kn` |
| 平均总预应力损失 | 293.307 | MPa | `presentation_summary.prestress.total_loss_mpa` |
| 平均损失比例 | 21.026 | % | `presentation_summary.prestress.total_loss_ratio` |
| 正弯矩承载力利用率 | 0.956 | 1 | `presentation_summary.resistance.positive_flexure_utilization` |
| 负弯矩承载力利用率 | 0.963 | 1 | `presentation_summary.resistance.negative_flexure_utilization` |
| 抗剪利用率 | 0.916 | 1 | `presentation_summary.resistance.shear_utilization` |
| 施工阶段最大绝对应力 | 10.929 | MPa | `presentation_summary.construction.max_abs_stress_mpa` |
| 频遇长期活载挠度 | 30.555 | mm | `presentation_summary.service.maximum_live_deflection_mm` |
| 控制跨挠度限值 | 166.667 | mm | `presentation_summary.service.deflection_limit_mm` |

控制负弯矩坐标 x＝160 m，正弯矩坐标 x＝110 m，剪力坐标 x＝160 m。数值按当前程序的包络口径保存，剪力左右侧值详见分析数组。

最大活跃等效钢束为 22 组、每组 19 股。活跃组数沿桥长变化，这不是 22 根通长施工钢束的详图。损失比例为程序节点均值，施工应力来自简化静定悬臂模型。

## 推荐阅读顺序

1. [总体图 PDF](CAD_PDF/01_总体立面图.pdf)：跨径、平立面和相对高程。
2. [计算书 PDF](02_桥梁工程课程设计计算书.pdf)：模型、计算、验算及第 11 章复核。
3. [PPTX 汇报](03_设计汇报.pptx)：可编辑图表、表格及来源备注。
4. [复核 HTML](交叉复核/462a08e191404847b556a59fbb743c9c/交叉复核报告.html)：下载后在浏览器离线打开；GitHub 不执行仓库中的 HTML。
5. [复核 JSON](交叉复核/462a08e191404847b556a59fbb743c9c/交叉复核报告.json)：查看容差、控制误差、规则和源码哈希。
6. [计算追溯 CSV](计算追溯表.csv)和[计算数据 CSV](计算数据.csv)：查公式、中间值和沿桥长数组。

## CAD 原生与预览文件

| 图纸 | DWG | DXF | PDF |
| --- | --- | --- | --- |
| 总体布置 | [DWG](CAD_DWG/01_总体立面图.dwg) | [DXF](CAD_DXF/01_总体立面图.dxf) | [PDF](CAD_PDF/01_总体立面图.pdf) |
| 跨中横断面 | [DWG](CAD_DWG/02_跨中横断面图.dwg) | [DXF](CAD_DXF/02_跨中横断面图.dxf) | [PDF](CAD_PDF/02_跨中横断面图.pdf) |
| 墩顶横断面 | [DWG](CAD_DWG/03_墩顶横断面图.dwg) | [DXF](CAD_DXF/03_墩顶横断面图.dxf) | [PDF](CAD_PDF/03_墩顶横断面图.pdf) |

![总体布置](预览/01_总体立面图.png)

![墩顶倒角箱梁](预览/03_墩顶横断面图.png)

跨中图中“等效合力点”与箱室说明有局部拥挤，原始输出保持不变；转回检查通过不能替代人工版式检查。图纸中的下部结构与等效钢束仍是示意，不代表完成基础设计或真实分束详图。

## 文件真实性与范围

[代表文件清单.json](代表文件清单.json)记录这 34 个文件的原始相对路径、字节数与 SHA-256；[生成清单.json](生成清单.json)是此次完整运行的原始清单，包含未被选入本目录的中间文件，两者不能混用。

复核编号：`462a08e191404847b556a59fbb743c9c`。输入哈希：`ac9d10c3929c3db0e35512f6c545aa877d1649e2a7e84c83c932b5414808f677`。

六类验算通过与双程序数值一致均只对应已覆盖的课程纵向模型。逐龄期损失、完整合龙历史、空间、横向局部、锚固区和下部结构仍未验证。未选入 DOCX 的原因是 Word 实际分页未独立渲染；字体和 MathType 对象结构已检查。
