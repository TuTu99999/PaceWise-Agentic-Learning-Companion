"""
Giao diện dòng lệnh (CLI) chạy Multi-Agent trên Terminal.
Tích hợp LangGraph Checkpointer (MemorySaver) hỗ trợ hội thoại đa lượt (Multi-turn conversations).
Cách chạy:
    python -m src.agents
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Đảm bảo hiển thị tiếng Việt trên Terminal Windows không bị lỗi font/codec
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Đảm bảo sys.path chứa thư mục gốc dự án dù chạy bằng cách nào
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.graph import agent  # noqa: E402


def _print_banner(session_id: str):
    print("=" * 65)
    print(" 🎓 LMS CANVAS MULTI-AGENT SYSTEM (TERMINAL CLI)")
    print(f" 🔑 Phiên làm việc (Session ID): {session_id}")
    print(" 💡 Lệnh nhanh:")
    print("    - Nhập câu hỏi hoặc yêu cầu bất kỳ để trò chuyện với Agent")
    print("    - '/new'   : Tạo phiên học mới (xóa ngữ cảnh cũ)")
    print("    - '/state' : Xem trạng thái dữ liệu (State) đang lưu trữ")
    print("    - 'exit'   : Thoát chương trình")
    print("=" * 65)


async def main():
    session_id = f"session_{uuid.uuid4().hex[:6]}"
    _print_banner(session_id)

    while True:
        try:
            user_input = input(f"\n[Sinh viên @ {session_id}] > ").strip()
            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit", "q"}:
                print("\n👋 Tạm biệt! Hẹn gặp lại bạn trong buổi học tiếp theo.")
                break

            if user_input.lower() == "/new":
                session_id = f"session_{uuid.uuid4().hex[:6]}"
                print("\n" + "=" * 65)
                print(f"🔄 ĐÃ KHỞI TẠO PHIÊN HỌC MỚI: {session_id}")
                print("=" * 65)
                continue

            config = {"configurable": {"thread_id": session_id}}

            if user_input.lower() in {"/state", "/status"}:
                snapshot = agent.get_state(config)
                values = snapshot.values if snapshot else {}
                print("\n--- 📊 TRẠNG THÁI HIỆN TẠI CỦA PHIÊN HỌC ---")
                print(f"- Node gần nhất: {values.get('current_node', 'Chưa có')}")
                print(f"- Workflow: {values.get('workflow', 'Chưa có')}")
                milestones = values.get("proposed_milestones", [])
                print(f"- Số milestones trong kế hoạch: {len(milestones)}")
                if milestones:
                    for m in milestones:
                        print(f"  + [{m.get('milestone_id')}] {m.get('title')} ({m.get('estimated_minutes')} phút)")
                passages = values.get("retrieved_passages", [])
                print(f"- Số đoạn học liệu đang trích xuất: {len(passages)}")
                disputes = values.get("disputed_evidence", [])
                print(f"- Số khiếu nại trích dẫn: {len(disputes)}")
                print("---------------------------------------------")
                continue

            print("\n⏳ Đang xử lý qua Multi-Agent Coordinator...")
            result = await agent.ainvoke({"query": user_input}, config=config)

            workflow = result.get("workflow", "unknown")
            node = result.get("current_node", "unknown")
            response = str(result.get("response") or "Không có phản hồi.")

            # Lớp bảo vệ: Loại bỏ hoàn toàn khối JSON thô hoặc thẻ nội bộ để sinh viên chỉ nhìn thấy văn bản thân thiện
            import re
            clean_display = re.sub(r"<DATA_[A-Z_]+>[\s\S]*?</DATA_[A-Z_]+>", "", response).strip()
            clean_display = re.sub(r"`{1,3}(?:json)?[\s\S]*?(?:`{1,3}|$)", "", clean_display).strip()
            clean_display = re.sub(r"\{[\s\S]*?\"(?:recovery_options|milestones|proposed_milestones|understanding_eval)\"[\s\S]*?\}", "", clean_display).strip()
            clean_display = re.sub(r"\n{3,}", "\n\n", clean_display).strip()

            if not clean_display or len(clean_display) < 20:
                if result.get("recovery_options"):
                    from src.agents.workflows.recover import _format_options_as_text
                    clean_display = _format_options_as_text(result["recovery_options"])
                else:
                    clean_display = response

            print(f"\n[AI Agent | {workflow.upper()} | Node: {node}]")
            print("-" * 50)
            print(clean_display)
            print("-" * 50)

            # In thông tin bổ trợ nếu có milestone được tạo/chỉnh sửa
            if result.get("proposed_milestones"):
                print(f"📌 Đã lưu {len(result['proposed_milestones'])} milestones vào bộ nhớ phiên {session_id}.")

        except KeyboardInterrupt:
            print("\n\n⏹️ Thao tác bị gián đoạn. Tạm biệt!")
            break
        except Exception as e:
            print(f"\n❌ Lỗi trong quá trình xử lý: {e}")


if __name__ == "__main__":
    asyncio.run(main())
