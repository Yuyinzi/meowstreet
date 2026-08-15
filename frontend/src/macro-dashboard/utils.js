import { state } from "./state.js";

export function $(id) {
    return document.getElementById(id);
  }


export function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }


export function fmtStatus(value) {
    const label = String(value ?? "").replace(/_/g, " ");
    const zh = zhLabel(label);
    return zh ? `${label} / ${zh}` : label;
  }


export function fmtNumber(value) {
    if (value === null || value === undefined) return "n/a";
    return Number(value).toFixed(2);
  }


export function fmtInteger(value) {
    if (value === null || value === undefined) return "n/a";
    return Math.round(Number(value)).toLocaleString(undefined, {
      maximumFractionDigits: 0,
    });
  }


export function fmtPercent(value) {
    if (value === null || value === undefined) return "n/a";
    return `${fmtNumber(value)}%`;
  }


export function fmtCorrelationPercent(value) {
    if (value === null || value === undefined) return "n/a";
    return fmtPercent(value * 100);
  }


export function fmtDate(value) {
    return value || "n/a";
  }


export function fmtDateOnly(value) {
    if (value === null || value === undefined) return "n/a";
    return String(value).slice(0, 10);
  }


export function lineLabel(labels, key) {
    const label = labels?.[key] || key;
    const zh = zhLabel(label);
    return zh ? `${label} (${zh})` : label;
  }


export function bilingualLineLabel(labels, key) {
    const label = labels?.[key] || key;
    const zh = zhLabel(label);
    return zh ? `${escapeHtml(label)}<br><small>${escapeHtml(zh)}</small>` : escapeHtml(label);
  }


export function visibleMarketPhaseMarkets(markets) {
    return (markets || []).filter((market) => String(market.region ?? "").toUpperCase() === "US");
  }


export function statusClass(market) {
    return market.latest.market_phase_status === "bear_market" ? "bear" : "bull";
  }


export function selectedMarket() {
    return state.markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)
      || null;
  }


export function fmtRate(value) {
    if (value === null || value === undefined) return "n/a";
    return `${Number(value).toFixed(2)}%`;
  }


export function fmtUsdMillions(value) {
    if (value === null || value === undefined) return "n/a";
    const absValue = Math.abs(value);
    const sign = value < 0 ? "-" : "";
    if (absValue >= 1000000) return `${sign}$${fmtNumber(absValue / 1000000)}T`;
    if (absValue >= 1000) return `${sign}$${fmtNumber(absValue / 1000)}B`;
    return `${sign}$${fmtNumber(absValue)}M`;
  }


export function fmtSignedUsdMillions(value) {
    if (value === null || value === undefined) return "n/a";
    const formatted = fmtUsdMillions(value);
    return value > 0 ? `+${formatted}` : formatted;
  }


export function fmtPctDecimal(value) {
    if (value === null || value === undefined) return "n/a";
    return `${(Number(value) * 100).toFixed(2)}%`;
  }


export function trendArrow(value) {
    if (value === null || value === undefined) return "";
    const numericValue = Number(value);
    if (numericValue > 0) return "↑ ";
    if (numericValue < 0) return "↓ ";
    return "→ ";
  }


export function fmtSignedPctDecimal(value) {
    if (value === null || value === undefined) return "n/a";
    const numericValue = Number(value);
    const sign = numericValue > 0 ? "+" : "";
    return `${sign}${(numericValue * 100).toFixed(2)}%`;
  }


export function fmtDirectionalPct(value) {
    if (value === null || value === undefined) return "n/a";
    return `${trendArrow(value)}${fmtSignedPctDecimal(value)}`;
  }


export function fmtPercentRank(value) {
    if (value === null || value === undefined) return "n/a";
    const rank = Math.round(Number(value) * 100);
    const lastTwoDigits = rank % 100;
    if (lastTwoDigits >= 11 && lastTwoDigits <= 13) return `${rank}th`;
    const lastDigit = rank % 10;
    if (lastDigit === 1) return `${rank}st`;
    if (lastDigit === 2) return `${rank}nd`;
    if (lastDigit === 3) return `${rank}rd`;
    return `${rank}th`;
  }


