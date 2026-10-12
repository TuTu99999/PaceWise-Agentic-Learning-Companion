"""
Tools hỗ trợ tính toán thời gian, lịch trình và độ trễ.
Cung cấp các hàm định lượng cho Milestone Agent, Tracking, và Recovery Agent.
"""

from datetime import UTC, datetime
from typing import Any


def _parse_time_str(time_val: str) -> float | None:
    """Chuyển đổi chuỗi giờ 'HH:MM' hoặc 'HH:MM:SS' thành số giờ dạng float (0.0 - 24.0)."""
    try:
        parts = time_val.strip().split(":")
        hours = float(parts[0])
        minutes = float(parts[1]) if len(parts) > 1 else 0.0
        seconds = float(parts[2]) if len(parts) > 2 else 0.0
        return hours + minutes / 60.0 + seconds / 3600.0
    except (ValueError, IndexError):
        return None


def _parse_iso_datetime(dt_val: str | datetime) -> datetime | None:
    """Chuyển đổi chuỗi ISO hoặc datetime object thành datetime."""
    if isinstance(dt_val, datetime):
        return dt_val
    if not isinstance(dt_val, str):
        return None
    cleaned = dt_val.strip().replace("Z", "+00:00")
    # Thử parse ISO format
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        pass
    # Thử các format phổ biến khác
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _extract_slot_duration(slot: dict | Any) -> float:
    """
    Tính số giờ của một slot thời gian.
    Hỗ trợ cả trường hợp có 'hours' trực tiếp, hoặc cặp 'start'/'end' (ISO datetime hoặc time HH:MM).
    """
    if isinstance(slot, (int, float)):
        return max(0.0, float(slot))
    if not isinstance(slot, dict):
        return 0.0

    # 1. Kiểm tra nếu có trường số giờ trực tiếp
    for key in ("hours", "duration_hours", "duration", "available_hours"):
        if key in slot and slot[key] is not None:
            try:
                return max(0.0, float(slot[key]))
            except (ValueError, TypeError):
                pass

    # 2. Kiểm tra nếu có start và end
    start_raw = slot.get("start") or slot.get("start_time") or slot.get("start_hour")
    end_raw = slot.get("end") or slot.get("end_time") or slot.get("end_hour")

    if start_raw is not None and end_raw is not None:
        # Trường hợp numeric float (ví dụ: start=9, end=11.5)
        if isinstance(start_raw, (int, float)) and isinstance(end_raw, (int, float)):
            return max(0.0, float(end_raw) - float(start_raw))

        # Trường hợp ISO datetime
        start_dt = _parse_iso_datetime(start_raw)
        end_dt = _parse_iso_datetime(end_raw)
        if start_dt and end_dt:
            duration = (end_dt - start_dt).total_seconds() / 3600.0
            return max(0.0, duration)

        # Trường hợp chuỗi giờ "HH:MM"
        if isinstance(start_raw, str) and isinstance(end_raw, str):
            start_hours = _parse_time_str(start_raw)
            end_hours = _parse_time_str(end_raw)
            if start_hours is not None and end_hours is not None:
                duration = end_hours - start_hours
                if duration < 0:
                    duration += 24.0  # Vắt qua nửa đêm
                return max(0.0, duration)

    return 0.0


def _slot_bounds(slot: dict[str, Any]) -> tuple[str, float, float] | None:
    """Normalize a positioned slot to (day, start hour, end hour)."""
    start_raw = slot.get("start") or slot.get("start_time") or slot.get("start_hour")
    end_raw = slot.get("end") or slot.get("end_time") or slot.get("end_hour")
    if start_raw is None or end_raw is None:
        return None

    if isinstance(start_raw, (int, float)) and isinstance(end_raw, (int, float)):
        start, end = float(start_raw), float(end_raw)
        day = str(slot.get("day") or slot.get("date") or "default").strip().lower()
    else:
        start_dt = _parse_iso_datetime(start_raw)
        end_dt = _parse_iso_datetime(end_raw)
        if start_dt and end_dt:
            start = start_dt.timestamp() / 3600.0
            end = end_dt.timestamp() / 3600.0
            day = start_dt.date().isoformat()
        else:
            start = _parse_time_str(str(start_raw))
            end = _parse_time_str(str(end_raw))
            if start is None or end is None:
                return None
            day = str(slot.get("day") or slot.get("date") or "default").strip().lower()
    if end < start:
        end += 24.0
    return day, start, end


def _merged_duration(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged)


