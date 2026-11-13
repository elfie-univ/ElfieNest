import { Button, Empty } from "antd";
import type { NestEvent } from "./contracts";

const eventLabels: Readonly<Record<string, string>> = {
  gateway_started: "网关启动", runtime_connected: "Godot 已连接", runtime_disconnected: "Godot 已断开",
  configure_world: "正在配置世界", world_configured: "世界已就绪", startup_error: "世界加载失败",
  actor_added: "角色已加入", wander_enabled: "随机游走已开启", simulation_paused: "模拟已暂停",
  simulation_resumed: "模拟已继续", simulation_reset: "实验已重置", scene_manifest: "场景目录已同步",
  world_snapshot: "世界状态已同步", intent_accepted: "动作已接收", intent_started: "动作已开始",
  intent_terminal: "动作执行结果", wander_move: "随机游走目标已分配",
};

export function RunRecords({ events, close }: { events: readonly NestEvent[]; close: () => void }) {
  return <aside className="nest-run-records" id="nest-run-records" aria-label="运行记录">
    <header><strong>运行记录</strong><Button type="text" size="small" aria-label="关闭运行记录" onClick={close}>×</Button></header>
    {events.length === 0 ? <Empty description="还没有运行事件" /> : <ol className="nest-events">
      {[...events].reverse().map((event) => <li key={event.sequence}>
        <time>{new Date(event.occurred_at).toLocaleTimeString("zh-CN")}</time>
        <strong>{eventLabels[event.name] ?? event.name}</strong><p>{event.detail}</p>
      </li>)}
    </ol>}
  </aside>;
}