export function fmtDirectionalPercentRank(value, directionValue) {
    if (value === null || value === undefined) return "n/a";
    return `${trendArrow(directionValue)}${fmtPercentRank(value)}`;
  }


export const ZH_LABELS = {
    // US Rates
    "10-Year Treasury": "10年期国债",
    "2-Year Treasury": "2年期国债",
    "10Y - 2Y Spread": "10Y-2Y利差",
    "10Y Real Rate": "10年期实际利率",
    "CPI Real Rate": "CPI实际利率",
    "Fed Funds": "联邦基金利率",
    "Breakeven": "盈亏平衡通胀率",
    "VIX": "VIX波动率指数",
    "10Y Treasury Minus CPI YoY": "10年期国债减CPI同比",
    "CPI Real Rate vs VIX": "CPI实际利率 vs VIX",
    "Real Rate": "实际利率",
    "Comparison": "对比",
    "Interpretation": "解读",
    "Yield Curve Analysis": "收益率曲线分析",
    "US Yield Curve - Comparative Analysis": "美国收益率曲线对比分析",
    "US Real Yield Curve (TIPS) - Comparative Analysis": "美国实际收益率曲线(TIPS)对比分析",

    "primary lag": "滞后期",
    "usable": "可用",
    "caution": "谨慎",
    "weak": "弱",
    "not usable": "不可用",
    "long bias": "多头偏向",
    "defensive": "防御性",
    "requires GDP forecast": "需要GDP预测",
    "Primary lag": "主要滞后期",
    "Primary": "主要",
    // Market Phase
    "Drawdown": "回撤",
    "Through": "截至",
    "Close": "收盘价",
    "Rolling High": "滚动高点",
    "Bear/Bull Level": "熊/牛市分界线",
    "Data Through": "数据截至",
    "Bull segment": "牛市区间",
    "Bear segment": "熊市区间",
    "Bear/Bull level": "熊/牛市分界线",
    "bear market": "熊市",
    "bull market": "牛市",
    // Chart defaults
    "Value": "数值",
    "Latest": "最新",
    // Credit Conditions
    "Credit Conditions": "信用环境",
    "Credit Conditions Diagnostics": "信用环境诊断",
    "BBB Credit Spread": "BBB信用利差",
    "CCC Credit Spread": "CCC信用利差",
    "CCC vs BBB Quality Spread": "CCC与BBB质量利差",
    "Data Coverage": "数据覆盖",
    "Data Gap": "数据缺口",
    "No Interpolation": "不插值",
    "BBB - 10Y": "BBB - 10年",
    "CCC - 10Y": "CCC - 10年",
    "CCC - BBB": "CCC - BBB",
    "Overall Credit Risk": "整体信用风险",
    "Quality Dispersion": "信用质量分化",
    "Healthy": "健康",
    "Weak Credit Warning": "弱信用预警",
    "Risk Rising": "风险上升",
    "Crisis Stress": "危机压力",
    "Mixed": "混合",
    "Missing": "缺失",
    "Overall": "整体",
    "Weak Credit": "弱信用",
    "Level Zone": "水平区间",
    "Full-History Percentile": "全样本历史分位",
    "1M Trend": "1个月趋势",
    "3M Trend": "3个月趋势",
    "Acceleration": "加速",
    "Very Low": "很低",
    "Normal": "正常",
    "Tightening": "开始紧张",
    "Stressed": "承压",
    "Crisis": "危机",
    "Low Dispersion": "分化很小",
    "Weak Credit Pressure": "弱信用承压",
    "Serious Deterioration": "明显恶化",
    "Elevated": "偏高",
    "Rising": "上升",
    "Falling": "下降",
    "Stable": "稳定",
    "Accelerating Up": "加速上升",
    "Accelerating Down": "加速下降",
    "No Acceleration": "未加速",
    // Growth Cycle
    "State": "状态",
    "Change": "变化",
    "Shock": "冲击",
    "YoY Growth": "同比增长",
    "3M Change": "3个月变化",
    "MoM Shock": "月度冲击",
    "M2 Level": "M2总量",
    "M2 Money Supply": "M2货币供应",
    "Cyclical Commodities & USD": "周期性大宗商品与美元",
    "M2 YoY Growth": "M2同比增长",
    "M2 3M Change": "M2三个月变化",
    "M2 MoM Shock Events": "M2月度冲击事件",
    "Shock Signal": "冲击信号",
    "Extreme Injection": "极端注入",
    "Strong Injection": "较强注入",
    "Strong Contraction": "较强收缩",
    "Extreme Contraction": "极端收缩",
    // ISM Manufacturing
    "ISM Business Cycle": "商业周期",
    "ISM Growth Drivers": "增长驱动力",
    "ISM Inflation & Supply": "通胀与供应",
    "ISM Industry Breadth": "行业广度",
    "Business Cycle": "商业周期",
    "Growth Drivers": "增长驱动力",
    "Inflation & Supply": "通胀与供应",
    "Industry Breadth": "行业广度",
    "Pending": "待完成",
    "PMI": "采购经理指数",
    "Above 50": "高于50",
    "Available drivers": "可用指标数",
    // ISM Industries
    "Computer & Electronic Products": "计算机与电子产品",
    "Wood Products": "木制品",
    "Furniture & Related Products": "家具及相关产品",
    "Machinery": "机械设备",
    "Transportation Equipment": "运输设备",
    "Food, Beverage & Tobacco Products": "食品、饮料与烟草",
    "Textile Mills": "纺织业",
    "Apparel, Leather & Allied Products": "服装、皮革及相关产品",
    "Paper Products": "造纸业",
    "Printing & Related Support Activities": "印刷及相关支持",
    "Petroleum & Coal Products": "石油与煤炭产品",
    "Chemical Products": "化工产品",
    "Plastics & Rubber Products": "塑料与橡胶制品",
    "Nonmetallic Mineral Products": "非金属矿物制品",
    "Primary Metals": "基础金属",
    "Fabricated Metal Products": "金属制品",
    "Electrical Equipment, Appliances & Components": "电气设备、家电及组件",
    "Miscellaneous Manufacturing": "其他制造业",
    // Inflation Context
    "Growth Cycle": "增长周期",
    "Inflation Context": "通胀环境",
    "Core PCE YoY": "核心PCE同比",
    "Gap vs Fed 2% Target": "相对美联储2%目标",
    "Fed 2% Target": "美联储2%目标",
    "Fed Target (since 2012)": "美联储目标（2012年起）",
    "Fed Target": "美联储目标",
    "GDP Expectations": "GDP预期",
    "Pending Inputs": "待输入",
    "Expected Direction": "预期方向",
    "ISM-Implied Direction": "ISM隐含方向",
    "ISM Outlook": "ISM展望",
    "Required Inputs": "所需输入",
    "Supporting Context": "辅助背景",
    "Not Ready": "未就绪",
    "Fed Balance Sheet": "美联储资产负债表",
    "Liquidity Context": "流动性背景",
    "Total Assets": "总资产",
    "Total Assets 13W Net Change": "总资产13周净变化",
    "Treasury 13W Net Change": "美债持仓13周净变化",
    "MBS 13W Net Change": "MBS持仓13周净变化",
    "Treasury 13W Change": "美债持仓13周净变化",
    "MBS 13W Change": "MBS持仓13周净变化",
    "Fed Total Assets YoY": "美联储总资产同比",
    "Fed Balance Sheet 13W Composition": "美联储资产负债表13周构成",
    "Above Target": "高于目标",
    "Near Target": "接近目标",
    "Below Target": "低于目标",
    "FOMC Calendar": "FOMC日历",
    "Policy Timing": "政策时点",
    "Next Meeting": "下次会议",
    "FOMC Tone": "FOMC倾向",
    "Policy Track": "政策轨道",
    "Statement": "声明",
    "Minutes": "纪要",
    "Latest Tone": "最新倾向",
    "Next FOMC Meeting": "下次FOMC会议",
    "Latest FOMC Tone": "最近FOMC倾向",
    "Next Meeting Date": "下次会议日期",
    "Action": "政策动作",
    "Guidance": "前瞻指引",
    "Language": "声明语气",
    "Bias": "综合倾向",
    "Change": "较上次",
    "Hold": "维持",
    "Cut": "降息",
    "Hike": "加息",
    "Neutral": "中性",
    "Hawkish": "偏鹰",
    "Dovish": "偏鸽",
    "Mixed": "混合",
    "Mild Hawkish": "温和偏鹰",
    "Mild Dovish": "温和偏鸽",
    "More Hawkish vs previous": "较上次更偏鹰",
    "More Dovish vs previous": "较上次更偏鸽",
    "Unchanged": "未变化",
    "Less Hawkish vs previous": "较上次偏鹰减弱",
    "Less Dovish vs previous": "较上次偏鸽减弱",
    "Policy meeting": "政策会议",
    "Includes SEP": "包含经济预测摘要",
    "No scheduled meeting": "暂无已安排会议",
    "Tone unavailable": "暂无倾向",
    "Pending review": "等待审核",
    "FOMC Policy Read": "FOMC政策解读",
    "Statement Bias": "声明基调",
    "Minutes Confirmation": "纪要确认",
    "Risk Focus": "风险焦点",
    "Policy Conviction": "政策坚定度",
    "Confirmed": "确认",
    "Confirmed But Divided": "确认但有分歧",
    "Weakened": "削弱",
    "Stronger Underneath": "内部更强",
    "Contradicted": "矛盾",
    "Inflation": "通胀",
    "Growth Labor": "增长/就业",
    "Financial Stability": "金融稳定",
    "Balanced": "平衡",
    "Moderate": "中等",
    "Divided": "分歧",
    "Pending": "待处理",
    // GDP Expectations components
    "ISM Manufacturing": "ISM制造业",
    "ISM Services": "ISM服务业",
    "Labor Trend": "就业趋势",
    "Consumer Indicators": "消费指标",
    "Available": "可用",
    "Unavailable": "不可用",
    "Not Loaded": "未加载",
    "Supports Growth": "支持增长",
    "Growth Slowing": "增长放缓",
    "Supports Contraction": "支持收缩",
    "Contraction Easing": "收缩缓解",
    "Turning Supportive": "转向支持",
    "Slowing": "放缓",
    "Improving": "改善",
    "Turning Up": "转向上行",
    "Evidence": "证据",
    // ISM Policy Pressure
    "Policy Pressure": "政策压力",
    "Growth Pressure": "增长压力",
    "Inflation Pressure": "通胀压力",
    "Supply Pressure": "供应压力",
    "Combined Pressure": "综合压力",
    "Inflation Caution": "通胀警惕",
    "Less Easing Pressure": "宽松减弱压力",
    // Survey Synthesis
    "Survey Synthesis": "调查综合",
    // Economic Confirmation
    "Economic Confirmation": "经济确认",
    "Claims-Based Labor Confirmation": "基于申领数据的劳动力确认",
    "Initial Claims": "初次申领",
    "Continuing Claims": "持续申领",
    "Claims Direction": "申领方向",
    "Macro Growth Regime": "宏观增长机制",
    "Coverage": "覆盖范围",
    "Overall Economic Confirmation": "总体经济确认",
    "Labor Context": "劳动力背景",
    "Real Activity": "实际活动",
    "Classification": "分类",
    "Observation Period": "观测周期",
    "Latest 4W Mean": "最新4周均值",
    "Comparison 4W Mean": "对比4周均值",
    "Reason": "原因",
    "Method Version": "方法版本",
    "Method Status": "方法状态",
    "Vintages": "数据版本",
    "Reference Period": "参考周期",
    "Release Date": "发布日期",
    "Source": "来源",
    "Based On": "基于",
    "Status": "状态",
    "Next Event": "下一事件",
    "Direction": "方向",
    "Nonfarm Payrolls Change": "非农月度变化",
    "Payrolls 3M Avg Change": "非农3M平均变化",
    "Manufacturing Production": "制造业生产",
    "Total Industrial Production": "工业总生产",
    "Capacity Utilization": "产能利用率",
    "Unemployment Rate": "失业率",
    "Average Weekly Hours": "平均每周工时",
    "Average Hourly Earnings": "平均时薪",
    "Payroll Revisions": "非农修订",
    "Wage Pressure Context": "薪资压力背景",
    "As Of": "截至",
    "Vintage Policy": "数据版本策略",
    "Context only — does not change the confirmation result": "仅作背景参考 — 不影响确认结果",
    "Data collected. Method pending approval — shown as context only.": "数据已收集。方法待审批 — 仅作背景参考。",
    "No Real Activity data has been collected yet. Method pending approval.": "尚未收集实际活动数据。方法待审批。",
    "Labor context data is not yet available.": "劳动力背景数据尚不可用。",
    "No upcoming Employment Situation event is scheduled.": "暂无已安排的就业形势报告事件。",
    "Revised payroll observations": "已修订的非农观测",
    "At Release": "发布时值",
    "Latest": "最新值",
    "Revision #": "修订次数",
    "Period": "周期",
    "Value": "数值",
    "Release": "发布",
    "Open": "打开",
    "ISM Growth Direction": "ISM增长方向",
    "Both Expanding": "制造业与服务业均扩张",
    "Both Contracting": "制造业与服务业均收缩",
    "Both Neutral": "制造业与服务业均中性",
    "Diverging": "制造业与服务业分化",
    "Manufacturing & Services PMI Trend": "制造业与服务业PMI走势",
    "Both Lower Than Last Month": "两者均低于上月",
    "Both Higher Than Last Month": "两者均高于上月",
    "Both Unchanged From Last Month": "两者均与上月持平",
    "New Orders Signal": "新订单信号",
    "Expanding but Slowing": "仍在扩张，但正在放缓",
    "Expanding and Improving": "扩张并改善",
    "Expanding and Stable": "扩张且稳定",
    "Contraction Deepening": "收缩加深",
    "Contraction Easing": "收缩缓解",
    "Contracting and Stable": "收缩且稳定",
    "Mixed New Orders": "新订单信号混合",
    "Leading Indicator Comparison": "领先指标对比",
    "Slowing Together": "同步放缓",
    "Improving Together": "同步改善",
    "Stable Together": "同步稳定",
    "Services Leading": "服务业领先",
    "Manufacturing Leading": "制造业领先",
    "Not Applicable": "不适用",
    "Unresolved": "尚未确认",
    "ISM-implied GDP Growth": "ISM指向的GDP增长",
    "Growth Accelerating": "增长可能加速",
    "Growth Slowing": "增长速度可能放缓",
    "Growth Contracting": "增长可能收缩",
    "Growth Improving": "增长可能改善",
    "ISM Portfolio Contribution": "ISM对组合倾向的影响",
    "Supports Long Bias": "支持偏多倾向",
    "Supports Neutral or Defensive Bias": "支持中性或防御倾向",
    "ISM signals support a more constructive risk-asset posture, while Market Setup determines the final portfolio posture.": "ISM信号支持更积极的风险资产倾向，但最终仓位仍由Market Setup决定。",
    "Expansion remains intact; weaker one-period momentum is caution, not a confirmed reversal. Market Setup determines the final portfolio posture.": "扩张格局仍未改变；一期的动能转弱是警惕信号，并非已确认的反转。最终仓位仍由Market Setup决定。",
    "Observation Status": "观察状态",
    "Continue Observing": "继续观察",
    "No Additional Observation Flag": "无需额外观察提示",
    "awaiting_confirmation": "继续观察",
    "Awaiting Confirmation": "继续观察",
    "Building Permits": "建筑许可",
    "not_required": "无需确认",
    "Not Required": "无需确认",
    "Services Backlog Signal": "服务业订单积压信号",
    "Supports Continued Growth": "支持增长延续",
    "Supports Weaker Demand": "支持需求走弱",
    "Supports Growth": "支持增长",
    "Supports Contraction": "支持收缩",
    "ISM signals alone do not support materially increasing risk exposure or shifting to a short posture.": "仅凭ISM信号，不足以支持明显增加风险资产敞口，也不足以支持转向做空。",
    "ISM signals support a neutral or more defensive posture, while Market Setup determines the final portfolio posture.": "ISM信号支持保持中性或提高防御性，但最终仓位仍由Market Setup决定。",
    "Contraction remains intact; one-period improvement awaits confirmation. Market Setup determines the final portfolio posture.": "收缩格局仍未改变；一期的改善尚未被确认。最终仓位仍由Market Setup决定。",
    "Manufacturing and Services data are insufficient to form an ISM portfolio bias.": "制造业和服务业数据尚不足，暂不形成ISM组合倾向。",
    "Rising": "上升",
    "Falling": "下降",
    "Flat": "持平",
    "Expanding": "扩张中",
    "Contracting": "收缩中",
    "Mixed": "混杂",
    "Slowing": "放缓",
    "Improving": "改善",
    "Stable": "稳定",
    "Aligned expansion": "一致扩张",
    "Aligned contraction": "一致收缩",
    "Aligned neutral": "一致中性",
    "Divergent": "分歧",
    "Not applicable": "不适用",
    "Unresolved": "未解决",
    "Aligned": "一致",
    "Aligned rising": "一致上升",
    "Aligned falling": "一致下降",
    "Mixed momentum": "混合动能",
    "Long": "做多",


    // Bias Evidence
    "Bias Evidence": "偏向证据",
    "Macro Portfolio Bias": "宏观组合偏向",
    "ISM Contribution": "ISM贡献",
    "Confirmation Status": "确认状态",
    "Partial": "部分确认",
    "Long": "做多",
    "Short": "做空",
    "GDP direction": "GDP方向",
    "Long clues": "做多线索",
    "Short clues": "做空线索",
    "Manufacturing": "制造业",
    "Services": "服务业",
    "Labor": "就业",
    "Practical Guidance": "操作指南",
    "Do": "动作",
    "Avoid": "避免",
    "What Supports the Conclusion": "结论支撑",
    "Why Conviction Is Limited": "为何谨慎",
    "What Would Change the View": "什么会改变看法",
    "More defensive": "更防御",
    "More constructive": "更积极",
    "Component Data": "组件数据",
    "Supporting data": "支持数据",
    "Regional Research Read": "区域研究读数",
    "Regional Optimism vs National": "区域乐观指数 vs 全国",
    "Quarterly raw survey data — not seasonally adjusted": "原始季度调查数据 — 未经季节性调整",
    "QoQ": "季度环比",
  };


