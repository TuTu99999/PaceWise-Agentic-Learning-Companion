from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.planning import build_plan_draft
from src.services.planning_time import partition_open_assignments

NOW = datetime(2026, 10, 10, 11, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))


def test_expired_work_cannot_consume_future_capacity_or_become_complete():
    assignments = [{'id': 'expired', 'title': 'Old quiz', 'deadline': '2026-10-10T10:45:00+07:00'},
                   {'id': 'active', 'title': 'New task', 'deadline': '2026-10-10T20:00:00+07:00'}]
    plan_input = {'weekStart': '2026-10-05', 'tasks': [{'taskId': 'expired', 'remainingMin': 540}, {'taskId': 'active', 'remainingMin': 60}],
                  'availability': [{'weekday': 5, 'enabled': True, 'start': '12:00', 'end': '18:00'}], 'unavailable': [],
                  'pinnedBlocks': [{'id': 'old', 'taskId': 'expired', 'date': '2026-10-06', 'start': '15:00', 'end': '16:00'}],
                  'weeklyGoals': [{'id': 'old-goal', 'title': 'Expired work', 'taskIds': ['expired']},
                                  {'id': 'mixed', 'title': 'Current work', 'taskIds': ['expired', 'active']}]}
    original = deepcopy((plan_input, assignments))
    result = build_plan_draft(plan_input, assignments, now=NOW,
        proposed_milestones=[{'milestone_id': 'old-m', 'task_id': 'expired', 'title': 'Never attach to active task'}])
    assert result['feasibility']['feasible']
    assert result['feasibility']['deficitMin'] == 0
    assert result['feasibility']['workRequiredMin'] == 60
    assert result['feasibility']['shortfalls'] == []
    assert {m['taskId'] for m in result['milestones']} == {'active'}
    assert [(g['id'], g['taskIds']) for g in result['weeklyGoals']] == [('mixed', ['active'])]
    assert all(m['milestoneId'] != 'old-m' for m in result['milestones'])
    assert result['expiredTasks'][0]['remainingMin'] == 540
    assert result['expiredTasks'][0]['status'] == 'overdue_unresolved'
    assert all(block['id'] != 'old' for block in result['blocks'])
    assert (plan_input, assignments) == original


def test_deadline_partition_uses_exact_local_time_without_expiring_date_only_today():
    items = [{'id': 'boundary', 'due_at': '2026-10-10T04:00:00Z'},
             {'id': 'date-only', 'deadline': '2026-10-10'},
             {'id': 'future', 'due_at': '2026-10-10T04:01:00Z'},
             {'id': 'submitted', 'deadline': '2026-10-12', 'submission': {'workflow_state': 'submitted'}}]
    active, expired = partition_open_assignments(items, now=NOW, timezone_name='Asia/Ho_Chi_Minh', fallback=NOW.date())
    assert [a['id'] for a in active] == ['date-only', 'future']
    assert [a['id'] for a in expired] == ['boundary']


def test_unselected_expired_assignment_is_history_not_uncovered_future_work():
    result = build_plan_draft({'tasks': [], 'availability': [], 'unavailable': []},
        [{'id': 'old', 'deadline': '2026-10-10T10:00:00+07:00'}], now=NOW)
    assert result['feasibility']['uncoveredTasks'] == []
    assert result['feasibility']['requiredMin'] == 0
    assert result['expiredTasks'][0]['taskId'] == 'old'
