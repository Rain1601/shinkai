export type Locale = "zh" | "en";

export function isZh(locale: Locale): boolean {
  return locale === "zh";
}

export function localizeMode(mode: unknown, locale: Locale): string {
  const value = String(mode ?? "");
  if (!isZh(locale)) {
    if (value === "mode_b_narrative") return "Mode B Discovery";
    if (value === "mode_a_company") return "Mode A Company Analysis";
    return value || "Unknown";
  }
  if (value === "mode_b_narrative") return "模式 B：主题发现";
  if (value === "mode_a_company") return "模式 A：公司深度分析";
  return value || "未知";
}

export function localizeStatus(status: string, locale: Locale): string {
  if (!isZh(locale)) return status;
  return (
    {
      created: "已创建",
      running: "运行中",
      paused: "已暂停",
      awaiting_checkpoint: "等待检查点",
      completed: "已完成",
      failed: "失败",
      aborted: "已终止"
    }[status] ?? status
  );
}

export function localizeStage(stage: string, locale: Locale): string {
  if (!isZh(locale)) return stage;
  const loopMatch = stage.match(/^loop_(.+)_(expanding|review|optimize)$/);
  if (loopMatch) {
    const action =
      loopMatch[2] === "expanding" ? "扩展" : loopMatch[2] === "review" ? "复盘" : "优化";
    return `第 ${loopMatch[1]} 轮${action}`;
  }
  return (
    {
      created: "已创建",
      scoped: "已定范围",
      planning: "规划中",
      graph_expansion: "图谱扩展",
      underwriting: "公司深度分析",
      review: "复盘",
      evaluating: "评测中",
      completed: "已完成",
      failed: "失败"
    }[stage] ?? stage
  );
}

export function localizeDecision(decision: unknown, locale: Locale): string {
  const value = String(decision ?? "");
  if (!isZh(locale)) return value;
  return (
    {
      queue_mode_a: "进入模式 A 队列",
      watch_only: "继续观察",
      continue_deeper: "继续向下挖掘",
      expand_next_frontier: "扩展下一前沿",
      block_and_research_contradiction: "先处理反证",
      refresh_sources: "刷新来源",
      raise_primary_source_priority: "提高一手来源优先级",
      invest: "可进入投资研究",
      watch: "观察名单",
      reject: "暂不进入"
    }[value] ?? value
  );
}

export function localizeEventType(type: unknown, locale: Locale): string {
  const value = String(type ?? "event");
  if (!isZh(locale)) return value;
  return (
    {
      run_start: "运行创建",
      run_recovered: "运行恢复",
      plan: "计划生成",
      tool_call: "工具调用",
      tool_result: "工具返回",
      frontier_selected: "前沿选择",
      frontier_reprioritized: "前沿重排",
      role_step_completed: "角色步骤完成",
      supply_chain_layer_started: "层级启动",
      frontier_expanded: "前沿扩展",
      theme_discovered: "主题发现",
      judgment_created: "判断生成",
      candidate_created: "候选创建",
      candidate_scored: "候选评分",
      review_completed: "复盘完成",
      optimization_decision: "优化决策",
      memory_patch_proposed: "记忆补丁",
      filter_policy_patch_proposed: "筛选规则补丁",
      checklist_patch_proposed: "清单补丁",
      research_task_created: "研究任务",
      human_injection: "人工注入",
      injection_acknowledged: "注入回应",
      checkpoint_raised: "等待审阅",
      checkpoint_released: "审阅完成",
      graph_delta: "图谱更新",
      evidence_found: "证据发现",
      claim_created: "论点创建",
      claim_validated: "论点校验",
      company_deep_analysis_completed: "公司深度分析",
      company_dossier_created: "公司档案创建",
      budget_exhausted: "预算耗尽",
      eval_completed: "评测完成",
      child_run_created: "子运行创建",
      usage: "用量记录",
      error: "错误",
      done: "完成"
    }[value] ?? value
  );
}

export function localizeText(value: unknown, locale: Locale): string {
  const text = String(value ?? "");
  if (!isZh(locale) || !text) return text;
  return exactZh[text] ?? text;
}

export function formatNumber(value: unknown): string {
  if (typeof value === "number") return String(Math.round(value * 1000) / 1000);
  return String(value ?? "n/a");
}

const exactZh: Record<string, string> = {
  "Autonomous Discovery": "自主发现",
  "SSE Smoke": "SSE 验证",
  "AI infrastructure": "AI 基础设施",
  "data center constraints": "数据中心约束",
  "advanced packaging": "先进封装",
  "surface concrete under-covered themes and candidates": "挖掘具体、低覆盖的主题与候选公司",
  "discover AI supply-chain key companies": "发现 AI 供应链关键公司",
  "Power and electrical infrastructure": "电力与电气基础设施",
  "Advanced packaging, HBM, and test capacity": "先进封装、HBM 与测试产能",
  "Cluster networking and optical interconnect": "集群网络与光互连",
  "Thermal systems and liquid cooling": "热管理系统与液冷",
  "AI data center growth is increasingly constrained by grid interconnects, switchgear, UPS capacity, backup generation, and power density.":
    "AI 数据中心扩张越来越受并网、开关设备、UPS 容量、备用发电与功率密度约束。",
  "AI accelerator availability depends on CoWoS-like advanced packaging, HBM integration, probe cards, handlers, inspection, and metrology.":
    "AI 加速器供给依赖 CoWoS 类先进封装、HBM 集成、探针卡、分选机、检测与量测产能。",
  "Large training and inference clusters create non-linear east-west traffic, raising demand for optical modules, DSPs, high-speed cables, and switching.":
    "大规模训练和推理集群带来非线性东西向流量，推动光模块、DSP、高速线缆和交换设备需求。",
  "Rack power density pushes air cooling limits, forcing liquid cooling, CDUs, heat exchangers, facility redesign, and maintenance capability.":
    "机柜功率密度逼近风冷上限，推动液冷、CDU、换热器、机房改造和运维能力需求。",
  "Trace sub-suppliers for switchgear, busway, thermal power management, and grid interconnect equipment.":
    "继续追踪开关设备、母线槽、热电管理和并网设备的下级供应商。",
  "Separate durable test/metrology exposure from cyclical semiconductor equipment recovery.":
    "区分测试/量测的长期 AI 暴露与半导体设备周期性复苏。",
  "Validate whether optical AI exposure is structurally profitable or only a cyclical inventory rebound.":
    "验证光通信 AI 暴露是否具备结构性盈利能力，而非只是库存周期反弹。",
  "Map component suppliers below CDUs and facility thermal integrators.":
    "继续映射 CDU 和机房热管理集成商之下的部件供应商。",
  "Run Q1 quality and Q2 underwater filters.": "执行 Q1 质量与 Q2 低覆盖度筛选。",
  "Potential second-order beneficiary tied to a concrete AI bottleneck.":
    "与具体 AI 瓶颈相关的潜在二阶受益公司。",
  "Self-directed discovery": "自主发现",
  "Agent-led": "Agent 主导",
  "No payload": "无载荷",
  "needs source": "需要来源"
};