export function zhLabel(label) {
    return ZH_LABELS[label] || null;
  }


export function bilingualLabel(label) {
    const zh = zhLabel(label);
    return zh ? `${escapeHtml(label)}<small>${escapeHtml(zh)}</small>` : escapeHtml(label);
  }


export const CREDIT_DETAIL_MAP = {};


export const CREDIT_STATUS_META = {
    healthy: { label: "Healthy", zh: "健康" },
    weak_credit_warning: { label: "Weak Credit Warning", zh: "弱信用预警" },
    risk_rising: { label: "Risk Rising", zh: "风险上升" },
    crisis_stress: { label: "Crisis Stress", zh: "危机压力" },
    mixed: { label: "Mixed", zh: "混合" },
    missing: { label: "Missing", zh: "缺失" },
  };


export const CREDIT_REGIME_VISIBLE_POINTS = 126;


export function creditStatusMeta(status) {
    return CREDIT_STATUS_META[status] || CREDIT_STATUS_META.missing;
  }


export function creditDiagnosticInterpretation(status) {
    const messages = {
      healthy: {
        text: "Overall credit risk is low and quality dispersion is contained. Credit conditions are supportive for risk appetite.",
        zh: "整体信用风险较低，信用质量分化受控。信用环境对风险偏好较友好。",
      },
      weak_credit_warning: {
        text: "Overall credit risk is low, but CCC-BBB quality dispersion is elevated. The market is not broadly stressed, but weak borrowers are still under pressure.",
        zh: "整体信用风险不高，但CCC-BBB质量利差偏高。市场并非全面承压，但弱信用主体仍被要求更高风险补偿。",
      },
      risk_rising: {
        text: "Credit spreads are rising or moving into stressed zones. Risk is being repriced across credit markets.",
        zh: "信用利差正在上升，或已进入承压区间。信用市场正在重新定价风险。",
      },
      crisis_stress: {
        text: "Credit stress is broad and severe. Treat this as a high-risk credit regime until spreads stop accelerating.",
        zh: "信用压力广泛且严重。在利差停止加速前，应视为高风险信用环境。",
      },
      mixed: {
        text: "Credit signals are mixed. Read level, percentile, and trend together before drawing a directional conclusion.",
        zh: "信用信号不一致。需要结合水平、历史分位和趋势一起判断。",
      },
      missing: {
        text: "Credit condition data is incomplete. Refresh the credit series before interpreting this section.",
        zh: "信用环境数据不完整。解读前需要先刷新信用数据。",
      },
    };
    return messages[status] || messages.missing;
  }


