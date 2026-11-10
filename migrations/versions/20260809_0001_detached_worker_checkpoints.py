"""Create detached worker checkpoint table.

Revision ID: 20260809_0001
Revises:
Create Date: 2026-08-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "detached_worker_checkpoints",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("assignment_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("worker_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("sprint", sa.String(length=255), nullable=False),
        sa.Column("jira_issue_key", sa.String(length=64), nullable=False, index=True),
        sa.Column("branch_name", sa.String(length=512), nullable=False),
        sa.Column("worktree_path", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("last_command", sa.Text(), nullable=False),
        sa.Column("resume_action", sa.String(length=64), nullable=False),
        sa.Column("resume_recommendation", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("codex_job_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("context_pack_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("failed_request_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("output_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("resume_after", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("redacted_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("detached_worker_checkpoints")
