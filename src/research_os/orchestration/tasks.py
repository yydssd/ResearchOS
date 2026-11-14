"""Research task helpers (plan §9)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from research_os.domain.enums import TaskStatus, TaskType
from research_os.domain.models import ResearchTask, new_id
from research_os.storage.repositories import SqlTaskRepository
from research_os.storage.tables import TaskRow


def create_task(
    session: Session,
    run_id: str,
    task_type: TaskType,
    input_ids: list[str] | None = None,
    priority: int = 0,
    status: TaskStatus = TaskStatus.PENDING,
) -> ResearchTask:
    """Persist a new research task for a run (plan §9)."""
    task = ResearchTask(
        id=new_id("t"),
        run_id=run_id,
        task_type=task_type,
        status=status,
        input_ids=input_ids or [],
        priority=priority,
    )
    SqlTaskRepository(session).create(task)
    return task


def complete_task(session: Session, task: ResearchTask, output_ids: list[str] | None = None) -> ResearchTask:
    """Mark a task COMPLETED and record its output ids; failures must be
    persisted as events by the caller (invariant: never swallow exceptions)."""
    task.status = TaskStatus.COMPLETED
    task.output_ids = output_ids or []
    row = session.get(TaskRow, task.id)
    if row is not None:
        row.status = task.status.value
        row.output_ids = task.output_ids
    return task