export function bilingualTitle(title) {
    const zh = zhLabel(title);
    return zh ? `${escapeHtml(title)}<br><small>${escapeHtml(zh)}</small>` : escapeHtml(title);
  }


export function titleCaseToken(value) {
    return String(value || "missing")
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }


export function formatPolicyAction(value) {
    const map = {
      hold: "Hold",
      cut: "Cut",
      hike: "Hike",
    };
    return map[value] || titleCaseToken(value);
  }


export function formatToneValue(value) {
    const map = {
      hawkish: "Hawkish",
      dovish: "Dovish",
      neutral: "Neutral",
      mixed: "Mixed",
    };
    return map[value] || titleCaseToken(value);
  }


export function formatOverallBias(value) {
    const map = {
      mild_hawkish: "Mild Hawkish",
      mild_dovish: "Mild Dovish",
      hawkish: "Hawkish",
      dovish: "Dovish",
      neutral: "Neutral",
      mixed: "Mixed",
    };
    return map[value] || titleCaseToken(value);
  }


export function formatToneChange(value) {
    const map = {
      more_hawkish: "More Hawkish vs previous",
      more_dovish: "More Dovish vs previous",
      unchanged: "Unchanged",
      less_hawkish: "Less Hawkish vs previous",
      less_dovish: "Less Dovish vs previous",
    };
    return map[value] || titleCaseToken(value);
  }


