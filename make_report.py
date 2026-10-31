"""Render saved experiments into a readable, auditable Chinese report."""
import csv
import json
from pathlib import Path

from simulate import CN, COPIES, COST, DBF, DECK_CODE
from run_batch import EXPERIMENTS

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / (name + ".json")).read_text(encoding="utf-8"))


def percent(value):
    return f"{value * 100:.2f}%"


def row(result, turn):
    return result["rows"][turn - 1]


def main():
    results = {name: load(name) for name, _, _ in EXPERIMENTS}
    batch = json.loads((ROOT / "batch_summary.json").read_text(encoding="utf-8"))
    lines = [
        "# 三随从恩佐斯贼：三、四、五回合启动率",
        "",
        "日期：2026-10-31。牌表来自 10 月 24 日的剑宗恩佐斯贼攻略。",
        "",
        "**这是给定策略的无干扰启动率，不是实战胜率，也不是数学最优打法的证明。**",
        "",
        "## 主结果：对手空场，攻略留牌",
        "",
        "先后手各 200,000 局。第 t 回合指该回合开始时有 t 个法力水晶；硬币、伪造币和减费另行结算。",
        "",
        "| 回合 | 先手首次启动 | 先手累计启动 | 后手首次启动 | 后手累计启动 |",
        "|---|---:|---:|---:|---:|",
    ]
    first = results["guide_first_empty"]
    second = results["guide_second_empty"]
    for t in (3, 4, 5):
        a, b = row(first, t), row(second, t)
        lines.append(f"| {t} | {percent(a['first'])} | {percent(a['cumulative'])} | {percent(b['first'])} | {percent(b['cumulative'])} |")
    lines += [
        "",
        "首次启动：恰好在该回合第一次拉出恩佐斯。累计启动：在该回合结束之前已经启动，包括更早回合。",
        f"两回合内累计启动：先手 {percent(row(first, 2)['cumulative'])}，后手 {percent(row(second, 2)['cumulative'])}。",
        "",
        "### 累计启动率的 95% Wilson 置信区间",
        "",
        "| 回合 | 先手 | 后手 |",
        "|---|---|---|",
    ]
    for t in (3, 4, 5):
        a, b = row(first, t)["cumulative_ci95"], row(second, t)["cumulative_ci95"]
        lines.append(f"| {t} | {percent(a[0])} - {percent(a[1])} | {percent(b[0])} - {percent(b[1])} |")
    lines += [
        "",
        "置信区间只描述随机抽样误差，不覆盖出牌策略、规则假设、对手行为带来的误差。",
        "",
        "## 对照实验：均为累计启动率",
        "",
        "| 实验 | 每组局数 | 先手 ≤3 | 先手 ≤4 | 先手 ≤5 | 后手 ≤3 | 后手 ≤4 | 后手 ≤5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    pairs = [
        ("攻略留牌、空场", "guide_first_empty", "guide_second_empty"),
        ("攻略留牌、对手有骨刺目标", "guide_first_target", "guide_second_target"),
        ("条件保留待发/暗影步的留牌", "cheap_first_empty", "cheap_second_empty"),
        ("地图发现按牌库张数加权", "weighted_first_empty", "weighted_second_empty"),
        ("出牌前缀搜索加深至3步", "depth3_first_empty", "depth3_second_empty"),
        ("禁用主动过牌，其他规则相同", "natural_first_empty", "natural_second_empty"),
    ]
    for label, left, right in pairs:
        a, b = results[left], results[right]
        values = [percent(row(r, t)["cumulative"]) for r in (a, b) for t in (3, 4, 5)]
        lines.append(f"| {label} | {a['n']:,} | " + " | ".join(values) + " |")
    lines += [
        "",
        "## 模型与策略",
        "",
        "- 先手起手3张，后手起手4张并在换牌后得到幸运币；每回合自然抽一张。被换走的牌不参与替换抽牌，替换完成后再洗回。",
        "- 攻略留牌：保留三个随从，以及挖掘宝藏、行骗、潜伏帷幕，包括重复的检索牌。",
        "- 对照留牌：保留三个随从、挖掘宝藏、潜伏帷幕；原始起手有检索牌时保留待发，有碎冰者时保留暗影步，不再无条件保留行骗。",
        "- 启动：合法触发幻术师亡语，手中可拉的随从只有恩佐斯。主要为碎冰者使其立即死亡，也允许自己用骨刺击杀幻术师。不把仅抽齐组件算成功。",
        "- 每次决策先用确定性搜索检查能否立即启动；否则采用补缺件、定向检索、法力效率和资源保存的经验评分，最多搜索2步不涉及随机抽牌的出牌前缀。每抽一张后重新决策。",
        "- 出牌策略只能看到手牌、场面、剩余牌张数、已经揭示的发现选项和探底结果；不能看到未揭示的牌库顺序。",
        "- 定向抽随从/法术随机选择牌库中符合条件的实体，无放回。行骗先抽法术，连击再抽随从。",
        "- 地图从牌库中发现，不是发现复制；主模型对剩余的不同卡牌名称等概率提供最多3个不同选项；另跑张数加权版本检查该抽样口径的影响。首选牌本回合打出后，才获取另一个剩余选项；交易不触发第二张。",
        "- 探底查看真实的底部3张，选择后移至顶上；没连击不立即抽。定向抽牌和交易不随意重洗整副牌。",
        "- 交易花1费，先抽顶牌，再将弯刀插入随机位置，不会抽回同一张交易牌；手中随机一个法术获得永久减1费。交易不触发连击，不消耗待发或骨刺效果。",
        "- 待发只作用于下一张法术；骨刺击杀后只作用于本回合下一张牌；碎冰者的亡语减费可跨回合并通过回手重打累加。暗影步使回手随从永久减2费。",
        "- 殒命暗影只在已经位于手中时响应施法，复制所打法术及其永久费用修改，不把待发、骨刺这类消耗型光环一并复制；未变形的暗影不能打出。",
        "- 矿锄为2费、1攻、2耐久，每回合英雄最多攻击一次，通过攻击抽牌，装备本身不抽牌。",
        "- 记录10张手牌上限及爆牌；记录随从回手、武器覆盖、奥秘不能重复挂同名等与启动有关的限制。",
        "",
        "## 必须注意的边界",
        "",
        "- 对手不打断、不斩杀、不移除我方碎冰者；英雄能正常攻击。由此得到的是金鱼测试，不是正常天梯的实际启动率。",
        "- 骨刺目标实验只是假定从第2回合起，每回合对手提供一个可被骨刺直接击杀的目标；不是对手全程送多个目标，也不是对某个职业环境的估计。空场模型仍可击杀自己的碎冰者。",
        "- 启动前不使用梦魇供能、似曾相识、美味变异鱼、托瓦格尔的阴谋，不假定偷来神牌；这些牌仍留在30张牌中，可以被普通抽牌抽到。",
        "- 不计靠对手主动击杀幻术师、随从交换、偷牌奇迹、计时器、网络延迟等获得的额外启动路线；也不模拟恩佐斯展开后的随机亡语池与斩杀。",
        "- 经验评分不是完整的多回合最优决策求解器。地图选择、探底选择、资源保存和起手留牌仍可优化。不同规则细节的验证与策略优化误差可能大于蒙特卡洛抽样误差。",
        "",
        "## 牌表快照",
        "",
        "| 卡牌 | 费用 | 数量 | dbfId |",
        "|---|---:|---:|---:|",
    ]
    for k in sorted(range(20), key=lambda k: (COST[k], k)):
        lines.append(f"| {CN[k]} | {COST[k]} | {COPIES[k]} | {DBF[k]} |")
    lines += [
        "",
        "卡组代码：",
        "",
        "```text",
        DECK_CODE,
        "```",
        "",
        "## 验证与复现",
        "",
        f"共完成 {batch['games']:,} 局、{len(batch['experiments'])} 组实验。随机种子为20261031；随机抽样使用Python标准库random.Random。",
        "30项单元测试通过。额外生成10,000个战术状态，对其中6,424个被判定能启动的状态逐步执行校验，均合法完成启动。",
        "",
        "- `simulate.py`：单组模拟，可指定`--n`、`--second`、`--enemy`、`--policy cheap`、`--weighted`、`--depth`、`--seed`。",
        "- `run_batch.py`：完整实验，最多4个本地进程。",
        "- `test_simulate.py`：规则与决策信息隔离测试。",
        "- `*_empty.json`、`*_target.json`：概率、计数、Wilson区间和首次启动样例出牌日志。",
        "- `results.csv`：各组逐回合结果汇总。",
        "- `cards_zhCN.json`、`cards_enUS.json`：取自HearthstoneJSON的卡牌文本快照。",
        "",
        "Python只使用标准库，不需要安装依赖。",
        "",
        "## 来源",
        "",
        "- [剑宗恩佐斯贼攻略与牌表](https://ds.163.com/article/6adc4ff19a24a1198dbdf6a5/)",
        "- [HearthstoneJSON 中文卡牌数据](https://api.hearthstonejson.com/v1/latest/zhCN/cards.json)",
        "- [Discover：牌库发现会抽走卡牌、选项不重复](https://hearthstone.wiki.gg/wiki/Discover)",
        "- [Tradeable：交易、抽牌与连击规则](https://hearthstone.wiki.gg/wiki/Tradeable)",
        "- [Cultist Map](https://hearthstone.wiki.gg/wiki/Cultist_Map)",
        "- [Shadow of Demise](https://hearthstone.wiki.gg/wiki/Shadow_of_Demise)",
    ]
    (ROOT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (ROOT / "results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["experiment", "n", "turn", "first_count", "first_probability", "cumulative_count", "cumulative_probability", "cumulative_ci95_low", "cumulative_ci95_high"])
        for name, r in results.items():
            for v in r["rows"]:
                writer.writerow([name, r["n"], v["turn"], v["first_count"], v["first"], v["cumulative_count"], v["cumulative"], *v["cumulative_ci95"]])
    print(ROOT / "REPORT.md")


if __name__ == "__main__":
    main()