def calculate_available_hours(
    availability: list[dict] | None,
    unavailable_slots: list[dict] | None = None,
) -> float:
    """
    Tính toán tổng số giờ rảnh thực tế trong tuần sau khi trừ các khung giờ bận
    (lịch học cố định, việc cá nhân, lịch thi...).

    Args:
        availability: Danh sách các khung thời gian rảnh dự kiến của sinh viên.
        unavailable_slots: Danh sách các khung thời gian bận không thể xếp lịch.

    Returns:
        float: Tổng số giờ rảnh khả dụng (làm tròn 2 chữ số thập phân, tối thiểu 0.0).
    """
    if not availability:
        return 0.0

    unavailable_slots = unavailable_slots or []
    total_available = sum(_extract_slot_duration(slot) for slot in availability)

    # Numeric durations have no position on a calendar, so they are conservatively
    # subtracted. Calendar slots are only subtracted when they overlap an available slot.
    numeric_unavailable = sum(
        _extract_slot_duration(slot)
        for slot in unavailable_slots
        if isinstance(slot, (int, float))
        or (isinstance(slot, dict) and any(key in slot for key in ("hours", "duration_hours", "duration")))
    )

    overlap_hours = 0.0
    for available in availability:
        if not isinstance(available, dict):
            continue
        available_bounds = _slot_bounds(available)
        if available_bounds is None:
            continue
        available_day, available_start, available_end = available_bounds
        intersections: list[tuple[float, float]] = []
        for unavailable in unavailable_slots:
            if not isinstance(unavailable, dict):
                continue
            unavailable_bounds = _slot_bounds(unavailable)
            if unavailable_bounds is None:
                continue
            unavailable_day, unavailable_start, unavailable_end = unavailable_bounds
            if available_day != unavailable_day:
                continue
            overlap_start = max(available_start, unavailable_start)
            overlap_end = min(available_end, unavailable_end)
            if overlap_end > overlap_start:
                intersections.append((overlap_start, overlap_end))
        overlap_hours += _merged_duration(intersections)

    net_available = max(0.0, total_available - numeric_unavailable - overlap_hours)
    return round(net_available, 2)


def check_deadline_slack(
    deadline: str | datetime,
    estimated_hours: float,
    current_time: str | datetime | None = None,
) -> dict:
    """
    Kiểm tra thời gian dự phòng (slack hours) trước hạn chót.
    slack_hours = thời gian từ hiện tại tới deadline - số giờ dự kiến hoàn thành.

    Quy tắc an toàn:
        - Đánh dấu is_at_risk = True nếu slack_hours < 2.0 (dưới ngưỡng 2 giờ dự phòng tối thiểu).
        - Phân loại mức độ nguy cơ: 'critical' (< 0h), 'high' (< 2h), 'safe' (>= 2h).

    Args:
        deadline: Thời điểm deadline (chuỗi ISO datetime hoặc số giờ còn lại dạng string/float).
        estimated_hours: Ước lượng thời gian cần để hoàn thành bài tập (giờ).
        current_time: Thời điểm mốc để so sánh (mặc định là datetime.now()).

    Returns:
        dict: {
            "deadline": str,
            "hours_until_deadline": float,
            "estimated_hours": float,
            "slack_hours": float,
            "is_at_risk": bool,
            "risk_level": "critical" | "high" | "safe",
            "message": str
        }
    """
    est_hours = max(0.0, float(estimated_hours))

    # Xác định mốc thời gian tham chiếu (current_time)
    if current_time is None:
        now_dt = datetime.now(UTC)
    elif isinstance(current_time, datetime):
        now_dt = current_time
    else:
        parsed_current = _parse_iso_datetime(str(current_time))
        now_dt = parsed_current if parsed_current else datetime.now(UTC)

    # Xử lý nếu deadline là số giờ tương đối (ví dụ: "24", 48.0)
    hours_until_deadline = None
    if isinstance(deadline, (int, float)):
        hours_until_deadline = float(deadline)
        deadline_str = f"+{hours_until_deadline:.1f} hours"
    elif isinstance(deadline, str) and deadline.strip().replace(".", "", 1).isdigit():
        hours_until_deadline = float(deadline.strip())
        deadline_str = f"+{hours_until_deadline:.1f} hours"
    else:
        deadline_dt = _parse_iso_datetime(deadline)
        if deadline_dt:
            if deadline_dt.tzinfo is None and now_dt.tzinfo is not None:
                deadline_dt = deadline_dt.replace(tzinfo=now_dt.tzinfo)
            elif deadline_dt.tzinfo is not None and now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=deadline_dt.tzinfo)
            deadline_str = deadline_dt.isoformat()
            diff_seconds = (deadline_dt - now_dt).total_seconds()
            hours_until_deadline = diff_seconds / 3600.0
        else:
            # Fallback nếu chuỗi không parse được datetime
            hours_until_deadline = 0.0
            deadline_str = str(deadline)

    slack_hours = hours_until_deadline - est_hours
    slack_rounded = round(slack_hours, 2)
    is_at_risk = slack_rounded < 2.0

    if slack_rounded < 0:
        risk_level = "critical"
        message = (
            f"Báo động nghiêm trọng: Quỹ thời gian thiếu hụt {abs(slack_rounded):.1f} giờ "
            f"so với deadline ({deadline_str}). Cần kích hoạt quy trình phục hồi (Recover) ngay."
        )
    elif is_at_risk:
        risk_level = "high"
        message = (
            f"Cảnh báo nguy cơ cao: Thời gian đệm chỉ còn {slack_rounded:.1f} giờ "
            f"(dưới ngưỡng an toàn 2.0 giờ). Cần theo dõi sát sao hoặc giảm tải."
        )
    else:
        risk_level = "safe"
        message = (
            f"Tiến độ an toàn: Thời gian đệm đạt {slack_rounded:.1f} giờ "
            f"trước deadline ({deadline_str})."
        )

    return {
        "deadline": deadline_str,
        "hours_until_deadline": round(hours_until_deadline, 2),
        "estimated_hours": round(est_hours, 2),
        "slack_hours": slack_rounded,
        "is_at_risk": is_at_risk,
        "risk_level": risk_level,
        "message": message,
    }