export function formatMinutesConfirmation(value) {
    return formatToneValue(value || "pending");
  }


export function formatRiskFocus(value) {
    return formatToneValue(value || "unknown");
  }


export function formatPolicyConviction(value) {
    return formatToneValue(value || "unknown");
  }


export function toneBadgeClass(tone) {
    const t = String(tone || "unknown").toLowerCase();
    if (["dovish", "mild_dovish"].includes(t)) return "tone-dovish";
    if (["hawkish", "mild_hawkish"].includes(t)) return "tone-hawkish";
    if (t === "neutral") return "tone-neutral";
    return "tone-unknown";
  }


export function formatPressureValue(value) {
    const map = {
      inflation_caution: "Inflation Caution",
      less_easing_pressure: "Less Easing Pressure",
      easing_pressure: "Easing Pressure",
      elevated: "Elevated",
      normal: "Normal",
      mixed: "Mixed",
    };
    return map[value] || titleCaseToken(value);
  }


export function formatBiasValue(value) {
    const map = {
      long: "Long",
      short: "Short",
      neutral: "Neutral",
    };
    return map[value] || titleCaseToken(value);
  }


export function componentLabel(compId) {
    const map = {
      ism_manufacturing: "ISM Manufacturing",
      ism_services: "ISM Services",
      labor_trend: "Labor Trend",
      consumer_indicators: "Consumer Indicators",
    };
    return map[compId] || titleCaseToken(compId);
  }


