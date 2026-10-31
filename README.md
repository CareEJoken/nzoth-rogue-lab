# 三随从恩佐斯贼启动实验室

用可复现的蒙特卡洛模拟，分析狂野三随从恩佐斯贼的启动回合。

在线页面：https://CareEJoken.github.io/nzoth-rogue-lab/

## 使用

- 在线打开页面，或双击本地 `nzoth-lab.html`，无需安装依赖。
- 输入整数随机种子，选择先后手，逐步查看换牌、抽牌、出牌、减费和战场。
- 图表显示所选实验先后手各 200,000 局的已保存结果，不会随单局种子重新计算。
- 新增“待发组合留牌”：在攻略留牌基础上，原始起手有伺机待发 + 行骗或潜伏帷幕时，两边都留；其他出牌策略不变。
- 示例：种子 `5`、先手、攻略留牌/对手空场，在第三回合启动。

## 统计口径

启动指合法触发狗头人幻术师亡语，手牌随从池只剩恩佐斯并拉出其复制；不是仅抽齐组件，也不是斩杀。

模型不计对手干扰，采用有限搜索和经验出牌策略。结果是给定策略的无干扰启动率，不是实战胜率，也不是最优打法上限。卡牌与牌表快照日期为 2026-10-31。

详细牌表、规则、来源与统计结果见 [REPORT.md](REPORT.md)。

## 构建与验证

需要 Python 3.10+；JavaScript 校验需要 Node.js，无额外第三方依赖。

```sh
python -m unittest -q test_simulate
python build_dashboard.py
node test_dashboard.js
```

构建生成离线成品 `nzoth-lab.html` 和 Pages 入口 `docs/index.html`。
`dashboard.template.html` 是编辑用模板，直接打开会跳转到成品。

`node test_dashboard.js` 检查脚本语法、模板跳转、10 组各 200,000 局的数据、发布文件一致性及 1,540 组 Python/JavaScript 回放一致性。

新增口径可以单独复现，不必重跑旧实验：

```sh
python simulate.py --n 200000 --seed 20261031 --policy combo --out combo_first_empty.json
python simulate.py --n 200000 --seed 20261031 --policy combo --second --out combo_second_empty.json
python make_combo_cases.py
```

如需重新运行所有批量实验：

```sh
python run_batch.py
python make_report.py
python build_dashboard.py
node test_dashboard.js
```

## 更新在线页面

GitHub Pages 发布源为 `main` 分支的 `/docs` 目录。修改源码后先重新构建和验证，再提交并推送：

```sh
python build_dashboard.py
node test_dashboard.js
git add .
git commit -m "Update simulator dashboard"
git push
```

GitHub 会自动发布新版本；部署可能需要几分钟。

## 文件

- `simulate.py` / `test_simulate.py`：Python 模拟器与规则测试。
- `browser-engine.js`：浏览器模拟器，整数种子随机流与 Python 一致。
- `dashboard.template.html` / `build_dashboard.py`：页面源码与离线构建器。
- `*_first_*.json` / `*_second_*.json`：批量实验结果。
- `browser-parity-cases.json`：Python 回放校验样本。
- `browser-combo-parity-cases.json` / `make_combo_cases.py`：新增组合留牌的校验样本及生成器。
- `docs/`：独立静态发布目录，不包含模板、日志或 Python 源码。

非暴雪官方项目，相关游戏名称与卡牌内容归其权利人所有。