def detect_schedule_conflicts(slots: list[dict] | None) -> list[dict]:
    """
    Phát hiện các nhiệm vụ hoặc khung giờ bị trùng lịch (schedule overlap).

    Args:
        slots: Danh sách các task/sự kiện đã xếp lịch. Mỗi slot cần có:
               - 'title' hoặc 'id' hoặc 'name': Tên nhiệm vụ
               - 'start' và 'end': Có thể là ISO datetime, hoặc 'day' kèm 'start_time'/'end_time',
                 hoặc số giờ float (start_hour, end_hour).

    Returns:
        list[dict]: Danh sách các xung đột được phát hiện, gồm thông tin 2 slot bị trùng,
                    thời lượng trùng (phút) và thông điệp cảnh báo.
    """
    if not slots or len(slots) < 2:
        return []

    # Chuẩn hóa các slot về khoảng thời gian (start_val, end_val, day_key, original_slot)
    normalized_slots = []
    for idx, slot in enumerate(slots):
        title = slot.get("title") or slot.get("name") or slot.get("id") or f"Task_{idx + 1}"
        day_key = str(slot.get("day") or slot.get("date") or "DEFAULT_DAY").strip().lower()

        start_raw = slot.get("start") or slot.get("start_time") or slot.get("start_hour")
        end_raw = slot.get("end") or slot.get("end_time") or slot.get("end_hour")

        if start_raw is None or end_raw is None:
            continue

        # 1. Thử parse ISO datetime
        start_dt = _parse_iso_datetime(start_raw)
        end_dt = _parse_iso_datetime(end_raw)
        if start_dt and end_dt:
            normalized_slots.append({
                "id": slot.get("id", f"slot_{idx}"),
                "title": title,
                "start": start_dt.timestamp(),
                "end": end_dt.timestamp(),
                "day_key": start_dt.strftime("%Y-%m-%d"),
                "raw": slot,
            })
            continue

        # 2. Thử parse numeric float hours
        if isinstance(start_raw, (int, float)) and isinstance(end_raw, (int, float)):
            normalized_slots.append({
                "id": slot.get("id", f"slot_{idx}"),
                "title": title,
                "start": float(start_raw) * 3600.0,
                "end": float(end_raw) * 3600.0,
                "day_key": day_key,
                "raw": slot,
            })
            continue

        # 3. Thử parse chuỗi "HH:MM"
        if isinstance(start_raw, str) and isinstance(end_raw, str):
            s_hours = _parse_time_str(start_raw)
            e_hours = _parse_time_str(end_raw)
            if s_hours is not None and e_hours is not None:
                normalized_slots.append({
                    "id": slot.get("id", f"slot_{idx}"),
                    "title": title,
                    "start": s_hours * 3600.0,
                    "end": e_hours * 3600.0,
                    "day_key": day_key,
                    "raw": slot,
                })

    conflicts = []
    num_items = len(normalized_slots)
    for i in range(num_items):
        for j in range(i + 1, num_items):
            s1 = normalized_slots[i]
            s2 = normalized_slots[j]

            # Chỉ so sánh nếu cùng ngày/ngữ cảnh thời gian
            if s1["day_key"] != s2["day_key"]:
                continue

            # Kiểm tra chồng lấn khoảng thời gian: start1 < end2 và start2 < end1
            if s1["start"] < s2["end"] and s2["start"] < s1["end"]:
                overlap_seconds = min(s1["end"], s2["end"]) - max(s1["start"], s2["start"])
                overlap_minutes = max(0.0, round(overlap_seconds / 60.0, 1))
                if overlap_minutes > 0:
                    conflicts.append({
                        "slot_1": s1["raw"],
                        "slot_2": s2["raw"],
                        "conflict_type": "time_overlap",
                        "overlap_minutes": overlap_minutes,
                        "description": (
                            f"Trùng lịch giữa '{s1['title']}' và '{s2['title']}' "
                            f"({overlap_minutes:.0f} phút trên {s1['day_key']})."
                        ),
                    })

    return conflicts