export function componentStatusBadge(status) {
    if (status === "available") {
      return `<strong class="inflation-status-badge component-status-available">${bilingualLabel("Available")}</strong>`;
    }
    if (status === "pending") {
      return `<strong class="inflation-status-badge component-status-pending">${bilingualLabel("Pending")}</strong>`;
    }
    if (status === "not_loaded") {
      return `<strong class="inflation-status-badge component-status-pending">${bilingualLabel("Not Loaded")}</strong>`;
    }
    return `<strong class="inflation-status-badge component-status-unavailable">${bilingualLabel("Unavailable")}</strong>`;
  }


export function formatComponentDirection(direction) {
    const map = {
      supports_growth: "Supports Growth",
      supports_long: "Supports Long",
      supports_short: "Supports Short",
      conflicting: "Conflicting",
      mixed: "Mixed",
      growth_caution: "Growth Slowing",
      supports_contraction: "Supports Contraction",
      contraction_easing: "Contraction Easing",
      turning_supportive: "Turning Supportive",
    };
    return map[direction] || titleCaseToken(direction);
  }


export function formatGdpDirection(direction) {
    const map = {
      rising: "Rising",
      slowing: "Slowing",
      falling: "Falling",
      improving: "Improving",
      turning_up: "Turning Up",
      stable: "Stable",
      mixed: "Mixed",
    };
    return map[direction] || titleCaseToken(direction);
  }


export function formatBiasComponentValue(value) {
    const map = {
      supports_growth: "Supports Growth",
      supports_long: "Supports Long",
      supports_short: "Supports Short",
      conflicting: "Conflicting",
      unavailable: "Unavailable",
      pending: "Pending",
    };
    return map[value] || titleCaseToken(value);
  }


export function formatComponentLabel(key) {
    const map = {
      ism_manufacturing: "Manufacturing",
      ism_services: "Services",
      labor: "Labor",
    };
    return map[key] || titleCaseToken(key);
  }


export function trendGlyph(value) {
    return { rising: "↑", falling: "↓", stable: "→" }[value] || "";
  }


export function accelerationGlyph(value) {
    return { accelerating_up: "↑↑", accelerating_down: "↓↓" }[value] || "";
  }


export function accelerationLabel(value) {
    return value === "none" ? "No Acceleration" : titleCaseToken(value);
  }


export function formatPercentile(value) {
    return value === null || value === undefined ? "n/a" : `${value}%`;
  }


export function fmtIsmIndex(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
    return Number(value).toFixed(1);
  }


export function ismBadgeClass(status) {
    if (["expansion", "supportive", "neutral", "available"].includes(status)) return "supportive";
    if (["contraction", "warning", "inflation_pressure", "supply_pressure"].includes(status)) return "warning";
    if (["missing", "pending_inputs"].includes(status)) return "missing";
    return "mixed";
  }


export function fmtIsmPointChange(value) {
    if (value === null || value === undefined) return "\u2014";
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toFixed(1)}`;
  }


export function fmtIsmBreadthCount(value) {
    if (value === null || value === undefined) return "\u2014";
    return String(value);
  }


export function fmtMonthYear(value) {
    const [year, month, day] = String(value).split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day || 1));
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    });
  }


export function fmtYear(value) {
    return String(value || "").slice(0, 4);
  }

